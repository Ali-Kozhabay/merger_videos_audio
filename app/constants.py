import os

# Whisper API accepts files up to 25MB; keep headroom for safety.
WHISPER_SAFE_FILESIZE_BYTES = 22 * 1024 * 1024
WHISPER_TARGET_SAMPLE_RATE = 16_000
WHISPER_TARGET_BITRATE = "64k"

# Font locations (local first, then common system paths)
FONT_DIR = os.path.join("data", "fonts")
FONT_CANDIDATES = [
    (os.path.join(FONT_DIR, "DejaVuSans.ttf"), "DejaVuSans"),
    (os.path.join(FONT_DIR, "NotoSans-Regular.ttf"), "NotoSans"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "NotoSans"),
    ("/usr/share/fonts/noto/NotoSans-Regular.ttf", "NotoSans"),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "ArialUnicode"),
]

FONT_DOWNLOAD_URLS = [
    (
        os.path.join(FONT_DIR, "DejaVuSans.ttf"),
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf",
    ),
    (
        os.path.join(FONT_DIR, "NotoSans-Regular.ttf"),
        "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    ),
]
