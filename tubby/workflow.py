from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tubby.languages import language_code_for
from tubby.local_ai import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    AnalysisReport,
    analyze_transcript,
)
from tubby.pdf_report import create_pdf_report
from tubby.transcript import VideoTranscript, fetch_youtube_transcript

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class AnalysisResult:
    transcript: VideoTranscript
    analysis: AnalysisReport
    pdf_path: Path


def analyze_youtube_to_pdf(
    url: str,
    output_dir: str | Path,
    output_language: str = "English",
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    progress: ProgressCallback | None = None,
) -> AnalysisResult:
    _report_progress(progress, "Reading the YouTube transcript...")
    transcript = fetch_youtube_transcript(
        url,
        preferred_language_code=language_code_for(output_language),
    )
    _report_progress(
        progress,
        f"Loaded {len(transcript.cues):,} transcript segments in {transcript.language_name}.",
    )
    analysis = analyze_transcript(
        transcript,
        output_language=output_language,
        model=model,
        base_url=ollama_url,
        progress=progress,
    )
    pdf_path = create_pdf_report(
        transcript,
        analysis,
        output_dir=output_dir,
        output_language=output_language,
        model=model,
        progress=progress,
    )
    return AnalysisResult(transcript=transcript, analysis=analysis, pdf_path=pdf_path)


def _report_progress(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)
