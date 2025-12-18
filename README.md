# Video Audio Merger Bot

Telegram bot built with Telethon (MTProto) that:
- queues videos per user and merges their audio into a single MP3
- optionally transcribes + translates the merged audio (OpenAI Whisper + Google Translate)
- optionally paraphrases the transcript and generates a narrated, subtitled “story video”
- optionally generates a longer narrated video via Runway from plain text or a PDF

This repo is designed for running your own bot instance (it is not a hosted service).

## Features
- **Video → merged audio:** send multiple Telegram videos/documents and tap **✅ Process Videos** to get a combined MP3.
- **/translate:** transcribe the merged MP3 with `whisper-1`, then generate PDFs with translations (RU/EN/KK).
- **/paraphrase:** paraphrase the last transcript (English) and send a PDF.
- **/video_from_paraphrase:** turn your paraphrase into a narrated, subtitled MP4
- **/video_from_text:** send text (or a PDF) and get a ~5 minute narrated, subtitled Runway video back (no webhooks required).

## Requirements
- Python 3.10+
- `ffmpeg` (MoviePy uses it to read/write audio/video)
- Poetry (recommended) or any installer that supports `pyproject.toml`
- Credentials:
  - Telegram `API_ID` + `API_HASH` (from https://my.telegram.org)
  - Telegram bot token `BOT_TOKEN` (from @BotFather)
  - OpenAI API key `API_KEY` (for Whisper / GPT / TTS / optional image fallback)
  - Runway key `RUNWAY_API_KEY` (only required for `/video_from_text`)

## Quick start
1. Create your `.env` file:
   - `cp .env.example .env`
   - fill in the values (see “Configuration” below)
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Run the bot:
   ```bash
   poetry run python main.py
   ```

## Configuration
Environment variables are loaded from `.env` (see `config.py`).

Required:
- `API_ID`: Telegram API ID (integer)
- `API_HASH`: Telegram API hash
- `BOT_TOKEN`: bot token from @BotFather
- `BOT_NAME`: bot name (currently required by settings)
- `API_KEY`: OpenAI API key

Optional (Runway):
- `RUNWAY_API_KEY`: required for `/video_from_text`
- `RUNWAY_MODEL`: defaults to `veo3.1_fast`
- `RUNWAY_IMAGE_MODEL`: defaults to `gen4_image_turbo` (used for the short “bumper” clips)
- `RUNWAY_SIZE`: defaults to `1280:720`

## Commands (user-facing)
- `/start`: show the keyboard and help text
- `/status`: show how many videos are queued
- `/clear`: clear your queued videos and any pending requests
- `/done` or **✅ Process Videos**: merge queued videos into one MP3
- `/translate`: transcribe + translate the last merged MP3 and send PDFs
- `/paraphrase`: paraphrase the last transcript and send a PDF
- `/video_from_paraphrase`: build a narrated + subtitled MP4 from your paraphrase
- `/video_from_text [text]`: generate a Runway video from text (also supports PDFs)

Note: the keyboard includes `/video_from_paraphrase`, but there is no handler implemented for it yet. Use `/keywords` instead.

## Typical flows
**Merge audio**
1. Send 1+ videos to the bot.
2. Tap **✅ Process Videos** (or run `/done`).
3. You’ll receive `combined_audio.mp3`.

**Translate**
1. Run `/translate` after you’ve merged audio.
2. The bot sends a PDF per language (RU/EN/KK).

**Paraphrase → video**
1. Run `/translate`, then `/paraphrase`.
2. Run `/video_from_paraphrase` to get a narrated + subtitled MP4.

**Runway video from text/PDF**
1. Run `/video_from_text some text...`, or send a PDF and run `/video_from_text` in reply.
2. If you run `/video_from_text` without content, the bot will ask you to send text/PDF next.

## Data & privacy notes
- Videos are downloaded to a temporary directory during processing and deleted afterwards.
- The latest merged audio is also copied to `output_audio/` so it can be used for `/translate` (it is deleted after translation completes).
- Per-user queues/transcripts/paraphrases are stored **in memory**; restarting the process clears them.
- External services used (depending on commands): OpenAI, Google Translate, Runway, and `image.pollinations.ai`.

## Docs
- `docs/DEPLOYMENT.md` – running on a server (systemd example)
- `docs/TROUBLESHOOTING.md` – common setup/runtime issues

## Project structure
- `main.py` – async entrypoint
- `app/bot.py` – Telethon handlers + user flows
- `app/service.py` – client creation + shared helpers
- `app/runway.py` – Runway task creation, polling, and downloading
- `app/audio_utils.py` – Whisper transcription + translations + paraphrasing
- `app/video_utils.py` – narration, subtitles, image/slide video building
- `app/pdf_utils.py`, `app/fonts.py` – PDF generation + Unicode font handling
- `app/state.py` – in-memory per-user state
- `config.py` – environment variable settings loader
