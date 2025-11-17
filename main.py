import os
import logging


from pyrogram import Client, filters
from pyrogram.types import Message
from moviepy.editor import VideoFileClip, concatenate_audioclips, AudioFileClip
from pathlib import Path

from config import settings

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)



# Directories
TEMP_DIR = "temp_videos"
OUTPUT_DIR = "output_audio"

# Create necessary directories
Path(TEMP_DIR).mkdir(exist_ok=True)
Path(OUTPUT_DIR).mkdir(exist_ok=True)

# Store user videos in memory
user_videos = {}

# Initialize Pyrogram Client (User Account)
app = Client(
    name=settings.BOT_NAME,
    api_id=settings.API_ID,
    api_hash=settings.API_HASH,
    phone_number=settings.PHONE_NUMBER,
)


@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Send welcome message."""
    await message.reply_text(
        "🎬 **Welcome to Video Audio Merger Bot!**\n\n"
        "📹 Send me multiple video files (up to 2GB each!)\n"
        "🎵 I'll extract and merge the audio\n"
        "🔊 Then send you the combined audio file\n\n"
        "**Commands:**\n"
        "• `/start` - Start the bot\n"
        "• `/merge` - Merge all sent videos' audio\n"
        "• `/clear` - Clear all videos and start over\n"
        "• `/status` - Check how many videos you've sent\n\n"
    )


@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Send help message."""
    await message.reply_text(
        "**How to use:**\n\n"
        "1️⃣ Send me video files one by one\n"
        "2️⃣ Use `/status` to check your queue\n"
        "3️⃣ Use `/merge` to combine all audio\n"
        "4️⃣ Use `/clear` to delete all and start over\n\n"
        "💡 **Tip:** You can send videos up to 2GB each!"
    )


@app.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    """Show status of user's videos."""
    user_id = message.from_user.id

    if user_id not in user_videos or not user_videos[user_id]:
        await message.reply_text("📭 No videos in queue. Send some videos first!")
        return

    count = len(user_videos[user_id])
    video_list = "\n".join([f"  {i + 1}. {os.path.basename(v)}" for i, v in enumerate(user_videos[user_id])])

    await message.reply_text(
        f"📊 **Status:**\n"
        f"Videos in queue: **{count}**\n\n"
        f"**Videos:**\n{video_list}\n\n"
        f"Use `/merge` to combine them or `/clear` to start over."
    )


@app.on_message(filters.command("clear") & filters.private)
async def clear_command(client: Client, message: Message):
    """Clear all videos for the user."""
    user_id = message.from_user.id

    if user_id in user_videos:
        # Delete files
        deleted_count = 0
        for video_path in user_videos[user_id]:
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Error deleting file {video_path}: {e}")

        # Clear from memory
        user_videos[user_id] = []

        await message.reply_text(f"🗑️ Cleared **{deleted_count}** video(s)! You can start fresh now.")
    else:
        await message.reply_text("📭 No videos to clear.")


@app.on_message(filters.video & filters.private | filters.document & filters.private)
async def handle_video(client: Client, message: Message):
    """Handle incoming video files."""
    user_id = message.from_user.id

    # Initialize user's video list if not exists
    if user_id not in user_videos:
        user_videos[user_id] = []

    # Get video (can be sent as video or document)
    video = message.video or message.document

    if not video:
        await message.reply_text("❌ Please send a valid video file.")
        return

    # Check if document is actually a video
    if message.document and not (message.document.mime_type and 'video' in message.document.mime_type):
        await message.reply_text("❌ Please send a valid video file.")
        return

    # Get file info
    file_size_mb = video.file_size / (1024 * 1024)
    file_name = video.file_name or f"video_{len(user_videos[user_id])}.mp4"

    status_msg = await message.reply_text(f"⬇️ Downloading **{file_name}** ({file_size_mb:.2f} MB)...")

    try:
        # Download video
        file_path = os.path.join(TEMP_DIR, f"{user_id}_{len(user_videos[user_id])}_{file_name}")
        await message.download(file_path)

        # Store video path
        user_videos[user_id].append(file_path)

        await status_msg.edit_text(
            f"✅ **Video received!**\n\n"
            f"📊 Total videos: **{len(user_videos[user_id])}**\n"
            f"💾 Size: {file_size_mb:.2f} MB\n\n"
            f"Send more videos or use `/merge` to combine audio."
        )

    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        await status_msg.edit_text(f"❌ Error downloading video: {str(e)}")


@app.on_message(filters.command("merge") & filters.private)
async def merge_audio_command(client: Client, message: Message):
    """Merge audio from all videos."""
    user_id = message.from_user.id

    if user_id not in user_videos or not user_videos[user_id]:
        await message.reply_text("❌ No videos to merge. Send some videos first!")
        return

    if len(user_videos[user_id]) < 2:
        await message.reply_text("❌ You need at least 2 videos to merge. Send more videos!")
        return

    status_msg = await message.reply_text(f"🎵 Processing **{len(user_videos[user_id])}** videos...")

    audio_clips = []
    temp_audio_files = []

    try:
        # Extract audio from each video
        for i, video_path in enumerate(user_videos[user_id], 1):
            await status_msg.edit_text(
                f"🎬 Extracting audio from video **{i}/{len(user_videos[user_id])}**...\n"
                f"📁 {os.path.basename(video_path)}"
            )

            video_clip = VideoFileClip(video_path)
            audio = video_clip.audio

            if audio is None:
                await message.reply_text(f"⚠️ Video {i} has no audio track, skipping...")
                video_clip.close()
                continue

            # Save audio temporarily
            temp_audio_path = os.path.join(TEMP_DIR, f"{user_id}_audio_{i}.mp3")
            audio.write_audiofile(temp_audio_path, logger=None, verbose=False)
            temp_audio_files.append(temp_audio_path)

            audio_clips.append(AudioFileClip(temp_audio_path))
            video_clip.close()

        if not audio_clips:
            await status_msg.edit_text("❌ No audio found in any of the videos!")
            return

        # Concatenate audio
        await status_msg.edit_text(f"🔗 Merging **{len(audio_clips)}** audio tracks...")
        final_audio = concatenate_audioclips(audio_clips)

        # Save final audio
        output_path = os.path.join(OUTPUT_DIR, f"{user_id}_merged_audio.mp3")
        final_audio.write_audiofile(output_path, logger=None, verbose=False)

        # Get file size
        output_size_mb = os.path.getsize(output_path) / (1024 * 1024)

        # Close clips
        for clip in audio_clips:
            clip.close()
        final_audio.close()

        # Send audio file
        await status_msg.edit_text(f"📤 Sending merged audio ({output_size_mb:.2f} MB)...")

        await message.reply_audio(
            audio=output_path,
            title="Merged Audio",
            caption=f"✅ **Audio merged successfully!**\n\n"
                    f"🎵 Combined {len(audio_clips)} audio tracks\n"
                    f"💾 Size: {output_size_mb:.2f} MB\n\n"
                    f"Use `/clear` to remove videos or send more to merge again."
        )

        await status_msg.delete()

        # Cleanup temp audio files
        for temp_file in temp_audio_files:
            try:
                os.remove(temp_file)
            except:
                pass

        # Cleanup output file
        try:
            os.remove(output_path)
        except:
            pass

    except Exception as e:
        logger.error(f"Error merging audio: {e}")
        await status_msg.edit_text(f"❌ **Error merging audio:**\n`{str(e)}`")

        # Cleanup on error
        for clip in audio_clips:
            clip.close()


        # Cleanup temp files on error
        for temp_file in temp_audio_files:
            os.remove(temp_file)



def main():
    """Start the bot."""
    logger.info("Starting Video Audio Merger Bot with Pyrogram...")
    logger.info("First run will require phone verification code from Telegram")

    # Run the bot
    app.run()


if __name__ == '__main__':
    main()