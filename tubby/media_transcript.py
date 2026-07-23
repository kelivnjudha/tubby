from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Callable

from tubby.languages import language_name_for_code
from tubby.transcript import TranscriptCue, TranscriptError, VideoTranscript
from tubby.utils import format_duration

ProgressCallback = Callable[[str], None]

DEFAULT_WHISPER_MODEL = os.environ.get("TUBBY_WHISPER_MODEL", "small")
WHISPER_MODEL_OPTIONS = ("tiny", "base", "small", "medium", "large-v3", "turbo")
SUPPORTED_MEDIA_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".avi",
    ".flac",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
    ".wmv",
}


def transcribe_media_file(
    media_path: str | Path,
    model_size: str = DEFAULT_WHISPER_MODEL,
    progress: ProgressCallback | None = None,
) -> VideoTranscript:
    source = Path(media_path).expanduser().resolve()
    if not source.is_file():
        raise TranscriptError(f"The selected media file does not exist: {source}")
    if source.suffix.casefold() not in SUPPORTED_MEDIA_EXTENSIONS:
        raise TranscriptError(
            f"Unsupported media type '{source.suffix or 'unknown'}'. "
            "Choose a common audio or video file."
        )

    selected_model = model_size.strip() or DEFAULT_WHISPER_MODEL
    _report_progress(progress, f"Loading local speech model {selected_model}...")
    WhisperModel = _whisper_model_class()

    try:
        model = WhisperModel(
            selected_model,
            device=os.environ.get("TUBBY_WHISPER_DEVICE", "cpu"),
            compute_type=os.environ.get("TUBBY_WHISPER_COMPUTE_TYPE", "int8"),
        )
        segments, info = model.transcribe(
            str(source),
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True,
        )
        duration = _optional_float(getattr(info, "duration", None))
        cues = _consume_segments(segments, duration, progress)
    except TranscriptError:
        raise
    except Exception as exc:
        raise TranscriptError(f"Could not transcribe the selected media file: {exc}") from exc

    if not cues:
        raise TranscriptError("No spoken words were detected in the selected media file.")

    language_code = str(getattr(info, "language", "") or "unknown")
    return VideoTranscript(
        title=source.stem or source.name,
        video_id=_media_id(source),
        source_url=str(source),
        language_code=language_code,
        language_name=language_name_for_code(language_code),
        is_auto_generated=True,
        cues=cues,
        duration=int(round(duration)) if duration is not None else None,
        source_kind="local_media",
        transcription_engine=f"faster-whisper {selected_model}",
    )


def download_transcription_model(model_size: str = DEFAULT_WHISPER_MODEL) -> None:
    selected_model = model_size.strip() or DEFAULT_WHISPER_MODEL
    WhisperModel = _whisper_model_class()
    WhisperModel(
        selected_model,
        device=os.environ.get("TUBBY_WHISPER_DEVICE", "cpu"),
        compute_type=os.environ.get("TUBBY_WHISPER_COMPUTE_TYPE", "int8"),
    )


def _consume_segments(
    segments: Any,
    duration: float | None,
    progress: ProgressCallback | None,
) -> tuple[TranscriptCue, ...]:
    cues: list[TranscriptCue] = []
    last_update_second = -1
    for segment in segments:
        text = re.sub(r"\s+", " ", str(getattr(segment, "text", ""))).strip()
        if not text:
            continue

        start = max(0.0, _optional_float(getattr(segment, "start", 0)) or 0.0)
        end = max(start, _optional_float(getattr(segment, "end", start)) or start)
        cues.append(TranscriptCue(start=start, duration=end - start, text=text))

        current_second = int(end)
        if progress is not None and current_second - last_update_second >= 15:
            if duration:
                progress(
                    "Transcribing locally: "
                    f"{format_duration(current_second)} of {format_duration(duration)}"
                )
            else:
                progress(f"Transcribing locally: {format_duration(current_second)} processed")
            last_update_second = current_second
    return tuple(cues)


def _media_id(source: Path) -> str:
    stat = source.stat()
    fingerprint = f"{source}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _report_progress(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _whisper_model_class() -> Any:
    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError as exc:
        raise TranscriptError(
            "Local media transcription is not installed. Run the Tubby setup script again."
        ) from exc
    return WhisperModel
