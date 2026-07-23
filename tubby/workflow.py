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
from tubby.media_transcript import DEFAULT_WHISPER_MODEL, transcribe_media_file
from tubby.pdf_report import create_pdf_report
from tubby.report_styles import DEFAULT_REPORT_STYLE
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
    report_style: str = DEFAULT_REPORT_STYLE,
    progress: ProgressCallback | None = None,
    include_source_transcript: bool = False,
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
    return _analyze_to_pdf(
        transcript,
        output_dir=output_dir,
        output_language=output_language,
        model=model,
        ollama_url=ollama_url,
        report_style=report_style,
        progress=progress,
        include_source_transcript=include_source_transcript,
    )


def analyze_media_to_pdf(
    media_path: str | Path,
    output_dir: str | Path,
    output_language: str = "English",
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    report_style: str = DEFAULT_REPORT_STYLE,
    whisper_model: str = DEFAULT_WHISPER_MODEL,
    progress: ProgressCallback | None = None,
    include_source_transcript: bool = False,
) -> AnalysisResult:
    _report_progress(progress, "Preparing local media transcription...")
    transcript = transcribe_media_file(
        media_path,
        model_size=whisper_model,
        progress=progress,
    )
    _report_progress(
        progress,
        f"Transcribed {len(transcript.cues):,} speech segments in {transcript.language_name}.",
    )
    return _analyze_to_pdf(
        transcript,
        output_dir=output_dir,
        output_language=output_language,
        model=model,
        ollama_url=ollama_url,
        report_style=report_style,
        progress=progress,
        include_source_transcript=include_source_transcript,
    )


def _analyze_to_pdf(
    transcript: VideoTranscript,
    output_dir: str | Path,
    output_language: str,
    model: str,
    ollama_url: str,
    report_style: str,
    progress: ProgressCallback | None,
    include_source_transcript: bool,
) -> AnalysisResult:
    analysis = analyze_transcript(
        transcript,
        output_language=output_language,
        model=model,
        base_url=ollama_url,
        report_style=report_style,
        progress=progress,
    )
    pdf_path = create_pdf_report(
        transcript,
        analysis,
        output_dir=output_dir,
        output_language=output_language,
        model=model,
        report_style=report_style,
        progress=progress,
        include_source_transcript=include_source_transcript,
    )
    return AnalysisResult(transcript=transcript, analysis=analysis, pdf_path=pdf_path)


def _report_progress(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)
