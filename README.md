# Video Audio Merger Bot

Telegram bot (Telethon) that queues your videos, extracts and concatenates their audio tracks, then lets you transcribe and translate the merged audio to English, Russian, and Kazakh with OpenAI.

## Features
- Accepts Telegram videos/documents (up to 2 GB each) and keeps a per-user queue.
- Extracts audio with MoviePy and returns a single merged MP3.
- `/status`, `/done` (via “✅ Process Videos” button), `/clear`, `/translate`, `/start` commands.
- `/translate` transcribes the last merged audio with Whisper and sends PDFs containing the original transcript plus English/Russian/Kazakh translations (via free Google Translate).
- Cleans up temporary files automatically.

## Requirements
- Python 3.10+
- [Poetry](https://python-poetry.org/) or another way to install from `pyproject.toml`
- Telegram bot token + OpenAI API key for Whisper/ChatGPT.

## Setup
1. Create a `.env` next to `config.py`:
   ```env
   API_ID=123456
   API_HASH=0123456789abcdef0123456789abcdef
   BOT_NAME=video_audio_merger_bot
   BOT_TOKEN=123456:abcdef...
   API_KEY=sk-...
   ```
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Ensure the folders exist (the app also auto-creates them): `temp_videos/` for downloads and `output_audio/` for stored merged audio.

## Running the bot
```bash
poetry run python main.py
```
The bot uses the supplied `BOT_TOKEN` to start; no interactive login is required.

## Usage flow
1. Send the bot one or more videos.
2. Tap “📊 Status” or `/status` to see your queue.
3. Tap “✅ Process Videos” or `/done` to merge and receive the combined MP3.
4. Tap `/translate` to transcribe that merged audio and receive a PDF with English/Russian/Kazakh translations.
5. Use `/clear` anytime to reset your queue.

## Project structure
- `main.py` – handlers, MoviePy processing, and translation/PDF generation.
- `config.py` – Pydantic settings loader for environment variables.
- `temp_videos/`, `output_audio/`, `data/`, `bot_session.session` – runtime artifacts.
