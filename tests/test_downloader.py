from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tubby.downloader import (
    FormatInfo,
    VideoInfo,
    audio_preferred_quality,
    build_ydl_options,
    estimate_selected_download,
    video_format_for_quality,
    video_quality_requires_ffmpeg,
)
from tubby.utils import format_bytes, format_download_status, format_duration, format_eta


class UtilsTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(65), "1:05")
        self.assertEqual(format_duration(3661), "1:01:01")
        self.assertEqual(format_duration(None), "Unknown")

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1024 * 1024), "1.0 MB")

    def test_format_eta(self) -> None:
        self.assertEqual(format_eta(125), "2:05")
        self.assertEqual(format_eta(None), "Unknown")

    def test_format_download_status(self) -> None:
        ratio, text = format_download_status(512, 1024, 256, 2)

        self.assertEqual(ratio, 0.5)
        self.assertIn("50.0%", text)
        self.assertIn("1.0 KB file size", text)
        self.assertIn("0:02 left", text)


class DownloaderOptionTests(unittest.TestCase):
    def test_video_quality_selector_best(self) -> None:
        selector = video_format_for_quality("Best")
        self.assertEqual(selector, "bv*+ba/b")

    def test_video_quality_selector_height_cap(self) -> None:
        selector = video_format_for_quality("720p")
        self.assertIn("height<=720", selector)

    def test_video_quality_selector_without_ffmpeg_uses_single_file(self) -> None:
        selector = video_format_for_quality("720p", allow_merge=False)

        self.assertIn("best[height<=720]", selector)
        self.assertNotIn("+ba", selector)

    def test_build_audio_options_adds_mp3_postprocessor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ffmpeg_path = Path(temp_dir) / "ffmpeg"
            options = build_ydl_options(
                Path(temp_dir),
                "audio",
                ffmpeg_location=ffmpeg_path,
            )

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["preferredcodec"], "mp3")
        self.assertEqual(options["postprocessors"][0]["preferredquality"], "0")
        self.assertEqual(options["ffmpeg_location"], str(ffmpeg_path))

    def test_audio_preferred_quality_accepts_bitrate(self) -> None:
        self.assertEqual(audio_preferred_quality("320 kbps"), "320K")

    def test_build_video_options_adds_progress_hook(self) -> None:
        def hook(_: dict[str, object]) -> None:
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            options = build_ydl_options(temp_dir, "video", "1080p", hook)

        self.assertEqual(options["progress_hooks"], [hook])
        self.assertEqual(options["format"], "bv*[height<=1080]+ba/b[height<=1080]")

    def test_build_video_options_without_ffmpeg_disables_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            options = build_ydl_options(temp_dir, "video", "1080p", allow_merge=False)

        self.assertNotIn("+ba", options["format"])

    def test_high_video_qualities_require_ffmpeg(self) -> None:
        self.assertTrue(video_quality_requires_ffmpeg("2160p"))
        self.assertFalse(video_quality_requires_ffmpeg("720p"))

    def test_estimate_selected_video_download_changes_with_quality(self) -> None:
        info = VideoInfo(
            title="Example",
            duration=60,
            formats=(
                FormatInfo(ext="mp4", height=360, vcodec="avc1", acodec="mp4a", filesize=100),
                FormatInfo(ext="webm", height=2160, vcodec="vp9", acodec="none", filesize=1000),
                FormatInfo(ext="mp4", height=720, vcodec="avc1", acodec="none", filesize=400),
                FormatInfo(ext="webm", acodec="opus", vcodec="none", abr=160, filesize=80),
            ),
        )

        high = estimate_selected_download(info, "video", "2160p", allow_merge=True)
        low = estimate_selected_download(info, "video", "720p", allow_merge=True)

        self.assertEqual(high.size, 1080)
        self.assertEqual(low.size, 480)

    def test_estimate_audio_download_uses_selected_bitrate(self) -> None:
        info = VideoInfo(title="Example", duration=60)
        estimate = estimate_selected_download(info, "audio", "320 kbps")

        self.assertEqual(estimate.size, 2_400_000)


class VideoInfoTests(unittest.TestCase):
    def test_from_ydl_info_normalizes_values(self) -> None:
        info = VideoInfo.from_ydl_info(
            {
                "title": "Example",
                "duration": "90",
                "uploader": "Creator",
                "view_count": "1200",
                "filesize_approx": "4096",
                "upload_date": "20260512",
                "webpage_url": "https://example.test/watch",
                "id": "abc123",
            }
        )

        self.assertEqual(info.title, "Example")
        self.assertEqual(info.duration, 90)
        self.assertEqual(info.view_count, 1200)
        self.assertEqual(info.estimated_size, 4096)
        self.assertEqual(info.upload_date, "2026-05-12")


if __name__ == "__main__":
    unittest.main()
