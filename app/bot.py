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
from app.video_utils import (
    build_video_from_images,
    build_subtitle_entries,
    ensure_text_for_duration,
    generate_images_for_keywords,
    generate_keyword_video,
    mux_video_audio_and_subtitles,
    synthesize_speech_from_text,
    text_to_scenes,
    VIDEO_SIZE,
)
from app import runway
from app.pdf_utils import create_pdf, create_pdf_for_paraphrasing, extract_text_from_pdf
from app.state import (
    user_videos,
    user_audios,
    user_transcripts,
    user_paraphrases,
    pending_video_from_text,
    clear_user_data,
    clear_user_videos,
    clear_user_paraphrase,
)
from config import settings
from openai import OpenAI


logger = logging.getLogger(__name__)


def reply_keyboard() -> List[List[Button]]:
    return [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")],
        [Button.text("/translate"), Button.text("/paraphrase")],
        [Button.text("/video_from_paraphrase"), Button.text("/video_from_text")],
    ]


def register_handlers(client: TelegramClient) -> None:
    async def _extract_text_from_pdf_message(message, temp_dir: str) -> tuple[str | None, str | None]:
        doc = getattr(message, "document", None)
        mime = getattr(doc, "mime_type", "") if doc else ""
        if not mime.lower().endswith("pdf"):
            return None, None
        pdf_path = os.path.join(temp_dir, f"video_from_text_{message.id}.pdf")
        await client.download_media(message, pdf_path)
        try:
            text = await asyncio.to_thread(extract_text_from_pdf, pdf_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to extract text from PDF: %s", exc)
            text = None
        return text, pdf_path

    async def _build_and_send_video_from_text(
        event,
        user_text: str,
        status_msg,
        temp_dir: str,
    ) -> None:
        if not settings.RUNWAY_API_KEY:
            await status_msg.edit("❌ Runway is not configured. Set RUNWAY_API_KEY and try again.")
            return

        parts = 3
        scenes_per_part = 3
        total_scene_count = parts * scenes_per_part  # 9 scenes total
        per_scene_seconds = 10  # fixed to hit ~100s before looping
        image_clip_seconds = 3  # gen4 bumper after every 3 scenes
        loop_count = 3  # repeat ~100s reel -> ~300s
        model = getattr(settings, "RUNWAY_MODEL", "veo3.1_fast") or "veo3.1_fast"
        image_model = getattr(settings, "RUNWAY_IMAGE_MODEL", "gen4_image_turbo") or "gen4_image_turbo"
        ratio = getattr(settings, "RUNWAY_SIZE", "1280:720") or "1280:720"

        scene_prompts = text_to_scenes(user_text, max_scenes=total_scene_count) or [user_text]
        while len(scene_prompts) < total_scene_count:
            scene_prompts.append(scene_prompts[-1])
        scene_prompts = scene_prompts[:total_scene_count]

        video_paths: list[str] = []
        bumper_paths: list[str] = []
        clips = []
        loop_clips: list = []
        stitched_path = None
        looped_path = None
        stitched = None
        looped = None
        cli = OpenAI(api_key=settings.API_KEY)

        try:
            from moviepy.editor import VideoFileClip, concatenate_videoclips

            for part_idx in range(parts):
                start = part_idx * scenes_per_part
                block_prompts = scene_prompts[start:start + scenes_per_part]
                for scene_idx, scene_prompt in enumerate(block_prompts, start=1):
                    await status_msg.edit(
                        f"🚀 Sending part {part_idx + 1}/{parts}, scene {scene_idx}/{scenes_per_part} "
                        f"to Runway ({per_scene_seconds}s, {model})..."
                    )
                    video_path, _ = await runway.generate_runway_video(
                        api_key=settings.RUNWAY_API_KEY,
                        prompt=scene_prompt,
                        duration=per_scene_seconds,
                        model=model,
                        ratio=ratio,
                        download=True,
                    )
                    video_paths.append(video_path)
                    clip = await asyncio.to_thread(VideoFileClip, video_path)
                    clips.append(clip)

                bumper_prompt = " ".join(block_prompts)
                await status_msg.edit(
                    f"🖼️ Generating gen4 bumper for part {part_idx + 1}/{parts} ({image_clip_seconds}s)..."
                )
                bumper_path, _ = await runway.generate_runway_video(
                    api_key=settings.RUNWAY_API_KEY,
                    prompt=f"Cinematic still for: {bumper_prompt}",
                    duration=image_clip_seconds,
                    model=image_model,
                    ratio=ratio,
                    download=True,
                )
                bumper_paths.append(bumper_path)
                bumper_clip = await asyncio.to_thread(VideoFileClip, bumper_path)
                clips.append(bumper_clip)

            await status_msg.edit("🎬 Concatenating 9 scenes + 3 bumpers (~100s)...")
            stitched = await asyncio.to_thread(
                lambda: concatenate_videoclips(clips, method="compose")
            )

            stitched_path = os.path.join(temp_dir, "runway_stitched_base.mp4")
            await asyncio.to_thread(
                stitched.write_videofile,
                stitched_path,
                fps=24,
                codec="libx264",
                audio=True,
                audio_codec="aac",
                verbose=False,
                logger=None,
            )

            await status_msg.edit("🔁 Looping the base reel 3× to reach ~300s...")
            loop_clips = [await asyncio.to_thread(VideoFileClip, stitched_path) for _ in range(loop_count)]
            looped = await asyncio.to_thread(
                lambda: concatenate_videoclips(loop_clips, method="compose")
            )

            looped_path = os.path.join(temp_dir, "runway_looped_300s.mp4")
            await asyncio.to_thread(
                looped.write_videofile,
                looped_path,
                fps=24,
                codec="libx264",
                audio=True,
                audio_codec="aac",
                verbose=False,
                logger=None,
            )

            final_video_duration = looped.duration or (parts * ((scenes_per_part * per_scene_seconds) + image_clip_seconds) * loop_count)
            final_width, final_height = looped.size if getattr(looped, "size", None) else (1280, 720)

            await status_msg.edit("🎙️ Generating narration and subtitles to fit ~270s...")
            narration_script = await ensure_text_for_duration(
                cli,
                user_text,
                target_duration=final_video_duration,
                pause_every=30.0,
                pause_seconds=3.0,
            )
            speech_path, audio_duration = await synthesize_speech_from_text(
                cli,
                narration_script,
                temp_dir,
            )
            subtitles = build_subtitle_entries(narration_script, audio_duration, lead_time=0.25)

            await status_msg.edit("🔊 Merging video with narration + subtitles...")
            final_path, final_duration, width, height = await mux_video_audio_and_subtitles(
                looped_path,
                speech_path,
                subtitles,
                temp_dir,
                target_duration=audio_duration,
            )

            await status_msg.edit("📤 Uploading your Runway video...")
            await client.send_file(
                event.chat_id,
                final_path,
                caption=(
                    f"✅ Runway video ready (~{int(final_duration)}s, "
                    "9 scenes × 3 blocks, looped 3× with narration)."
                ),
                attributes=[
                    DocumentAttributeVideo(
                        duration=max(int(final_duration), 1),
                        w=int(width or final_width or 1280),
                        h=int(height or final_height or 720),
                        supports_streaming=True,
                    )
                ],
                mime_type="video/mp4",
                force_document=False,
            )
        except Exception as runway_exc:  # noqa: BLE001
            logger.exception("Runway video generation failed: %s", runway_exc)
            await status_msg.edit(
                "❌ Runway could not generate video. Try a shorter text or try again later."
            )
        finally:
            for clip in clips:
                try:
                    clip.close()
                except Exception:
                    pass
            for clip in loop_clips:
                try:
                    clip.close()
                except Exception:
                    pass
            for composite in (stitched, looped):
                try:
                    if composite:
                        composite.close()
                except Exception:
                    pass
            for path in video_paths + bumper_paths:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            if stitched_path and os.path.exists(stitched_path):
                try:
                    os.remove(stitched_path)
                except OSError:
                    pass
            if looped_path and os.path.exists(looped_path):
                try:
                    os.remove(looped_path)
                except OSError:
                    pass

    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        await event.respond(
            "👋 Welcome to Video Audio Concatenator Bot!\n\n"
            "📹 Send me multiple videos (up to 2GB each)\n"
            "🎵 I'll extract and combine their audio\n"
            "🔊 Then send you the merged audio file\n\n"
            "🪄 `/video_from_paraphrase` builds a stitched video from your paraphrased transcript (images per scene + subtitles).\n"
            "🆕 `/video_from_text` sends your text/PDF to Runway and returns a mini-video (no webhooks needed).\n"
            "Use the buttons below to control the bot:",
            buttons=reply_keyboard()
        )
        logger.info("%s started server", getattr(event.sender, "first_name", ""))

    @client.on(events.NewMessage(pattern='/clear'))
    async def clear_handler(event):
        user_id = event.sender_id
        if user_id in user_videos or pending_video_from_text.get(user_id):
            clear_user_data(user_id)
            await event.respond("✅ Cleared your data and pending requests!")
            logger.info("%s cleared data", getattr(event.sender, "first_name", ""))
            return
        await event.respond("❌ No videos in queue", buttons=reply_keyboard())

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

    @client.on(events.NewMessage(func=lambda e: e.sender_id in pending_video_from_text))
    async def video_from_text_followup_handler(event):
        """Handle follow-up text or PDF after /video_from_text was issued without content."""
        user_id = event.sender_id
        if event.raw_text and event.raw_text.strip().startswith("/"):
            return  # allow other command handlers to process

        temp_dir = tempfile.mkdtemp(prefix="video_from_text_")
        cleanup_paths: list[str] = []
        try:
            pdf_text, pdf_path = await _extract_text_from_pdf_message(event.message, temp_dir)
            if pdf_path:
                cleanup_paths.append(pdf_path)

            user_text = (event.raw_text or "").strip() or pdf_text
            if not user_text:
                await event.respond(
                    "❌ I didn't find any text in your message. Send a PDF or plain text.",
                    buttons=reply_keyboard(),
                )
                return

            pending_video_from_text.pop(user_id, None)
            status_msg = await event.respond("📜 Received content. Sending to Runway...")
            await _build_and_send_video_from_text(
                event,
                user_text,
                status_msg,
                temp_dir,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("video_from_text_handler failed: %s", exc)
            await event.respond("❌ Couldn't create video. Please try again with shorter text or a smaller PDF.", buttons=reply_keyboard())
        finally:
            for path in cleanup_paths:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
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
            clear_user_paraphrase(user_id)
            user_paraphrases[user_id] = paraphrased_text
            user_transcripts.pop(user_id, None)
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

    @client.on(events.NewMessage(pattern=r"(?is)^/keywords"))
    async def keywords_video_handler(event):
        """
        Create a video montage from the last paraphrased transcript:
        generate an image per text slice (no keywords) and stitch them together. Falls back to slides if image gen fails.
        """
        user_id = event.sender_id
        paraphrased_text = user_paraphrases.get(user_id)
        if not paraphrased_text:
            await event.respond(
                "❌ No paraphrased text found. Run `/translate` then `/paraphrase` first.",
                buttons=reply_keyboard()
            )
            return

        status_msg = await event.respond("🔍 Slicing your paraphrased text into scenes...")
        temp_dir = tempfile.mkdtemp(prefix="keywords_video_")
        max_scenes = 30

        try:
            cli = OpenAI(api_key=settings.API_KEY)
            scenes = text_to_scenes(paraphrased_text, max_scenes=max_scenes)
            if not scenes:
                raise ValueError("Couldn't derive scenes from paraphrased text.")

            await status_msg.edit("🎙️ Creating narration and subtitles...")
            speech_path, audio_duration = await synthesize_speech_from_text(
                cli,
                paraphrased_text,
                temp_dir,
            )
            # Keep visuals close to narration length to avoid a long silent tail.
            target_duration = audio_duration + 1.5
            subtitles = build_subtitle_entries(paraphrased_text, audio_duration, lead_time=0.15)

            video_w, video_h = VIDEO_SIZE
            try:
                await status_msg.edit("🖼️ Generating images for your scenes ...")
                image_paths = await generate_images_for_keywords(
                    scenes,
                    temp_dir,
                    cli=cli,
                )

                await status_msg.edit("🎞️ Building video from generated images...")
                result_path, total_duration, video_w, video_h = await build_video_from_images(
                    image_paths,
                    temp_dir,
                    target_duration=audio_duration,
                )
            except Exception as image_exc:  # noqa: BLE001
                logger.exception("Image-based video failed, falling back: %s", image_exc)
                await status_msg.edit("⚠️ Image generation failed, falling back to storyboard slides...")
                result_path, total_duration = await generate_keyword_video(
                    cli,
                    scenes,
                    temp_dir,
                    target_duration=audio_duration,
                )

            await status_msg.edit("🔊 Merging narration and subtitles...")
            final_path, final_duration, video_w, video_h = await mux_video_audio_and_subtitles(
                result_path,
                speech_path,
                subtitles,
                temp_dir,
                target_duration=audio_duration,
            )

            await status_msg.edit("📤 Uploading your stitched mini-video...")
            await client.send_file(
                event.chat_id,
                final_path,
                caption=f"✅ Combined {len(scenes)} scenes into one clip.",
                attributes=[
                    DocumentAttributeVideo(
                        duration=int(final_duration),
                        w=video_w,
                        h=video_h,
                        supports_streaming=True,
                    )
                ],
                mime_type="video/mp4",
                force_document=False,
            )
            clear_user_paraphrase(user_id)
        except Exception as exc:  # noqa: BLE001
            await status_msg.edit(f"❌ Couldn't create video: {exc}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @client.on(events.NewMessage(pattern=r"(?is)^/video_from_text(?:\s+(.+))?"))
    async def video_from_text_handler(event):
        """
        Create a Runway mini-video from arbitrary text or a provided PDF.
        """
        user_id = event.sender_id
        inline_text = (event.pattern_match.group(1) or "").strip() if event.pattern_match else ""
        temp_dir = tempfile.mkdtemp(prefix="video_from_text_")
        cleanup_paths: list[str] = []

        try:
            pdf_text = None
            # If the command is used in reply to a PDF, grab it
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                pdf_text, pdf_path = await _extract_text_from_pdf_message(reply_msg, temp_dir)
                if pdf_path:
                    cleanup_paths.append(pdf_path)
            # Or if the command message itself has a PDF attached
            if pdf_text is None:
                this_pdf_text, pdf_path = await _extract_text_from_pdf_message(event.message, temp_dir)
                if pdf_path:
                    cleanup_paths.append(pdf_path)
                if this_pdf_text:
                    pdf_text = this_pdf_text

            user_text = inline_text or pdf_text
            if not user_text:
                pending_video_from_text[user_id] = True
                await event.respond(
                    "📥 Send the text or PDF now (or reply to this message with a PDF). "
                    "I'll request a Runway mini-video from it.",
                    buttons=reply_keyboard(),
                )
                return

            pending_video_from_text.pop(user_id, None)
            status_msg = await event.respond("📜 Received content. Sending to Runway...")
            await _build_and_send_video_from_text(
                event,
                user_text,
                status_msg,
                temp_dir,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("video_from_text_followup_handler failed: %s", exc)
            await event.respond("❌ Couldn't create video. Please try again with shorter text or a smaller PDF.", buttons=reply_keyboard())
        finally:
            for path in cleanup_paths:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            shutil.rmtree(temp_dir, ignore_errors=True)


def create_client() -> TelegramClient:
    return TelegramClient('bot_session', settings.API_ID, settings.API_HASH)


async def run_client(client: TelegramClient) -> None:
    logger.info("STARTING TELETHON BOT...")
    try:
        await client.start(bot_token=settings.BOT_TOKEN)
        logger.info("TELETHON BOT STARTED ✓")
        await client.run_until_disconnected()
        logger.info("TELETHON BOT DISCONNECTED")
    except Exception as exc:  # noqa: BLE001
        logger.warning("TELETHON BOT FAILED:", repr(exc))
