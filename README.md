# Video Audio Merger Bot

A small Pyrogram-based Telegram userbot that downloads every video you forward to it, extracts each audio track with MoviePy, merges the clips, and sends you a single MP3 file back.

## Features
- Accepts Telegram videos or video documents (up to the usual 2 GB limit).
- Tracks a per-user queue so you can keep adding clips before merging.
- `/status`, `/merge`, `/clear`, `/help`, and `/start` commands for basic control.
- Cleans up downloaded videos and temporary audio files automatically.

## Requirements
- Python 3.13+
- [Poetry](https://python-poetry.org/) or another way to install dependencies from `pyproject.toml`
- A Telegram account to run the userbot.

## Setup
1. Copy `config.py`'s expected variables into a `.env` file (same folder) in this format:
   ```env
   API_ID=123456
   API_HASH=0123456789abcdef0123456789abcdef
   PHONE_NUMBER=+123456789
   BOT_NAME=video_audio_merger_bot
   ```
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Create the working folders once (the app also does this automatically): `temp_videos/` for downloads and `output_audio/` for merged files.

## Running the bot
```bash
poetry run python main.py
```
The first start triggers Pyrogram’s login flow—enter the Telegram verification code in the terminal, and the `video_audio_merger_bot.session` file will be created for future runs.

## Usage flow
1. Send the bot private video messages (or upload video documents).
2. Use `/status` to list what’s in your queue.
3. When you have at least two videos, send `/merge`; the bot extracts and concatenates only the audio tracks and replies with an MP3 file.
4. Use `/clear` anytime to delete queued files from disk and start fresh.

## Project structure
- `main.py` – bot logic, handlers, and MoviePy processing.
- `config.py` – Pydantic settings loader for environment variables.
- `temp_videos/`, `output_audio/`, `data/`, `video_audio_merger_bot.session` – runtime artifacts that the bot reads/writes.

Feel free to extend the bot with validation, background jobs, or a bot-token flow, but the current setup is ready for personal use once credentials are supplied.
