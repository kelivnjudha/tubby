from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


class TranscriptError(RuntimeError):
    """Raised when a usable transcript cannot be retrieved."""


@dataclass(frozen=True)
class TranscriptCue:
    start: float
    text: str
    duration: float | None = None

    @property
    def timestamp(self) -> str:
        total_seconds = max(0, int(self.start))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass(frozen=True)
class VideoTranscript:
    title: str
    video_id: str
    source_url: str
    language_code: str
    language_name: str
    is_auto_generated: bool
    cues: tuple[TranscriptCue, ...]
    uploader: str | None = None
    duration: int | None = None
    source_kind: str = "youtube"
    transcription_engine: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(f"[{cue.timestamp}] {cue.text}" for cue in self.cues)

    @property
    def source_type_label(self) -> str:
        return "Local media file" if self.source_kind == "local_media" else "YouTube"

    @property
    def transcript_source_label(self) -> str:
        if self.transcription_engine:
            return f"Local speech recognition - {self.transcription_engine}"
        if self.is_auto_generated:
            return f"Automatic captions - {self.language_name}"
        return f"Manual captions - {self.language_name}"


def fetch_youtube_transcript(
    url: str,
    preferred_language_code: str = "en",
) -> VideoTranscript:
    """Fetch manual or automatically generated captions through yt-dlp."""
    if not url.strip():
        raise TranscriptError("Enter a YouTube URL first.")

    yt_dlp = _yt_dlp()
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict):
                raise TranscriptError("YouTube did not return video information for this URL.")

            language_code, formats, is_auto_generated = _select_caption_track(
                info,
                preferred_language_code,
            )
            caption_format = _select_caption_format(formats)
            caption_url = caption_format.get("url")
            if not caption_url:
                raise TranscriptError("The selected YouTube caption track has no download URL.")

            response = ydl.urlopen(caption_url)
            try:
                raw_captions = response.read()
            finally:
                response.close()
    except TranscriptError:
        raise
    except Exception as exc:  # yt-dlp uses several extractor and network exceptions.
        raise TranscriptError(f"Could not retrieve the YouTube transcript: {exc}") from exc

    caption_text = raw_captions.decode("utf-8", errors="replace")
    extension = str(caption_format.get("ext") or "").casefold()
    cues = _parse_caption_data(caption_text, extension)
    if not cues:
        raise TranscriptError("YouTube returned an empty caption track for this video.")

    language_name = _caption_language_name(formats, language_code)
    return VideoTranscript(
        title=str(info.get("title") or "Untitled YouTube video"),
        video_id=str(info.get("id") or "unknown"),
        source_url=str(info.get("webpage_url") or info.get("original_url") or url),
        language_code=language_code,
        language_name=language_name,
        is_auto_generated=is_auto_generated,
        cues=cues,
        uploader=_optional_text(info.get("uploader") or info.get("channel")),
        duration=_optional_int(info.get("duration")),
    )


def parse_json3_transcript(content: str) -> tuple[TranscriptCue, ...]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranscriptError("YouTube returned malformed JSON captions.") from exc

    events = payload.get("events")
    if not isinstance(events, list):
        return ()

    cues: list[TranscriptCue] = []
    previous_text = ""
    for event in events:
        if not isinstance(event, dict):
            continue
        segments = event.get("segs")
        if not isinstance(segments, list):
            continue
        source_text = "".join(
            str(segment.get("utf8") or "") for segment in segments if isinstance(segment, dict)
        )
        source_text = _clean_caption_text(source_text)
        text = _remove_repeated_text(previous_text, source_text)
        if not text:
            continue

        start_ms = _optional_float(event.get("tStartMs")) or 0.0
        duration_ms = _optional_float(event.get("dDurationMs"))
        cues.append(
            TranscriptCue(
                start=start_ms / 1000,
                duration=duration_ms / 1000 if duration_ms is not None else None,
                text=text,
            )
        )
        previous_text = source_text

    return tuple(cues)


def parse_webvtt_transcript(content: str) -> tuple[TranscriptCue, ...]:
    cues: list[TranscriptCue] = []
    previous_text = ""
    blocks = re.split(r"\r?\n\s*\r?\n", content)
    for block in blocks:
        lines = [line.strip() for line in block.splitlines()]
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timing_index is None:
            continue

        timing_match = _VTT_TIMING_RE.search(lines[timing_index])
        if timing_match is None:
            continue

        source_text = _clean_caption_text(" ".join(lines[timing_index + 1 :]))
        text = _remove_repeated_text(previous_text, source_text)
        if not text:
            continue

        start = _parse_timestamp(timing_match.group("start"))
        end = _parse_timestamp(timing_match.group("end"))
        cues.append(TranscriptCue(start=start, duration=max(0.0, end - start), text=text))
        previous_text = source_text

    return tuple(cues)


def parse_ttml_transcript(content: str) -> tuple[TranscriptCue, ...]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise TranscriptError("YouTube returned malformed XML captions.") from exc

    cues: list[TranscriptCue] = []
    previous_text = ""
    for node in root.iter():
        if not node.tag.casefold().endswith("p"):
            continue
        source_text = _clean_caption_text("".join(node.itertext()))
        text = _remove_repeated_text(previous_text, source_text)
        if not text:
            continue

        start = _parse_timestamp(node.attrib.get("begin", "0"))
        end_value = node.attrib.get("end")
        duration_value = node.attrib.get("dur")
        duration: float | None = None
        if end_value:
            duration = max(0.0, _parse_timestamp(end_value) - start)
        elif duration_value:
            duration = _parse_timestamp(duration_value)

        cues.append(TranscriptCue(start=start, duration=duration, text=text))
        previous_text = source_text

    return tuple(cues)


def _select_caption_track(
    info: dict[str, Any],
    preferred_language_code: str,
) -> tuple[str, list[dict[str, Any]], bool]:
    manual = _caption_dictionary(info.get("subtitles"))
    automatic = _caption_dictionary(info.get("automatic_captions"))

    for captions, is_auto in ((manual, False), (automatic, True)):
        selected = _find_language(captions, preferred_language_code)
        if selected is not None:
            return selected, captions[selected], is_auto

    for fallback_code in ("en", str(info.get("language") or "")):
        if not fallback_code:
            continue
        for captions, is_auto in ((manual, False), (automatic, True)):
            selected = _find_language(captions, fallback_code)
            if selected is not None:
                return selected, captions[selected], is_auto

    for captions, is_auto in ((manual, False), (automatic, True)):
        for language_code, formats in captions.items():
            if language_code.casefold() != "live_chat":
                return language_code, formats, is_auto

    raise TranscriptError(
        "No captions are available for this video. Tubby currently requires manual "
        "subtitles or YouTube automatic captions."
    )


def _caption_dictionary(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(language): [item for item in formats if isinstance(item, dict)]
        for language, formats in value.items()
        if isinstance(formats, list) and formats
    }


def _find_language(
    captions: dict[str, list[dict[str, Any]]],
    requested_code: str,
) -> str | None:
    requested = requested_code.strip().casefold().replace("_", "-")
    if not requested:
        return None

    normalized = {
        language.casefold().replace("_", "-"): language
        for language in captions
        if language.casefold() != "live_chat"
    }
    if requested in normalized:
        return normalized[requested]

    base = requested.split("-", 1)[0]
    if base in normalized:
        return normalized[base]

    for normalized_code, original_code in normalized.items():
        if normalized_code.startswith(f"{requested}-"):
            return original_code
    for normalized_code, original_code in normalized.items():
        if normalized_code.startswith(f"{base}-"):
            return original_code
    return None


def _select_caption_format(formats: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in formats if item.get("url")]
    for extension in ("json3", "vtt", "srv3", "ttml"):
        for item in available:
            if str(item.get("ext") or "").casefold() == extension:
                return item
    if available:
        return available[0]
    raise TranscriptError("YouTube did not provide a downloadable caption format.")


def _caption_language_name(formats: list[dict[str, Any]], fallback: str) -> str:
    for item in formats:
        name = item.get("name")
        if name:
            return str(name)
    return fallback


def _parse_caption_data(content: str, extension: str) -> tuple[TranscriptCue, ...]:
    if extension == "json3":
        return parse_json3_transcript(content)
    if extension == "vtt":
        return parse_webvtt_transcript(content)
    if extension in {"srv3", "ttml", "xml"}:
        return parse_ttml_transcript(content)

    stripped = content.lstrip()
    if stripped.startswith("{"):
        return parse_json3_transcript(content)
    if stripped.startswith("<"):
        return parse_ttml_transcript(content)
    return parse_webvtt_transcript(content)


def _clean_caption_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def _remove_repeated_text(previous: str, current: str) -> str:
    if not current or current == previous:
        return ""
    if not previous:
        return current

    previous_words = previous.split()
    current_words = current.split()
    max_overlap = min(len(previous_words), len(current_words))
    for size in range(max_overlap, 0, -1):
        if previous_words[-size:] == current_words[:size]:
            return " ".join(current_words[size:]).strip()
    return current


def _parse_timestamp(value: str) -> float:
    text = value.strip().replace(",", ".")
    if text.endswith("ms"):
        return (_optional_float(text[:-2]) or 0.0) / 1000
    if text.endswith("s"):
        return _optional_float(text[:-1]) or 0.0

    parts = text.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _yt_dlp() -> Any:
    try:
        import yt_dlp
    except ModuleNotFoundError as exc:
        raise TranscriptError(
            "yt-dlp is not installed. Run the Tubby setup script and try again."
        ) from exc
    return yt_dlp


_VTT_TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})"
)
