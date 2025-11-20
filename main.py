import os
import asyncio
import tempfile
import shutil
import logging

from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
from moviepy.editor import VideoFileClip, concatenate_audioclips, AudioFileClip

from config import settings


logger = logging.getLogger(__name__)
# Initialize the client
client = TelegramClient('bot_session', settings.API_ID, settings.API_HASH)

# Store user video collections
user_videos = {}


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
        [Button.text("/clear"), Button.text("/start")]
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
        [Button.text("/clear"), Button.text("/start")]
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


@client.on(events.NewMessage(pattern='/done'))
async def done_handler(event):
    """Process all videos and create combined audio"""
    user_id = event.sender_id

    reply_buttons = [
        [Button.text("✅ Process Videos"), Button.text("📊 Status")],
        [Button.text("/clear"), Button.text("/start")]
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


# Callback query handler for inline buttons (keeping old functionality)
@client.on(events.CallbackQuery)
async def callback_handler(event):
    """Handle button clicks"""
    user_id = event.sender_id
    data = event.data.decode('utf-8')

    if data == "status":
        if user_id in user_videos and user_videos[user_id]:
            count = len(user_videos[user_id])
            buttons = [
                [Button.inline("✅ Process Videos", b"done")],
                [Button.inline("❌ Clear Queue", b"cancel")]
            ]
            await event.edit(
                f"📊 Queue Status\n\n"
                f"📹 Videos in queue: {count}\n"
                f"Ready to process!",
                buttons=buttons
            )
        else:
            buttons = [[Button.inline("🔙 Back to Start", b"start")]]
            await event.edit("📭 No videos in queue\n\nSend me some videos!", buttons=buttons)

    elif data == "cancel":
        if user_id in user_videos:
            del user_videos[user_id]
            buttons = [[Button.inline("🔙 Back to Start", b"start")]]
            await event.edit("✅ Video queue cleared!", buttons=buttons)
        else:
            buttons = [[Button.inline("🔙 Back to Start", b"start")]]
            await event.edit("❌ No videos in queue", buttons=buttons)

    elif data == "done":
        if user_id not in user_videos or not user_videos[user_id]:
            buttons = [[Button.inline("🔙 Back to Start", b"start")]]
            await event.edit("❌ No videos to process. Please send videos first!", buttons=buttons)
            return

        await event.edit("⏳ Processing your videos... This may take a while.")

        temp_dir = tempfile.mkdtemp()
        audio_clips = []

        try:
            # Download and extract audio from each video
            for idx, video_message in enumerate(user_videos[user_id]):
                await event.edit(
                    f"📥 Downloading video {idx + 1}/{len(user_videos[user_id])}..."
                )

                video_path = os.path.join(temp_dir, f"video_{idx}.mp4")
                audio_path = os.path.join(temp_dir, f"audio_{idx}.mp3")

                # Download video using Telethon client
                await client.download_media(video_message, video_path)

                await event.edit(
                    f"🎵 Extracting audio {idx + 1}/{len(user_videos[user_id])}..."
                )

                # Extract audio
                video_clip = VideoFileClip(video_path)
                if video_clip.audio is not None:
                    video_clip.audio.write_audiofile(audio_path, logger=None)
                    audio_clips.append(AudioFileClip(audio_path))
                    video_clip.close()
                else:
                    await client.send_message(
                        event.chat_id,
                        f"⚠️ Video {idx + 1} has no audio track, skipping..."
                    )
                    video_clip.close()
                    os.remove(video_path)
                    continue

                # Clean up video file
                os.remove(video_path)

            if not audio_clips:
                buttons = [[Button.inline("🔙 Back to Start", b"start")]]
                await event.edit("❌ No audio found in any videos!", buttons=buttons)
                del user_videos[user_id]
                shutil.rmtree(temp_dir)
                return

            await event.edit("🔗 Concatenating audio files...")

            # Concatenate all audio clips
            final_audio = concatenate_audioclips(audio_clips)
            output_path = os.path.join(temp_dir, "combined_audio.mp3")
            final_audio.write_audiofile(output_path, logger=None)

            # Close all clips
            for clip in audio_clips:
                clip.close()
            final_audio.close()

            await event.edit("📤 Uploading combined audio...")

            # Send the combined audio
            buttons = [[Button.inline("🔄 Process More Videos", b"start")]]
            await client.send_file(
                event.chat_id,
                output_path,
                attributes=[DocumentAttributeAudio(
                    duration=int(final_audio.duration),
                    title="Combined Audio",
                    performer="Video Audio Bot"
                )],
                caption="✅ Here's your combined audio!",
                buttons=buttons
            )

            await event.delete()

            # Clear user's video queue
            del user_videos[user_id]

        except Exception as e:
            buttons = [[Button.inline("🔙 Back to Start", b"start")]]
            await event.edit(f"❌ Error processing videos: {str(e)}", buttons=buttons)
            print(f"Error: {e}")

        finally:
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)

    elif data == "start":
        buttons = [
            [Button.inline("📊 Check Status", b"status")],
            [Button.inline("✅ Process Videos", b"done"), Button.inline("❌ Clear Queue", b"cancel")]
        ]

        await event.edit(
            "👋 Welcome to Video Audio Concatenator Bot!\n\n"
            "📹 Send me multiple videos (up to 2GB each)\n"
            "🎵 I'll extract and combine their audio\n"
            "🔊 Then send you the merged audio file\n\n"
            "Use the buttons below to control the bot:",
            buttons=buttons
        )



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





