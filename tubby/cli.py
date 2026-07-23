from __future__ import annotations

import argparse
from pathlib import Path

from tubby.downloader import (
    AUDIO_QUALITY_OPTIONS,
    VIDEO_QUALITY_OPTIONS,
    TubbyError,
    download_media,
    fetch_video_info,
    has_ffmpeg,
)
from tubby.utils import format_download_status


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    url = args.url_option or args.url

    if not url:
        parser.error("a URL is required")

    try:
        quality = args.audio_quality if args.mode == "audio" else args.quality
        if args.info:
            info = fetch_video_info(url)
            print(
                "\n".join(
                    info.summary_lines(
                        mode=args.mode,
                        quality=quality,
                        allow_merge=has_ffmpeg(),
                    )
                )
            )
            return 0

        output = Path(args.output).expanduser()
        path = download_media(
            url=url,
            output_dir=output,
            mode=args.mode,
            quality=quality,
            progress_hook=_progress_hook,
        )
    except TubbyError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"\nSaved to: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download any video from almost every URL.")
    parser.add_argument("url", nargs="?", help="video URL to download")
    parser.add_argument("-u", "--url", dest="url_option", help="video URL to download")
    parser.add_argument(
        "-m",
        "--mode",
        choices=("video", "audio"),
        default="video",
        help="download mode (default: video)",
    )
    parser.add_argument(
        "-q",
        "--quality",
        choices=VIDEO_QUALITY_OPTIONS,
        default="Best",
        help="video quality cap (video mode only)",
    )
    parser.add_argument(
        "--audio-quality",
        choices=AUDIO_QUALITY_OPTIONS,
        default="Best",
        help="MP3 conversion quality (audio mode only)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(Path.home() / "Downloads"),
        help="directory for downloaded files",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="show video information without downloading",
    )
    return parser


def _progress_hook(event: dict[str, object]) -> None:
    status = event.get("status")
    if status == "downloading":
        downloaded = _number(event.get("downloaded_bytes")) or 0
        total = _number(event.get("total_bytes")) or _number(event.get("total_bytes_estimate"))
        speed = _number(event.get("speed"))
        eta = _number(event.get("eta"))
        _, progress = format_download_status(downloaded, total, speed, eta)

        print(f"\r{progress}", end="", flush=True)
    elif status == "finished":
        print("\rProcessing download...".ljust(80), end="", flush=True)


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
