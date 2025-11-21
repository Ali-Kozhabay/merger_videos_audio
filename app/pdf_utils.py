from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.fonts import pick_font_name


def create_pdf(transcript: str, translations: dict[str, str], pdf_path: str) -> None:
    """Create a PDF with the transcript and translations."""
    font_name = pick_font_name()

    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch)

    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor='#2c3e50',
        spaceAfter=20,
        alignment=1,
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

    title = Paragraph("Audio Transcription & Translation", title_style)
    elements.append(title)

    timestamp = Paragraph(f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>",
                          styles['Normal'])
    elements.append(timestamp)
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("📝 Original Transcript", heading_style))
    clean_transcript = escape(transcript).replace("\n", "<br/>")
    elements.append(Paragraph(clean_transcript, body_style))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph("🌐 Translations", heading_style))
    elements.append(Spacer(1, 0.1 * inch))

    for lang_name, translated_text in translations.items():
        elements.append(Paragraph(f"<b>{lang_name}:</b>", body_style))
        clean_translation = escape(translated_text).replace("\n", "<br/>")
        elements.append(Paragraph(clean_translation, body_style))
        elements.append(Spacer(1, 0.15 * inch))

    doc.build(elements)
