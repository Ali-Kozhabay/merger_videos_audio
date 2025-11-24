import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime
from typing import List

from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio

from app.audio_utils import (
    transcribe_audio,
    translate_languages,
    paraphrasing_transcribe_text,
)
from app.pdf_utils import create_pdf,create_pdf_for_paraphrasing
from app.state import (
    user_videos,
    user_audios,
    user_transcripts,
    clear_user_data,
    clear_user_videos,
    clear_user_audio,
)
from config import settings
from openai import OpenAI


logger = logging.getLogger(__name__)


def reply_keyboard() -> List[List[Button]]:
    return [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")],
        [Button.text("/translate"),Button.text("/paraphrase")],
    ]


def register_handlers(client: TelegramClient) -> None:
    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        await event.respond(
            "👋 Welcome to Video Audio Concatenator Bot!\n\n"
            "📹 Send me multiple videos (up to 2GB each)\n"
            "🎵 I'll extract and combine their audio\n"
            "🔊 Then send you the merged audio file\n\n"
            "Use the buttons below to control the bot:",
            buttons=reply_keyboard()
        )
        logger.info("%s started server", getattr(event.sender, "first_name", ""))

    @client.on(events.NewMessage(pattern='/clear'))
    async def clear_handler(event):
        user_id = event.sender_id
        if user_id in user_videos:
            clear_user_data(user_id)
            await event.respond("✅ Video queue cleared!")
            logger.info("%s cleared video queue", getattr(event.sender, "first_name", ""))
        else:
            await event.respond("❌ No videos in queue")

    @client.on(events.NewMessage(pattern='/status'))
    async def status_handler(event):
        user_id = event.sender_id
        if user_id in user_videos and user_videos[user_id]:
            count = len(user_videos[user_id])
            await event.respond(
                f"📊 You have {count} video(s) in queue.\n"
                f"Tap '✅ Process Videos' to process them.",
                buttons=reply_keyboard()
            )
            logger.info("%s checked status", getattr(event.sender, "first_name", ""))
        else:
            await event.respond("📭 No videos in queue", buttons=reply_keyboard())

    @client.on(events.NewMessage(pattern='/translate'))
    async def translate_handler(event):
        user_id = event.sender_id
        reply_buttons = reply_keyboard()
        audio_path = user_audios.get(user_id)
        if not audio_path or not os.path.exists(audio_path):
            await event.respond(
                "❌ No processed audio found. Tap '✅ Process Videos' first.",
                buttons=reply_buttons
            )
            user_audios.pop(user_id, None)
            return

        processing_msg = await event.reply("🎧 Transcribing audio...")
        cli = OpenAI(api_key=settings.API_KEY)
        pdf_paths = []
        cleanup_paths = []

        try:
            transcript_input_path = audio_path

            transcript = await transcribe_audio(cli, transcript_input_path)
            user_transcripts[user_id] = transcript

            languages = {
                "Russian": "ru",
                "English": "en",
                "Kazakh": "kk"
            }

            await processing_msg.edit("🌐 Translating (Google)...")
            translations = await translate_languages(transcript, languages)

            await processing_msg.edit("📄 Generating PDFs...")
            for lang_name in languages.keys():
                per_lang_pdf = f"transcript_{event.message.id}_{languages[lang_name]}.pdf"
                await asyncio.to_thread(
                    create_pdf,
                    transcript,
                    {lang_name: translations[lang_name]},
                    per_lang_pdf
                )
                pdf_paths.append(per_lang_pdf)
                await event.reply(file=per_lang_pdf,
                                  message=f"✅ Transcript + {lang_name} translation")
                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except OSError:
                        raise OSError(f"Failed to remove {audio_path}")

        except Exception as exc:  # noqa: BLE001
            await event.reply(f"❌ {exc}", buttons=reply_buttons)
        finally:
            await processing_msg.delete()
            for path in pdf_paths + cleanup_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass


    @client.on(events.NewMessage(pattern='/done'))
    async def done_handler(event):
        from moviepy.editor import VideoFileClip, concatenate_audioclips, AudioFileClip

        user_id = event.sender_id
        reply_buttons = reply_keyboard()

        if user_id not in user_videos or not user_videos[user_id]:
            await event.respond("❌ No videos to process. Please send videos first!", buttons=reply_buttons)
            return

        processing_msg = await event.respond("⏳ Processing your videos... This may take a while.")
        temp_dir = tempfile.mkdtemp()
        audio_clips = []

        try:
            for idx, video_message in enumerate(user_videos[user_id]):
                status_msg = await processing_msg.edit(
                    f"📥 Downloading video {idx + 1}/{len(user_videos[user_id])}..."
                )

                video_path = os.path.join(temp_dir, f"video_{idx}.mp4")
                audio_path = os.path.join(temp_dir, f"audio_{idx}.mp3")

                await client.download_media(video_message, video_path)
                await status_msg.edit(
                    f"🎵 Extracting audio {idx + 1}/{len(user_videos[user_id])}..."
                )

                video_clip = VideoFileClip(video_path)
                if video_clip.audio is not None:
                    video_clip.audio.write_audiofile(audio_path, logger=None)
                    audio_clips.append(AudioFileClip(audio_path))
                else:
                    await event.respond(f"⚠️ Video {idx + 1} has no audio track, skipping...")
                video_clip.close()

            if not audio_clips:
                await processing_msg.edit("❌ No audio found in any videos!")
                clear_user_data(user_id)
                shutil.rmtree(temp_dir)
                return

            await processing_msg.edit("🔗 Concatenating audio files...")
            final_audio = concatenate_audioclips(audio_clips)
            output_path = os.path.join(temp_dir, "combined_audio.mp3")
            final_audio.write_audiofile(output_path, logger=None)

            os.makedirs("output_audio", exist_ok=True)
            old_audio_path = user_audios.get(user_id)
            if old_audio_path and os.path.exists(old_audio_path):
                try:
                    os.remove(old_audio_path)
                except OSError:
                    pass
            persistent_path = os.path.join(
                "output_audio",
                f"combined_{user_id}_{int(datetime.now().timestamp())}.mp3"
            )
            shutil.copy(output_path, persistent_path)
            user_audios[user_id] = persistent_path

            for clip in audio_clips:
                clip.close()
            final_audio.close()

            await processing_msg.edit("📤 Uploading combined audio...")
            await client.send_file(
                event.chat_id,
                output_path,
                attributes=[DocumentAttributeAudio(
                    duration=int(final_audio.duration),
                    title="Combined Audio",
                    performer="Video Audio Bot"
                )],
                caption="✅ Here's your combined audio!",
                buttons=reply_buttons
            )
            await processing_msg.delete()
            clear_user_videos(user_id)  # keep audio for /translate
        except Exception as exc:  # noqa: BLE001
            await event.respond(f"❌ Error processing videos: {exc}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @client.on(events.NewMessage(func=lambda e: e.video or (e.document and any(
        isinstance(attr, DocumentAttributeVideo) for attr in e.document.attributes
    ))))
    async def video_handler(event):
        user_id = event.sender_id
        if user_id not in user_videos:
            user_videos[user_id] = []
        user_videos[user_id].append(event.message)
        count = len(user_videos[user_id])
        await event.respond(
            f"✅ Video {count} received!\n\n"
            f"📹 Total videos in queue: {count}\n"
            f"Send more videos or tap '✅ Process Videos' to process them.",
            buttons=[
                [Button.text("✅ Process Videos"), Button.text("📊 Status")],
                [Button.text("/clear"), Button.text("/start")]
            ]
        )

    @client.on(events.NewMessage(pattern="/paraphrase"))
    async def paraphrase_handler(event):
        user_id = event.sender_id
        reply_buttons = reply_keyboard()
        transcript = user_transcripts.get(user_id)

        if not transcript:
            await event.respond(
                "❌ No transcripts found. Tap '/translate' after processing audio first.",
                buttons=reply_buttons
            )
            return

        processing_msg = await event.reply("📝 Paraphrasing transcript...")
        cli = OpenAI(api_key=settings.API_KEY)
        pdf_path = f"paraphrased_{event.message.id}.pdf"

        try:
            paraphrased_text = await paraphrasing_transcribe_text(cli, transcript)
            if not paraphrased_text:
                raise ValueError("Empty paraphrase received")
            await processing_msg.edit("📄 Generating PDFs...")
            await asyncio.to_thread(
                create_pdf_for_paraphrasing,
                transcript,
                paraphrased_text,
                pdf_path
            )
            await event.reply(
                file=pdf_path,
                message="✅ Paraphrased!"
            )
        except Exception as exc:  # noqa: BLE001
            await processing_msg.edit(f"❌ {exc}", buttons=reply_buttons)
        finally:
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except OSError:
                    pass



    @client.on(events.NewMessage(pattern='✅ Process Videos'))
    async def process_button_handler(event):
        await done_handler(event)

    @client.on(events.NewMessage(pattern='📊 Status'))
    async def status_button_handler(event):
        await status_handler(event)


def create_client() -> TelegramClient:
    return TelegramClient('bot_session', settings.API_ID, settings.API_HASH)


async def run_client(client: TelegramClient) -> None:
    print("STARTING TELETHON BOT...")
    try:
        await client.start(bot_token=settings.BOT_TOKEN)
        print("TELETHON BOT STARTED ✓")
        await client.run_until_disconnected()
        print("TELETHON BOT DISCONNECTED")
    except Exception as exc:  # noqa: BLE001
        print("TELETHON BOT FAILED:", repr(exc))
