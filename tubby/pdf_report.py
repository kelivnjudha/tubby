from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from tubby.local_ai import AnalysisReport
from tubby.transcript import VideoTranscript
from tubby.utils import format_duration

ProgressCallback = Callable[[str], None]

_INK = colors.HexColor("#182225")
_MUTED = colors.HexColor("#5F6B6E")
_TEAL = colors.HexColor("#177E78")
_CORAL = colors.HexColor("#E36A4A")
_PALE_TEAL = colors.HexColor("#E9F4F2")
_LINE = colors.HexColor("#D8E0E1")


class PdfReportError(RuntimeError):
    """Raised when a PDF report cannot be created."""


@dataclass(frozen=True)
class FontFamily:
    regular: str
    bold: str


def create_pdf_report(
    transcript: VideoTranscript,
    analysis: AnalysisReport,
    output_dir: str | Path,
    output_language: str,
    model: str,
    progress: ProgressCallback | None = None,
) -> Path:
    if progress is not None:
        progress("Building the PDF report...")

    target_dir = Path(output_dir).expanduser().resolve()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PdfReportError(f"Could not create the report folder: {exc}") from exc

    target = target_dir / _report_filename(transcript)
    report_fonts = _register_report_fonts(output_language)
    transcript_fonts = _register_report_fonts(transcript.language_code)
    styles = _build_styles(
        report_fonts,
        transcript_fonts,
        output_language,
        transcript.language_code,
    )

    try:
        with tempfile.NamedTemporaryFile(
            prefix=".tubby-report-",
            suffix=".pdf",
            dir=target_dir,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
    except OSError as exc:
        raise PdfReportError(f"Could not prepare the PDF report: {exc}") from exc

    document = SimpleDocTemplate(
        str(temporary_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=f"Tubby report: {transcript.title}",
        author="Tubby",
        subject="Local AI analysis of a YouTube transcript",
    )
    story = _build_story(
        transcript=transcript,
        analysis=analysis,
        output_language=output_language,
        model=model,
        styles=styles,
    )

    try:
        document.build(
            story,
            onFirstPage=lambda canvas, doc: _draw_page(canvas, doc, report_fonts),
            onLaterPages=lambda canvas, doc: _draw_page(canvas, doc, report_fonts),
        )
        temporary_path.replace(target)
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        raise PdfReportError(f"Could not create the PDF report: {exc}") from exc

    return target


def _build_story(
    transcript: VideoTranscript,
    analysis: AnalysisReport,
    output_language: str,
    model: str,
    styles: dict[str, ParagraphStyle],
) -> list[object]:
    caption_source = "Automatic captions" if transcript.is_auto_generated else "Manual captions"
    story: list[object] = [
        Paragraph("TUBBY", styles["eyebrow"]),
        Paragraph("Video Intelligence Report", styles["title"]),
        Paragraph(escape(transcript.title), styles["video_title"]),
        Spacer(1, 6 * mm),
        _metadata_table(
            (
                ("Source", transcript.source_url),
                ("Uploader", transcript.uploader or "Unknown"),
                ("Duration", format_duration(transcript.duration)),
                ("Transcript", f"{caption_source} - {transcript.language_name}"),
                ("Report language", output_language),
                ("Local model", model),
            ),
            styles,
        ),
        Spacer(1, 7 * mm),
        Paragraph("Executive Summary", styles["section"]),
        _summary_box(analysis.executive_summary, styles),
        Spacer(1, 6 * mm),
    ]

    _append_list_section(story, "Key Points", analysis.key_points, styles)
    _append_list_section(story, "Important Details", analysis.important_details, styles)
    _append_list_section(story, "Decisions and Actions", analysis.decisions_and_actions, styles)
    _append_list_section(story, "Questions and Caveats", analysis.questions_and_caveats, styles)

    story.extend(
        [
            Spacer(1, 8 * mm),
            Paragraph("Source Transcript", styles["title"]),
            Paragraph(
                (
                    "This appendix contains the caption text supplied to the local AI model. "
                    "Timestamps are based on the selected YouTube caption track."
                ),
                styles["body_muted"],
            ),
            Spacer(1, 5 * mm),
        ]
    )
    for cue in transcript.cues:
        story.append(
            Paragraph(
                f'<font color="#177E78"><b>[{cue.timestamp}]</b></font> {escape(cue.text)}',
                styles["transcript"],
            )
        )
    return story


def _append_list_section(
    story: list[object],
    heading: str,
    items: tuple[str, ...],
    styles: dict[str, ParagraphStyle],
) -> None:
    if not items:
        return
    story.append(Paragraph(heading, styles["section"]))
    for index, item in enumerate(items, start=1):
        story.append(Paragraph(f"{index}. {escape(item)}", styles["list"]))
    story.append(Spacer(1, 5 * mm))


def _summary_box(summary: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [[Paragraph(escape(summary), styles["summary"])]],
        colWidths=[174 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _PALE_TEAL),
                ("BOX", (0, 0), (-1, -1), 0.75, _TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _metadata_table(
    values: tuple[tuple[str, str], ...],
    styles: dict[str, ParagraphStyle],
) -> Table:
    rows = [
        [
            Paragraph(escape(label.upper()), styles["meta_label"]),
            Paragraph(_link_or_text(value), styles["meta_value"]),
        ]
        for label, value in values
    ]
    table = Table(rows, colWidths=[37 * mm, 137 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, _LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _link_or_text(value: str) -> str:
    escaped = escape(value)
    if value.startswith(("https://", "http://")):
        return f'<link href="{escaped}" color="#177E78">{escaped}</link>'
    return escaped


def _build_styles(
    report_fonts: FontFamily,
    transcript_fonts: FontFamily,
    output_language: str,
    transcript_language: str,
) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    report_wrap, report_alignment = _text_flow(output_language)
    transcript_wrap, transcript_alignment = _text_flow(transcript_language)
    return {
        "eyebrow": ParagraphStyle(
            "TubbyEyebrow",
            parent=sample["Normal"],
            fontName=report_fonts.bold,
            fontSize=9,
            leading=11,
            textColor=_CORAL,
            alignment=TA_LEFT,
            spaceAfter=3,
        ),
        "title": ParagraphStyle(
            "TubbyTitle",
            parent=sample["Title"],
            fontName=report_fonts.bold,
            fontSize=23,
            leading=28,
            textColor=_INK,
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "video_title": ParagraphStyle(
            "TubbyVideoTitle",
            parent=sample["Heading2"],
            fontName=transcript_fonts.regular,
            fontSize=13,
            leading=18,
            textColor=_MUTED,
            alignment=transcript_alignment,
            wordWrap=transcript_wrap,
        ),
        "section": ParagraphStyle(
            "TubbySection",
            parent=sample["Heading2"],
            fontName=report_fonts.bold,
            fontSize=14,
            leading=18,
            textColor=_INK,
            spaceBefore=2,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "summary": ParagraphStyle(
            "TubbySummary",
            parent=sample["BodyText"],
            fontName=report_fonts.regular,
            fontSize=10.5,
            leading=16,
            textColor=_INK,
            alignment=report_alignment,
            wordWrap=report_wrap,
        ),
        "list": ParagraphStyle(
            "TubbyList",
            parent=sample["BodyText"],
            fontName=report_fonts.regular,
            fontSize=10,
            leading=15,
            leftIndent=5 * mm,
            firstLineIndent=-5 * mm,
            textColor=_INK,
            spaceAfter=5,
            alignment=report_alignment,
            wordWrap=report_wrap,
        ),
        "transcript": ParagraphStyle(
            "TubbyTranscript",
            parent=sample["BodyText"],
            fontName=transcript_fonts.regular,
            fontSize=9,
            leading=13,
            textColor=_INK,
            spaceAfter=4,
            alignment=transcript_alignment,
            wordWrap=transcript_wrap,
        ),
        "body_muted": ParagraphStyle(
            "TubbyBodyMuted",
            parent=sample["BodyText"],
            fontName=report_fonts.regular,
            fontSize=9.5,
            leading=14,
            textColor=_MUTED,
        ),
        "meta_label": ParagraphStyle(
            "TubbyMetaLabel",
            parent=sample["Normal"],
            fontName=report_fonts.bold,
            fontSize=7.5,
            leading=10,
            textColor=_MUTED,
        ),
        "meta_value": ParagraphStyle(
            "TubbyMetaValue",
            parent=sample["Normal"],
            fontName=transcript_fonts.regular,
            fontSize=9,
            leading=12,
            textColor=_INK,
        ),
    }


def _draw_page(canvas: object, document: object, fonts: FontFamily) -> None:
    page_width, page_height = A4
    canvas.saveState()
    canvas.setStrokeColor(_LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, page_height - 14 * mm, page_width - 18 * mm, page_height - 14 * mm)
    canvas.setFont(fonts.bold, 7.5)
    canvas.setFillColor(_MUTED)
    canvas.drawString(18 * mm, page_height - 11 * mm, "TUBBY / LOCAL VIDEO INTELLIGENCE")
    canvas.setFont(fonts.regular, 8)
    canvas.drawRightString(
        page_width - 18 * mm,
        11 * mm,
        f"Page {document.page}",
    )
    canvas.setStrokeColor(_CORAL)
    canvas.setLineWidth(1.5)
    canvas.line(18 * mm, 15 * mm, 43 * mm, 15 * mm)
    canvas.restoreState()


def _register_report_fonts(language_hint: str) -> FontFamily:
    language_group = _language_group(language_hint)
    if language_group == "arabic":
        raise PdfReportError(
            "Right-to-left PDF output is not supported by this Tubby build. "
            "Choose another report language."
        )

    candidates: list[tuple[Path, Path | None]] = []
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

    if language_group == "thai":
        candidates.extend(
            [
                (windows_fonts / "LeelawUI.ttf", None),
                (
                    Path("/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf"),
                    Path("/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf"),
                ),
                (Path("/System/Library/Fonts/Thonburi.ttc"), None),
            ]
        )
    elif language_group == "korean":
        candidates.extend(
            [
                (windows_fonts / "malgun.ttf", windows_fonts / "malgunbd.ttf"),
                (Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"), None),
                (
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
                ),
            ]
        )
    elif language_group == "japanese":
        candidates.extend(
            [
                (windows_fonts / "YuGothR.ttc", windows_fonts / "YuGothB.ttc"),
                (
                    Path(
                        "/System/Library/Fonts/"
                        "\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4\u30b7\u30c3\u30af W3.ttc"
                    ),
                    None,
                ),
                (
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
                ),
            ]
        )
    elif language_group == "chinese":
        candidates.extend(
            [
                (windows_fonts / "msyh.ttc", windows_fonts / "msyhbd.ttc"),
                (Path("/System/Library/Fonts/PingFang.ttc"), None),
                (
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
                ),
            ]
        )
    elif language_group == "hindi":
        candidates.extend(
            [
                (windows_fonts / "Nirmala.ttc", None),
                (
                    Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
                    Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
                ),
                (Path("/System/Library/Fonts/Kohinoor.ttc"), None),
            ]
        )
    else:
        reportlab_fonts = Path(reportlab.__file__).resolve().parent / "fonts"
        candidates.extend(
            [
                (windows_fonts / "arial.ttf", windows_fonts / "arialbd.ttf"),
                (
                    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                ),
                (
                    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
                ),
                (reportlab_fonts / "Vera.ttf", reportlab_fonts / "VeraBd.ttf"),
            ]
        )

    registered_fonts = set(pdfmetrics.getRegisteredFontNames())
    for regular_path, bold_path in candidates:
        if not regular_path.exists():
            continue
        selected_bold = bold_path if bold_path and bold_path.exists() else regular_path
        font_key = hashlib.sha1(
            f"{regular_path.resolve()}|{selected_bold.resolve()}".encode("utf-8")
        ).hexdigest()[:12]
        regular_name = f"TubbyReportRegular{font_key}"
        bold_name = f"TubbyReportBold{font_key}"
        try:
            if regular_name not in registered_fonts:
                pdfmetrics.registerFont(TTFont(regular_name, str(regular_path), subfontIndex=0))
            if bold_name not in registered_fonts:
                pdfmetrics.registerFont(TTFont(bold_name, str(selected_bold), subfontIndex=0))
            pdfmetrics.registerFontFamily(
                regular_name,
                normal=regular_name,
                bold=bold_name,
                italic=regular_name,
                boldItalic=bold_name,
            )
        except Exception:
            continue
        return FontFamily(regular=regular_name, bold=bold_name)

    if language_group in {"thai", "korean", "japanese", "chinese", "hindi"}:
        raise PdfReportError(
            f"No compatible {language_hint} font was found. Install a Noto Sans font "
            "for that language and try again."
        )
    return FontFamily(regular="Helvetica", bold="Helvetica-Bold")


def _language_group(language_hint: str) -> str:
    normalized = language_hint.strip().casefold().replace("_", "-")
    if normalized == "thai" or normalized.startswith("th"):
        return "thai"
    if normalized == "korean" or normalized.startswith("ko"):
        return "korean"
    if normalized == "japanese" or normalized.startswith("ja"):
        return "japanese"
    if "chinese" in normalized or normalized.startswith("zh"):
        return "chinese"
    if normalized == "hindi" or normalized.startswith("hi"):
        return "hindi"
    if normalized == "arabic" or normalized.startswith("ar"):
        return "arabic"
    return "default"


def _text_flow(language_hint: str) -> tuple[str | None, int]:
    language_group = _language_group(language_hint)
    if language_group == "arabic":
        return "RTL", TA_RIGHT
    if language_group in {"korean", "japanese", "chinese"}:
        return "CJK", TA_LEFT
    return None, TA_LEFT


def _report_filename(transcript: VideoTranscript) -> str:
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", transcript.title)
    safe_title = re.sub(r"\s+", " ", safe_title).strip(" .")
    if not safe_title:
        safe_title = "YouTube Video"
    return f"{safe_title[:90]} [{transcript.video_id}] - Tubby Report.pdf"
