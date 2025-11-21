import asyncio
import os
import tempfile
from typing import Dict

from deep_translator import GoogleTranslator
from openai import OpenAI

from app.constants import WHISPER_SAFE_FILESIZE_BYTES, WHISPER_TARGET_BITRATE, WHISPER_TARGET_SAMPLE_RATE


async def compress_audio_for_whisper(source_path: str) -> str:
    """
    Downsample and downmix audio to keep size within Whisper limits.

    Returns the path to the compressed file (caller is responsible for cleanup).
    """
    def _compress() -> str:
        from moviepy.audio.io.AudioFileClip import AudioFileClip

        fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        clip = AudioFileClip(source_path)
        clip.write_audiofile(
            temp_path,
            fps=WHISPER_TARGET_SAMPLE_RATE,
            codec="libmp3lame",
            bitrate=WHISPER_TARGET_BITRATE,
            ffmpeg_params=["-ac", "1"],
            logger=None
        )
        clip.close()
        return temp_path

    return await asyncio.to_thread(_compress)


async def transcribe_audio(cli: OpenAI, audio_path: str) -> str:
    """Run Whisper transcription in a worker thread to avoid blocking the event loop."""
    def _transcribe() -> str:
        with open(audio_path, "rb") as audio:
            result = cli.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                response_format="text"
            )
        if isinstance(result, str):
            return result
        return getattr(result, "text", str(result))

    return await asyncio.to_thread(_transcribe)


async def translate_languages(text: str, languages: Dict[str, str]) -> Dict[str, str]:
    """Translate text into multiple languages using Google Translate."""
    def _translate() -> Dict[str, str]:
        translations: Dict[str, str] = {}
        for lang_name, lang_code in languages.items():
            translator = GoogleTranslator(source="auto", target=lang_code)
            translations[lang_name] = translator.translate(text)
        return translations

    return await asyncio.to_thread(_translate)


def is_too_large_for_whisper(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > WHISPER_SAFE_FILESIZE_BYTES
