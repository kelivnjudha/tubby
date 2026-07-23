from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfReader

from tubby.languages import LANGUAGE_OPTIONS, language_code_for, language_name_for_code
from tubby.local_ai import (
    DEFAULT_OLLAMA_URL,
    AnalysisReport,
    OllamaClient,
    OllamaError,
    ReportChapter,
    analyze_transcript,
    chunk_transcript,
)
from tubby.media_transcript import transcribe_media_file
from tubby.pdf_report import PdfReportError, create_pdf_report
from tubby.report_styles import DEFAULT_REPORT_STYLE, get_report_style
from tubby.transcript import (
    TranscriptCue,
    VideoTranscript,
    _select_caption_track,
    parse_json3_transcript,
    parse_ttml_transcript,
    parse_webvtt_transcript,
)
from tubby.workflow import analyze_media_to_pdf, analyze_youtube_to_pdf


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
                "report_title": "  Better   Notes ",
                "subtitle": " Useful source ",
                "executive_summary": "  Clear   summary ",
                "introduction": "First paragraph.\n\n Second paragraph.",
                "chapters": [
                    {
                        "title": " Chapter One ",
                        "body": " Detailed   body. ",
                        "key_takeaways": [" Keep this "],
                    }
                ],
                "key_points": [" One ", "", "Two"],
                "important_details": [],
                "decisions_and_actions": ["Act"],
                "questions_and_caveats": None,
                "conclusion": " Closing thought. ",
            }
        )

        self.assertEqual(report.report_title, "Better Notes")
        self.assertEqual(report.executive_summary, "Clear summary")
        self.assertEqual(report.introduction, "First paragraph.\n\nSecond paragraph.")
        self.assertEqual(report.chapters[0].title, "Chapter One")
        self.assertEqual(report.chapters[0].key_takeaways, ("Keep this",))
        self.assertEqual(report.key_points, ("One", "Two"))
        self.assertEqual(report.decisions_and_actions, ("Act",))

    def test_report_style_aliases(self) -> None:
        self.assertEqual(get_report_style("concise").label, "Short")
        self.assertEqual(get_report_style("detailed").label, "Fully detailed")

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

    @patch("tubby.local_ai.urlopen")
    def test_ollama_client_retries_truncated_json(self, mocked_urlopen: object) -> None:
        invalid = {
            "message": {"role": "assistant", "content": '{"executive_summary": "cut'},
            "done_reason": "length",
        }
        valid = {
            "message": {
                "role": "assistant",
                "content": json.dumps({"executive_summary": "Recovered"}),
            },
            "done_reason": "stop",
        }
        mocked_urlopen.side_effect = [
            _FakeResponse(json.dumps(invalid).encode("utf-8")),
            _FakeResponse(json.dumps(valid).encode("utf-8")),
        ]

        result = OllamaClient(model="gemma4").chat_json("System", "User")

        self.assertEqual(result["executive_summary"], "Recovered")
        retry_request = mocked_urlopen.call_args_list[1].args[0]
        retry_payload = json.loads(retry_request.data.decode("utf-8"))
        self.assertEqual(retry_payload["options"]["temperature"], 0)
        self.assertEqual(retry_payload["options"]["num_predict"], 8192)

    @patch("tubby.local_ai.OllamaClient.chat_json")
    def test_analysis_falls_back_to_extracted_evidence(
        self,
        mocked_chat: object,
    ) -> None:
        extraction = {
            "executive_summary": "Extracted summary",
            "key_points": ["One supported point"],
            "important_details": ["The value is 42"],
            "decisions_and_actions": [],
            "questions_and_caveats": ["One caveat"],
            "chronology": ["At 0:00 the value was introduced."],
            "topic_sections": [
                {"title": "Supported topic", "evidence": "Evidence-backed chapter body."}
            ],
        }
        mocked_chat.side_effect = [extraction, OllamaError("invalid final JSON")]
        transcript = VideoTranscript(
            title="Fallback source",
            video_id="fallback",
            source_url="local.wav",
            language_code="en",
            language_name="English",
            is_auto_generated=True,
            cues=(TranscriptCue(0, "Source text"),),
            source_kind="local_media",
            transcription_engine="faster-whisper small",
        )

        report = analyze_transcript(transcript, model="gemma4")

        self.assertEqual(report.executive_summary, "Extracted summary")
        self.assertEqual(report.chapters[0].title, "Supported topic")
        self.assertEqual(report.chapters[1].title, "Chronology")
        self.assertIn("0:00", report.chapters[1].body)
        self.assertEqual(report.important_details, ("The value is 42",))


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
            report_title="Video Intelligence Report",
            introduction="This introduces the source.",
            chapters=(
                ReportChapter(
                    title="A useful chapter",
                    body="The chapter explains the source material.",
                    key_takeaways=("Keep the evidence visible.",),
                ),
            ),
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
        self.assertIn("A useful chapter", extracted)
        self.assertIn("The chapter explains the source material.", extracted)
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
        self.assertEqual(language_name_for_code("th"), "Thai")
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
            report_style=DEFAULT_REPORT_STYLE,
            progress=None,
        )
        mocked_pdf.assert_called_once_with(
            transcript,
            analysis,
            output_dir="output",
            output_language="Thai",
            model="gemma4:e2b",
            report_style=DEFAULT_REPORT_STYLE,
            progress=None,
        )
        self.assertEqual(result.pdf_path, expected_path)

    @patch("tubby.workflow.create_pdf_report")
    @patch("tubby.workflow.analyze_transcript")
    @patch("tubby.workflow.transcribe_media_file")
    def test_media_workflow_transcribes_then_builds_selected_edition(
        self,
        mocked_transcribe: object,
        mocked_analyze: object,
        mocked_pdf: object,
    ) -> None:
        transcript = VideoTranscript(
            title="Local recording",
            video_id="media-id",
            source_url="recording.mp3",
            language_code="en",
            language_name="English",
            is_auto_generated=True,
            cues=(TranscriptCue(0, "Local speech"),),
            source_kind="local_media",
            transcription_engine="faster-whisper small",
        )
        analysis = AnalysisReport(executive_summary="Summary")
        mocked_transcribe.return_value = transcript
        mocked_analyze.return_value = analysis
        mocked_pdf.return_value = Path("local.pdf")

        result = analyze_media_to_pdf(
            media_path="recording.mp3",
            output_dir="output",
            report_style="Story",
            whisper_model="medium",
        )

        mocked_transcribe.assert_called_once_with(
            "recording.mp3",
            model_size="medium",
            progress=None,
        )
        mocked_analyze.assert_called_once_with(
            transcript,
            output_language="English",
            model="gemma4",
            base_url=DEFAULT_OLLAMA_URL,
            report_style="Story",
            progress=None,
        )
        mocked_pdf.assert_called_once_with(
            transcript,
            analysis,
            output_dir="output",
            output_language="English",
            model="gemma4",
            report_style="Story",
            progress=None,
        )
        self.assertEqual(result.pdf_path, Path("local.pdf"))


class MediaTranscriptionTests(unittest.TestCase):
    @patch("tubby.media_transcript._whisper_model_class")
    def test_local_media_transcription_builds_timestamped_source(
        self,
        mocked_model_class: object,
    ) -> None:
        class FakeWhisperModel:
            def __init__(self, *_: object, **__: object) -> None:
                return None

            def transcribe(self, *_: object, **__: object) -> tuple[list[object], object]:
                segments = [
                    SimpleNamespace(start=0.0, end=2.5, text=" Hello world "),
                    SimpleNamespace(start=16.0, end=18.0, text="Second point"),
                ]
                return segments, SimpleNamespace(duration=20.0, language="en")

        mocked_model_class.return_value = FakeWhisperModel
        progress: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            media_path = Path(temp_dir) / "meeting.mp3"
            media_path.write_bytes(b"test")
            transcript = transcribe_media_file(media_path, progress=progress.append)

        self.assertEqual(transcript.title, "meeting")
        self.assertEqual(transcript.source_kind, "local_media")
        self.assertEqual(transcript.language_name, "English")
        self.assertEqual(transcript.cues[1].timestamp, "0:16")
        self.assertIn("faster-whisper small", transcript.transcript_source_label)
        self.assertTrue(any("Transcribing locally" in message for message in progress))


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
