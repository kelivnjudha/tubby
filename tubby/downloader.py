from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from tubby.utils import format_bytes, format_count, format_duration

DownloadMode = Literal["video", "audio"]
ProgressHook = Callable[[dict[str, Any]], None]

OUTPUT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"
VIDEO_QUALITY_OPTIONS = ("Best", "2160p", "1440p", "1080p", "720p", "480p", "360p")
AUDIO_QUALITY_OPTIONS = ("Best", "320 kbps", "256 kbps", "192 kbps", "128 kbps")


class TubbyError(RuntimeError):
    """Raised when metadata lookup or download fails."""


@dataclass(frozen=True)
class FormatInfo:
    format_id: str | None = None
    ext: str | None = None
    height: int | None = None
    width: int | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize: int | None = None
    tbr: float | None = None
    abr: float | None = None
    fps: float | None = None
    format_note: str | None = None

    @classmethod
    def from_ydl_format(cls, info: dict[str, Any]) -> "FormatInfo":
        return cls(
            format_id=_optional_str(info.get("format_id")),
            ext=_optional_str(info.get("ext")),
            height=_optional_int(info.get("height")),
            width=_optional_int(info.get("width")),
            vcodec=_optional_str(info.get("vcodec")),
            acodec=_optional_str(info.get("acodec")),
            filesize=_format_size(info),
            tbr=_optional_float(info.get("tbr")),
            abr=_optional_float(info.get("abr")),
            fps=_optional_float(info.get("fps")),
            format_note=_optional_str(info.get("format_note")),
        )

    @property
    def has_video(self) -> bool:
        return self.vcodec is not None and self.vcodec != "none"

    @property
    def has_audio(self) -> bool:
        return self.acodec is not None and self.acodec != "none"

    @property
    def is_progressive(self) -> bool:
        return self.has_video and self.has_audio

    @property
    def is_video_only(self) -> bool:
        return self.has_video and not self.has_audio

    @property
    def is_audio_only(self) -> bool:
        return self.has_audio and not self.has_video


@dataclass(frozen=True)
class SelectedDownloadEstimate:
    label: str
    size: int | None = None
    warning: str | None = None


@dataclass(frozen=True)
class VideoInfo:
    title: str
    duration: int | None = None
    uploader: str | None = None
    view_count: int | None = None
    estimated_size: int | None = None
    formats: tuple[FormatInfo, ...] = ()
    upload_date: str | None = None
    webpage_url: str | None = None
    video_id: str | None = None

    @classmethod
    def from_ydl_info(cls, info: dict[str, Any]) -> "VideoInfo":
        return cls(
            title=str(info.get("title") or "Untitled video"),
            duration=_optional_int(info.get("duration")),
            uploader=_optional_str(info.get("uploader") or info.get("channel")),
            view_count=_optional_int(info.get("view_count")),
            estimated_size=_estimated_size(info),
            formats=_formats_from_ydl_info(info),
            upload_date=_normalize_upload_date(info.get("upload_date")),
            webpage_url=_optional_str(info.get("webpage_url") or info.get("original_url")),
            video_id=_optional_str(info.get("id")),
        )

    def summary_lines(
        self,
        mode: DownloadMode = "video",
        quality: str = "Best",
        allow_merge: bool = True,
    ) -> list[str]:
        estimate = estimate_selected_download(self, mode, quality, allow_merge=allow_merge)
        lines = [
            f"Title: {self.title}",
            f"Duration: {format_duration(self.duration)}",
            f"Uploader: {self.uploader or 'Unknown'}",
            f"Views: {format_count(self.view_count)}",
            f"Selected option: {estimate.label}",
            f"Estimated selected size: {format_bytes(estimate.size)}",
        ]
        if estimate.warning:
            lines.append(f"Note: {estimate.warning}")
        lines.append(f"Upload date: {self.upload_date or 'Unknown'}")
        return lines


def fetch_video_info(url: str) -> VideoInfo:
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
    except Exception as exc:  # yt-dlp raises several exception types.
        raise TubbyError(f"Could not fetch video information: {exc}") from exc

    if not isinstance(info, dict):
        raise TubbyError("Could not read video information from this URL.")

    return VideoInfo.from_ydl_info(info)


def download_media(
    url: str,
    output_dir: str | Path,
    mode: DownloadMode,
    quality: str = "Best",
    progress_hook: ProgressHook | None = None,
) -> Path:
    yt_dlp = _yt_dlp()
    target_dir = Path(output_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_available = has_ffmpeg()
    if mode == "audio" and not ffmpeg_available:
        raise TubbyError(
            "FFmpeg is required to convert audio downloads to MP3. "
            "Install FFmpeg and make sure `ffmpeg` is on PATH, or use video mode."
        )
    if mode == "video" and not ffmpeg_available and video_quality_requires_ffmpeg(quality):
        raise TubbyError(
            f"{quality} video with sound requires FFmpeg because high-resolution YouTube "
            "video and audio are separate streams. Install FFmpeg and make sure `ffmpeg` "
            "is on PATH, or choose 720p or lower."
        )

    options = build_ydl_options(
        target_dir,
        mode,
        quality,
        progress_hook,
        allow_merge=ffmpeg_available,
    )

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            result = ydl.extract_info(url, download=True)
    except Exception as exc:
        raise TubbyError(f"Download failed: {exc}") from exc

    return _downloaded_path(result, target_dir)


def build_ydl_options(
    output_dir: str | Path,
    mode: DownloadMode,
    quality: str = "Best",
    progress_hook: ProgressHook | None = None,
    allow_merge: bool = True,
) -> dict[str, Any]:
    target_dir = Path(output_dir).expanduser()
    options: dict[str, Any] = {
        "outtmpl": str(target_dir / OUTPUT_TEMPLATE),
        "noplaylist": True,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
    }

    if progress_hook is not None:
        options["progress_hooks"] = [progress_hook]

    if mode == "video":
        options["format"] = video_format_for_quality(quality, allow_merge=allow_merge)
    elif mode == "audio":
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": audio_preferred_quality(quality),
                    }
                ],
            }
        )
    else:
        raise ValueError(f"Unsupported download mode: {mode}")

    return options


def video_format_for_quality(quality: str, allow_merge: bool = True) -> str:
    normalized = (quality or "Best").strip().lower()
    if normalized in {"best", "auto"}:
        if not allow_merge:
            return "best[vcodec!=none][acodec!=none]/best"
        return "bv*+ba/b"

    if not normalized.endswith("p"):
        raise ValueError(f"Unsupported video quality: {quality}")

    height = _optional_int(normalized[:-1])
    if height is None or height <= 0:
        raise ValueError(f"Unsupported video quality: {quality}")

    if not allow_merge:
        return (
            f"best[height<={height}][vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]/best"
        )

    return f"bv*[height<={height}]+ba/b[height<={height}]"


def audio_preferred_quality(quality: str) -> str:
    normalized = (quality or "Best").strip().lower()
    if normalized in {"best", "auto"}:
        return "0"

    if normalized.endswith("kbps"):
        normalized = normalized.removesuffix("kbps").strip()

    bitrate = _optional_int(normalized)
    if bitrate is None or bitrate <= 0:
        raise ValueError(f"Unsupported audio quality: {quality}")

    return f"{bitrate}K"


def estimate_selected_download(
    info: VideoInfo,
    mode: DownloadMode,
    quality: str,
    allow_merge: bool = True,
) -> SelectedDownloadEstimate:
    if mode == "audio":
        return _estimate_audio_download(info, quality)
    if mode == "video":
        return _estimate_video_download(info, quality, allow_merge=allow_merge)
    raise ValueError(f"Unsupported download mode: {mode}")


def video_quality_requires_ffmpeg(quality: str) -> bool:
    height = _quality_height(quality)
    return height is not None and height > 720


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _yt_dlp() -> Any:
    try:
        import yt_dlp
    except ModuleNotFoundError as exc:
        raise TubbyError("yt-dlp is not installed. Run `pip install -r requirements.txt`.") from exc

    return yt_dlp


def _downloaded_path(result: Any, fallback_dir: Path) -> Path:
    if isinstance(result, dict):
        requested_downloads = result.get("requested_downloads")
        if isinstance(requested_downloads, list):
            for download in reversed(requested_downloads):
                if isinstance(download, dict):
                    path = download.get("filepath") or download.get("filename")
                    if path:
                        return Path(path)

        for key in ("filepath", "_filename", "filename"):
            path = result.get(key)
            if path:
                return Path(path)

    return fallback_dir


def _estimate_video_download(
    info: VideoInfo,
    quality: str,
    allow_merge: bool,
) -> SelectedDownloadEstimate:
    height = _quality_height(quality)
    if allow_merge:
        video = _best_format(info.formats, height=height, kind="video-only")
        audio = _best_format(info.formats, kind="audio-only")
        fallback = _best_format(info.formats, height=height, kind="progressive")

        if video and audio:
            return SelectedDownloadEstimate(
                label=f"{_format_video_label(video)} + {_format_audio_label(audio)}",
                size=_sum_known_sizes(video.filesize, audio.filesize),
            )
        if fallback:
            return SelectedDownloadEstimate(
                label=f"{_format_video_label(fallback)} with audio",
                size=fallback.filesize,
            )
        return SelectedDownloadEstimate("Selected video quality", info.estimated_size)

    progressive = _best_format(info.formats, height=height, kind="progressive")
    if progressive:
        return SelectedDownloadEstimate(
            label=f"{_format_video_label(progressive)} with audio",
            size=progressive.filesize,
            warning=(
                "FFmpeg is not available, so Tubby can only use single-file video streams. "
                "Install FFmpeg for 1080p, 1440p, or 2160p with sound."
            ),
        )

    return SelectedDownloadEstimate(
        label="Single-file video stream",
        size=info.estimated_size,
        warning="FFmpeg is not available, so high-resolution merged video cannot be estimated.",
    )


def _estimate_audio_download(info: VideoInfo, quality: str) -> SelectedDownloadEstimate:
    audio = _best_format(info.formats, kind="audio-only")
    bitrate = _quality_bitrate(quality)
    if bitrate and info.duration:
        estimated_size = int(info.duration * bitrate * 1000 / 8)
    elif audio:
        estimated_size = audio.filesize
    else:
        estimated_size = info.estimated_size

    source = f" from {_format_audio_label(audio)}" if audio else ""
    return SelectedDownloadEstimate(f"MP3 {quality}{source}", estimated_size)


def _best_format(
    formats: tuple[FormatInfo, ...],
    height: int | None = None,
    kind: Literal["video-only", "audio-only", "progressive"] = "progressive",
) -> FormatInfo | None:
    candidates: list[FormatInfo] = []
    for format_info in formats:
        if height is not None and format_info.height is not None and format_info.height > height:
            continue
        if kind == "video-only" and not format_info.is_video_only:
            continue
        if kind == "audio-only" and not format_info.is_audio_only:
            continue
        if kind == "progressive" and not format_info.is_progressive:
            continue
        candidates.append(format_info)

    if not candidates:
        return None

    if kind == "audio-only":
        return max(candidates, key=lambda item: (item.abr or item.tbr or 0, item.filesize or 0))

    return max(
        candidates,
        key=lambda item: (item.height or 0, item.fps or 0, item.tbr or 0, item.filesize or 0),
    )


def _format_video_label(format_info: FormatInfo) -> str:
    resolution = f"{format_info.height}p" if format_info.height else "video"
    fps = f" {int(format_info.fps)}fps" if format_info.fps else ""
    ext = f" {format_info.ext.upper()}" if format_info.ext else ""
    return f"{resolution}{fps}{ext}".strip()


def _format_audio_label(format_info: FormatInfo | None) -> str:
    if format_info is None:
        return "best audio"
    quality = f"{format_info.abr:g} kbps" if format_info.abr else "best audio"
    ext = f" {format_info.ext.upper()}" if format_info.ext else ""
    return f"{quality}{ext}".strip()


def _sum_known_sizes(*sizes: int | None) -> int | None:
    if any(size is None for size in sizes):
        return None
    return sum(size for size in sizes if size is not None)


def _quality_height(quality: str) -> int | None:
    normalized = (quality or "Best").strip().lower()
    if normalized in {"best", "auto"}:
        return None
    if not normalized.endswith("p"):
        return None
    return _optional_int(normalized[:-1])


def _quality_bitrate(quality: str) -> int | None:
    normalized = (quality or "Best").strip().lower()
    if normalized in {"best", "auto"}:
        return None
    if normalized.endswith("kbps"):
        normalized = normalized.removesuffix("kbps").strip()
    return _optional_int(normalized)


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


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _formats_from_ydl_info(info: dict[str, Any]) -> tuple[FormatInfo, ...]:
    formats = info.get("formats")
    if not isinstance(formats, list):
        return ()
    return tuple(FormatInfo.from_ydl_format(item) for item in formats if isinstance(item, dict))


def _estimated_size(info: dict[str, Any]) -> int | None:
    direct_size = _optional_int(info.get("filesize")) or _optional_int(info.get("filesize_approx"))
    if direct_size:
        return direct_size

    requested_formats = info.get("requested_formats")
    if isinstance(requested_formats, list):
        sizes = [_format_size(format_info) for format_info in requested_formats]
        if sizes and all(size is not None for size in sizes):
            return sum(size for size in sizes if size is not None)

    return None


def _format_size(format_info: Any) -> int | None:
    if not isinstance(format_info, dict):
        return None
    return _optional_int(format_info.get("filesize")) or _optional_int(
        format_info.get("filesize_approx")
    )


def _normalize_upload_date(value: Any) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text
