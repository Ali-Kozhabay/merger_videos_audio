import logging
import os
import urllib.request

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.constants import FONT_CANDIDATES, FONT_DIR, FONT_DOWNLOAD_URLS

logger = logging.getLogger(__name__)


def ensure_unicode_fonts() -> None:
    """Ensure at least one Unicode-capable font is available locally for PDFs."""
    os.makedirs(FONT_DIR, exist_ok=True)
    for target_path, url in FONT_DOWNLOAD_URLS:
        if os.path.exists(target_path):
            continue
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                with open(target_path, "wb") as f:
                    f.write(response.read())
            logger.info("Downloaded font to %s", target_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not download font from %s: %s", url, exc)


def pick_font_name() -> str:
    """Return a font name registered with ReportLab that supports Unicode."""
    ensure_unicode_fonts()
    fallback = "Helvetica"

    for font_path, candidate_name in FONT_CANDIDATES:
        if not os.path.exists(font_path):
            continue
        try:
            pdfmetrics.getFont(candidate_name)
        except KeyError:
            try:
                pdfmetrics.registerFont(TTFont(candidate_name, font_path))
            except Exception:  # noqa: BLE001
                continue
        return candidate_name

    logger.warning("Falling back to Helvetica; Cyrillic/Kazakh may render poorly")
    return fallback
