# Video Audio Merger Bot

Telegram bot (Telethon) that queues your videos, extracts and concatenates their audio tracks, then lets you transcribe and translate the merged audio to English, Russian, and Kazakh with OpenAI.

## Features
- Accepts Telegram videos/documents (up to 2 GB each) and keeps a per-user queue.
- Extracts audio with MoviePy and returns a single merged MP3.
- `/status`, `/done` (via “✅ Process Videos” button), `/clear`, `/translate`, `/start` commands.
- `/translate` transcribes the last merged audio with Whisper and sends PDFs containing the original transcript plus English/Russian/Kazakh translations (via free Google Translate).
- `/video_from_text` sends your text/PDF to Runway; it builds 3 blocks of 3 scenes (~100s), adds a 3s gen4 bumper after each block, loops the reel 3× (~300s total), and burns in narration + subtitles.
- Cleans up temporary files automatically.
- `/keywords` auto-builds a stitched 5–10 minute MP4 by generating images (free service) from keywords extracted from your latest paraphrased transcript and stitching them with MoviePy; falls back to a local LLM+MoviePy slide generator if image generation fails.

## Requirements
- Python 3.10+
- [Poetry](https://python-poetry.org/) or another way to install from `pyproject.toml`
- Telegram bot token + OpenAI API key for Whisper/ChatGPT.
- Runway API key.

## Setup
1. Create a `.env` next to `config.py`:
   ```env
   API_ID=123456
   API_HASH=0123456789abcdef0123456789abcdef
   BOT_NAME=video_audio_merger_bot
   BOT_TOKEN=123456:abcdef...
   API_KEY=sk-...
   RUNWAY_API_KEY=your_runway_api_key
   RUNWAY_MODEL=veo3.1
   RUNWAY_IMAGE_MODEL=gen4_image_turbo
   RUNWAY_SIZE=1280:720
   RUNWAY_SCENES=9
   RUNWAY_SCENE_SECONDS=9
   ```
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Ensure the folders exist (the app also auto-creates them): `temp_videos/` for downloads and `output_audio/` for stored merged audio.

## Runway setup (for `/video_from_text`)
- Create a Runway account, grab your API key from Settings → Developer → API Keys, and set `RUNWAY_API_KEY`.
- `/video_from_text` calls Runway's task API, polls until success, downloads the MP4, and sends it back—no webhook or public URL required. It now stitches 3×3 scenes (9 total) with 3s gen4 bumpers, loops the ~100s reel three times (~300s), and adds narration + subtitles. Defaults: scene length 10s (`RUNWAY_SCENE_SECONDS`), ratio `RUNWAY_SIZE`, video model `RUNWAY_MODEL` (default `veo3.1`/`veo3.1_fast`), bumper model `RUNWAY_IMAGE_MODEL` (gen4_image_turbo by default).

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
6. Run `/paraphrase` after `/translate`, then `/keywords` to get a 5–10 minute montage (images per keyword stitched into video; falls back to slides if image gen fails).
7. Use `/video_from_text` to request a Runway video; the bot polls Runway, builds 9 scenes in three blocks with gen4 bumpers, loops the ~100s reel three times, and returns the narrated/subtitled clip.

## Project structure
- `main.py` – entrypoint that runs the Telethon bot.
- `app/bot.py` – Telethon client creation plus all handlers.
- `app/runway.py` – Runway client with task creation, polling, and video download.
- `app/audio_utils.py` – Whisper-safe compression, transcription, and translations.
- `app/pdf_utils.py` & `app/fonts.py` – PDF generation with Unicode font handling.
- `app/state.py` – in-memory per-user queues.
- `config.py` – Pydantic settings loader for environment variables.
- `temp_videos/`, `output_audio/`, `data/`, `bot_session.session` – runtime artifacts.
