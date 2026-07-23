from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from tubby.languages import LANGUAGE_OPTIONS, language_code_for
from tubby.local_ai import (
    DEFAULT_OLLAMA_URL,
    AnalysisReport,
    OllamaClient,
    chunk_transcript,
)
from tubby.pdf_report import PdfReportError, create_pdf_report
from tubby.transcript import (
    TranscriptCue,
    VideoTranscript,
    _select_caption_track,
    parse_json3_transcript,
    parse_ttml_transcript,
    parse_webvtt_transcript,
)
from tubby.workflow import analyze_youtube_to_pdf


class TranscriptParsingTests(unittest.TestCase):
    def test_json3_parser_builds_timestamped_cues(self) -> None:
        content = json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 1000,
                        "dDurationMs": 2000,
                        "segs": [{"utf8": "Hello "}, {"utf8": "world"}],
                    },
                    {
                        "tStartMs": 3000,
                        "dDurationMs": 1000,
                        "segs": [{"utf8": "Next point"}],
                    },
                ]
            }
        )

        cues = parse_json3_transcript(content)

        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].timestamp, "0:01")
        self.assertEqual(cues[0].text, "Hello world")
        self.assertEqual(cues[1].duration, 1)

    def test_webvtt_parser_removes_rolling_caption_overlap(self) -> None:
        content = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello world

00:00:03.000 --> 00:00:05.000
Hello world next point
"""

        cues = parse_webvtt_transcript(content)

        self.assertEqual([cue.text for cue in cues], ["Hello world", "next point"])

    def test_ttml_parser_reads_paragraph_timing(self) -> None:
        content = """<?xml version="1.0" encoding="utf-8"?>
<tt xmlns="http://www.w3.org/ns/ttml">
  <body><div><p begin="1.5s" end="3.0s">A stated fact</p></div></body>
</tt>
"""

        cues = parse_ttml_transcript(content)

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].start, 1.5)
        self.assertEqual(cues[0].duration, 1.5)
        self.assertEqual(cues[0].text, "A stated fact")

    def test_caption_selection_prefers_manual_requested_language(self) -> None:
        info = {
            "subtitles": {
                "en": [{"ext": "json3", "url": "https://example.test/en"}],
                "th": [{"ext": "json3", "url": "https://example.test/th"}],
            },
            "automatic_captions": {
                "th": [{"ext": "json3", "url": "https://example.test/auto-th"}],
            },
        }

        language, formats, is_auto = _select_caption_track(info, "th")

        self.assertEqual(language, "th")
        self.assertEqual(formats[0]["url"], "https://example.test/th")
        self.assertFalse(is_auto)

    def test_caption_selection_uses_automatic_requested_before_manual_fallback(self) -> None:
        info = {
            "subtitles": {
                "fr": [{"ext": "json3", "url": "https://example.test/fr"}],
            },
            "automatic_captions": {
                "th": [{"ext": "json3", "url": "https://example.test/auto-th"}],
            },
        }

        language, _, is_auto = _select_caption_track(info, "th")

        self.assertEqual(language, "th")
        self.assertTrue(is_auto)


class LocalAiTests(unittest.TestCase):
    def test_chunk_transcript_preserves_all_lines(self) -> None:
        transcript = "\n".join(f"[0:{index:02d}] {'x' * 300}" for index in range(10))

        chunks = chunk_transcript(transcript, max_characters=1000)

        self.assertGreater(len(chunks), 1)
        self.assertEqual("\n".join(chunks), transcript)

    def test_analysis_report_cleans_model_values(self) -> None:
        report = AnalysisReport.from_mapping(
            {
                "executive_summary": "  Clear   summary ",
                "key_points": [" One ", "", "Two"],
                "important_details": [],
                "decisions_and_actions": ["Act"],
                "questions_and_caveats": None,
            }
        )

        self.assertEqual(report.executive_summary, "Clear summary")
        self.assertEqual(report.key_points, ("One", "Two"))
        self.assertEqual(report.decisions_and_actions, ("Act",))

    @patch("tubby.local_ai.urlopen")
    def test_ollama_client_reads_structured_chat_response(self, mocked_urlopen: object) -> None:
        response_payload = {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "executive_summary": "Summary",
                        "key_points": ["Point"],
                        "important_details": [],
                        "decisions_and_actions": [],
                        "questions_and_caveats": [],
                    }
                ),
            }
        }
        mocked_urlopen.return_value = _FakeResponse(json.dumps(response_payload).encode("utf-8"))

        result = OllamaClient(model="gemma4").chat_json("System", "User")

        self.assertEqual(result["executive_summary"], "Summary")
        request = mocked_urlopen.call_args.args[0]
        sent_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent_payload["model"], "gemma4")
        self.assertFalse(sent_payload["stream"])
        self.assertFalse(sent_payload["think"])
        self.assertEqual(sent_payload["options"]["num_ctx"], 32768)
        self.assertEqual(sent_payload["options"]["num_predict"], 4096)


class PdfReportTests(unittest.TestCase):
    def test_pdf_contains_analysis_and_transcript(self) -> None:
        transcript = VideoTranscript(
            title="Example Video",
            video_id="abc123",
            source_url="https://www.youtube.com/watch?v=abc123",
            language_code="en",
            language_name="English",
            is_auto_generated=False,
            cues=(
                TranscriptCue(0, "The first source statement."),
                TranscriptCue(65, "The second source statement."),
            ),
            uploader="Example Creator",
            duration=125,
        )
        analysis = AnalysisReport(
            executive_summary="A concise evidence-based summary.",
            key_points=("The first important point.",),
            important_details=("The value is 42.",),
            decisions_and_actions=("Review the source.",),
            questions_and_caveats=("No supporting example was provided.",),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = create_pdf_report(
                transcript,
                analysis,
                output_dir=temp_dir,
                output_language="English",
                model="gemma4",
            )
            reader = PdfReader(report_path)
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            temporary_files = list(Path(temp_dir).glob(".tubby-report-*.pdf"))

        self.assertIn("Video Intelligence Report", extracted)
        self.assertIn("A concise evidence-based summary.", extracted)
        self.assertIn("Source Transcript", extracted)
        self.assertIn("The second source statement.", extracted)
        self.assertEqual(temporary_files, [])

    def test_pdf_rejects_unsupported_right_to_left_output(self) -> None:
        transcript = VideoTranscript(
            title="Example",
            video_id="abc123",
            source_url="https://www.youtube.com/watch?v=abc123",
            language_code="en",
            language_name="English",
            is_auto_generated=False,
            cues=(TranscriptCue(0, "Example transcript."),),
        )
        analysis = AnalysisReport(executive_summary="Arabic summary placeholder.")

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(PdfReportError, "Right-to-left"):
                create_pdf_report(
                    transcript,
                    analysis,
                    output_dir=temp_dir,
                    output_language="Arabic",
                    model="gemma4",
                )


class WorkflowTests(unittest.TestCase):
    def test_language_code_defaults_to_english(self) -> None:
        self.assertEqual(language_code_for("English"), "en")
        self.assertEqual(language_code_for("Custom language"), "en")
        self.assertNotIn("Arabic", LANGUAGE_OPTIONS)

    @patch("tubby.workflow.create_pdf_report")
    @patch("tubby.workflow.analyze_transcript")
    @patch("tubby.workflow.fetch_youtube_transcript")
    def test_workflow_passes_language_model_and_result(
        self,
        mocked_fetch: object,
        mocked_analyze: object,
        mocked_pdf: object,
    ) -> None:
        transcript = VideoTranscript(
            title="Example",
            video_id="video-id",
            source_url="https://www.youtube.com/watch?v=video-id",
            language_code="th",
            language_name="Thai",
            is_auto_generated=True,
            cues=(TranscriptCue(0, "Example transcript"),),
        )
        analysis = AnalysisReport(executive_summary="Summary")
        expected_path = Path("report.pdf")
        mocked_fetch.return_value = transcript
        mocked_analyze.return_value = analysis
        mocked_pdf.return_value = expected_path

        result = analyze_youtube_to_pdf(
            url=transcript.source_url,
            output_dir="output",
            output_language="Thai",
            model="gemma4:e2b",
        )

        mocked_fetch.assert_called_once_with(
            transcript.source_url,
            preferred_language_code="th",
        )
        mocked_analyze.assert_called_once_with(
            transcript,
            output_language="Thai",
            model="gemma4:e2b",
            base_url=DEFAULT_OLLAMA_URL,
            progress=None,
        )
        mocked_pdf.assert_called_once_with(
            transcript,
            analysis,
            output_dir="output",
            output_language="Thai",
            model="gemma4:e2b",
            progress=None,
        )
        self.assertEqual(result.pdf_path, expected_path)


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.data


if __name__ == "__main__":
    unittest.main()
