import os
import asyncio
import tempfile
import shutil
import logging
from datetime import datetime
from xml.sax.saxutils import escape


from openai import  OpenAI
from deep_translator import GoogleTranslator
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
from moviepy.editor import VideoFileClip, concatenate_audioclips, AudioFileClip
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from config import settings


logger = logging.getLogger(__name__)
# Initialize the client
client = TelegramClient('bot_session', settings.API_ID, settings.API_HASH)

# Store user video collections
user_videos = {}
user_audios = {}


@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Handle /start command"""
    inline_buttons = [
        [Button.inline("📊 Check Status", b"status")],
        [Button.inline("✅ Process Videos", b"done"), Button.inline("❌ Clear Queue", b"cancel")]
    ]

    # Reply keyboard buttons (always visible at bottom)
    reply_buttons = [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")],
        [Button.text("/translate")]
    ]
    logger.info(f"{event.sender.first_name} started server")
    await event.respond(
        "👋 Welcome to Video Audio Concatenator Bot!\n\n"
        "📹 Send me multiple videos (up to 2GB each)\n"
        "🎵 I'll extract and combine their audio\n"
        "🔊 Then send you the merged audio file\n\n"
        "Use the buttons below to control the bot:",
        buttons=reply_buttons
    )

@client.on(events.NewMessage(pattern='/clear'))
async def clear_handler(event):
    """Clear user's video queue (alias for /cancel)"""
    user_id = event.sender_id
    if user_id in user_videos:
        del user_videos[user_id]
        await event.respond("✅ Video queue cleared!")
        logger.info(f"{event.sender.first_name} cleared video queue")
    else:
        await event.respond("❌ No videos in queue")


@client.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Show queue status"""
    user_id = event.sender_id

    reply_buttons = [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")],
        [Button.text("/translate")]
    ]

    if user_id in user_videos and user_videos[user_id]:
        count = len(user_videos[user_id])
        logger.info(f"{event.sender.first_name}  checked status ")
        await event.respond(
            f"📊 You have {count} video(s) in queue.\n"
            f"Tap '✅ Process Videos' to process them.",
            buttons=reply_buttons
        )
    else:
        await event.respond("📭 No videos in queue", buttons=reply_buttons)


def create_pdf(transcript, translations, pdf_path):
    """
    Creates a PDF with the transcript and translations.

    Args:
        transcript: Original transcription text
        translations: Dictionary of language name -> translated text (can be single entry)
        pdf_path: Output PDF file path
    """
    # Use a Unicode-capable font so Cyrillic/Kazakh render correctly
    font_name = "ArialUnicode"
    font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    if os.path.exists(font_path):
        try:
            pdfmetrics.getFont(font_name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
    else:
        font_name = "Helvetica"  # fallback, may not render Cyrillic ideally

    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch)

    # Container for PDF elements
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor='#2c3e50',
        spaceAfter=20,
        alignment=1,  # Center
        fontName=font_name
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor='#34495e',
        spaceAfter=10,
        spaceBefore=15,
        fontName=font_name
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        leading=16,
        spaceAfter=10,
        fontName=font_name
    )

    # Add title
    title = Paragraph("Audio Transcription & Translation", title_style)
    elements.append(title)

    # Add timestamp
    timestamp = Paragraph(f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>",
                          styles['Normal'])
    elements.append(timestamp)
    elements.append(Spacer(1, 0.3 * inch))

    # Add original transcript
    elements.append(Paragraph("📝 Original Transcript", heading_style))
    clean_transcript = escape(transcript).replace("\n", "<br/>")
    elements.append(Paragraph(clean_transcript, body_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Add translations
    elements.append(Paragraph("🌐 Translations", heading_style))
    elements.append(Spacer(1, 0.1 * inch))

    for lang_name, translated_text in translations.items():
        elements.append(Paragraph(f"<b>{lang_name}:</b>", body_style))
        clean_translation = escape(translated_text).replace("\n", "<br/>")
        elements.append(Paragraph(clean_translation, body_style))
        elements.append(Spacer(1, 0.15 * inch))

    # Build PDF
    doc.build(elements)


@client.on(events.NewMessage(pattern='/translate'))
async def translate_handler(event):
    """Translate video"""
    user_id = event.sender_id
    reply_buttons = [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")],
        [Button.text("/translate")]
    ]
    audio_path = user_audios.get(user_id)
    if not audio_path or not os.path.exists(audio_path):
        await event.respond(
            "❌ No processed audio found. Tap '✅ Process Videos' first.",
            buttons=reply_buttons
        )
        # Clean up stale mapping if file went missing
        if user_id in user_audios:
            user_audios.pop(user_id, None)
        return

    processing_msg = await event.reply("🎧 Transcribing audio...")

    cli = OpenAI(api_key=settings.API_KEY)
    pdf_paths = []
    translation_succeeded = False
    try:
        with open(audio_path, "rb") as audio:
            transcript = cli.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                response_format="text"
            )

            # Target languages for translation
            languages = {
                "Russian": "ru",
                "English": "en",
                "Kazakh": "kk"
            }

            # Update status
            await processing_msg.edit("🌐 Translating (Google)...")

            # Store translations
            translations = {}
            # Translate to each language
            try:
                for lang_name, lang_code in languages.items():
                    translator = GoogleTranslator(source="auto", target=lang_code)
                    translations[lang_name] = translator.translate(transcript)
            except Exception as translate_err:
                await processing_msg.edit("❌ Translation failed.")
                await event.reply(f"❌ Translation failed: {translate_err}", buttons=reply_buttons)
                return

            # Update status
            await processing_msg.edit("📄 Generating PDFs...")

            pdf_paths = []
            # Create and send one PDF per language
            for lang_name, lang_code in languages.items():
                per_lang_pdf = f"transcript_{event.message.id}_{lang_code}.pdf"
                create_pdf(transcript, {lang_name: translations[lang_name]}, per_lang_pdf)
                pdf_paths.append(per_lang_pdf)
                await event.reply(file=per_lang_pdf,
                                  message=f"✅ Transcript + {lang_name} translation")

            translation_succeeded = True
    except Exception as e:
        await event.reply(f"❌ {str(e)}", buttons=reply_buttons)
        # Delete processing message
    finally:
        await processing_msg.delete()
        # Clean up generated PDFs
        for path in pdf_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        # Clean up stored audio after successful translation
        if translation_succeeded:
            user_audios.pop(user_id, None)
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    pass


@client.on(events.NewMessage(pattern='/done'))
async def done_handler(event):
    """Process all videos and create combined audio"""
    user_id = event.sender_id

    reply_buttons = [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")],
        [Button.text("/translate")]
    ]

    if user_id not in user_videos or not user_videos[user_id]:
        await event.respond("❌ No videos to process. Please send videos first!", buttons=reply_buttons)
        return

    processing_msg = await event.respond("⏳ Processing your videos... This may take a while.")

    temp_dir = tempfile.mkdtemp()
    audio_clips = []

    try:
        # Download and extract audio from each video
        for idx, video_message in enumerate(user_videos[user_id]):
            status_msg = await processing_msg.edit(
                f"📥 Downloading video {idx + 1}/{len(user_videos[user_id])}..."
            )

            video_path = os.path.join(temp_dir, f"video_{idx}.mp4")
            audio_path = os.path.join(temp_dir, f"audio_{idx}.mp3")

            # Download video using Telethon client
            await client.download_media(video_message, video_path)

            await status_msg.edit(
                f"🎵 Extracting audio {idx + 1}/{len(user_videos[user_id])}..."
            )

            # Extract audio
            video_clip = VideoFileClip(video_path)
            if video_clip.audio is not None:
                video_clip.audio.write_audiofile(audio_path, logger=None)
                audio_clips.append(AudioFileClip(audio_path))
                video_clip.close()
            else:
                await event.respond(f"⚠️ Video {idx + 1} has no audio track, skipping...")
                video_clip.close()
                continue


        if not audio_clips:
            await processing_msg.edit("❌ No audio found in any videos!")
            del user_videos[user_id]
            shutil.rmtree(temp_dir)
            return

        await processing_msg.edit("🔗 Concatenating audio files...")

        # Concatenate all audio clips
        final_audio = concatenate_audioclips(audio_clips)
        output_path = os.path.join(temp_dir, "combined_audio.mp3")
        final_audio.write_audiofile(output_path, logger=None)

        # Persist combined audio for later translation
        os.makedirs("output_audio", exist_ok=True)
        # Remove someone's previous stored audio to avoid leaks
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

        # Close all clips
        for clip in audio_clips:
            clip.close()
        final_audio.close()

        await processing_msg.edit("📤 Uploading combined audio...")
        logger.info(f"{event.sender.first_name}  got extracted audio ")
        # Send the combined audio
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
        # Clear user's video queue
        del user_videos[user_id]

    except Exception as e:
        await event.respond(f"❌ Error processing videos: {str(e)}")
        print(f"Error: {e}")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


@client.on(events.NewMessage(func=lambda e: e.video or (e.document and any(
    isinstance(attr, DocumentAttributeVideo) for attr in e.document.attributes
))))
async def video_handler(event):
    """Handle incoming video messages"""
    user_id = event.sender_id

    # Initialize user's video list if not exists
    if user_id not in user_videos:
        user_videos[user_id] = []

    # Add video message to user's queue
    user_videos[user_id].append(event.message)

    count = len(user_videos[user_id])

    reply_buttons = [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")]
    ]

    await event.respond(
        f"✅ Video {count} received!\n\n"
        f"📹 Total videos in queue: {count}\n"
        f"Send more videos or tap '✅ Process Videos' to process them.",
        buttons=reply_buttons
    )


# Handle text button presses
@client.on(events.NewMessage(pattern='✅ Process Videos'))
async def process_button_handler(event):
    """Handle Process Videos button press"""
    await done_handler(event)


@client.on(events.NewMessage(pattern='📊 Status'))
async def status_button_handler(event):
    """Handle Status button press"""
    await status_handler(event)



async def run_bot():
    print("STARTING TELETHON BOT...")
    try:
        # запускаем бота
        await client.start(bot_token=settings.BOT_TOKEN)
        print("TELETHON BOT STARTED ✓")

        # держим его живым, пока соединение не разорвётся
        await client.run_until_disconnected()
        print("TELETHON BOT DISCONNECTED")
    except Exception as e:
        print("TELETHON BOT FAILED:", repr(e))




if __name__ == "__main__":
    asyncio.run(run_bot())
