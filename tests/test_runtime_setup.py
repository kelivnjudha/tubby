from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tubby.media_transcript import transcription_model_is_downloaded
from tubby.ollama_models import OllamaModel
from tubby.runtime_setup import (
    RuntimeStatus,
    SetupOptions,
    SetupProgress,
    _pull_ollama_model,
    find_ollama_executable,
    inspect_runtime,
    provision_runtime,
)


class RuntimeInspectionTests(unittest.TestCase):
    def test_windows_ollama_install_location_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            executable = Path(temporary_dir) / "Programs" / "Ollama" / "ollama.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            with (
                patch("tubby.runtime_setup.sys.platform", "win32"),
                patch("tubby.runtime_setup.shutil.which", return_value=None),
                patch.dict(
                    "tubby.runtime_setup.os.environ",
                    {"LOCALAPPDATA": temporary_dir},
                    clear=True,
                ),
            ):
                result = find_ollama_executable()

        self.assertEqual(result, executable.resolve())

    def test_runtime_status_includes_all_local_components(self) -> None:
        model = OllamaModel.inferred("qwen3:4b")
        with (
            patch("tubby.runtime_setup.list_installed_models", return_value=(model,)),
            patch("tubby.runtime_setup.find_ollama_executable", return_value=Path("ollama")),
            patch(
                "tubby.runtime_setup.transcription_model_is_downloaded",
                return_value=True,
            ),
            patch("tubby.runtime_setup.ffmpeg_executable", return_value=Path("ffmpeg")),
        ):
            status = inspect_runtime("small")

        self.assertTrue(status.ollama_running)
        self.assertEqual(status.report_models, (model,))
        self.assertTrue(status.whisper_ready)
        self.assertFalse(status.needs_setup)


class RuntimeProvisioningTests(unittest.TestCase):
    def test_setup_installs_and_starts_ollama_when_missing(self) -> None:
        installed_model = OllamaModel.inferred("qwen3:4b")
        ready_status = RuntimeStatus(
            ollama_executable=Path("ollama"),
            ollama_running=True,
            models=(installed_model,),
            whisper_model="small",
            whisper_ready=True,
            ffmpeg_executable=Path("ffmpeg"),
        )

        with (
            patch("tubby.runtime_setup._ollama_is_ready", return_value=False),
            patch("tubby.runtime_setup.find_ollama_executable", return_value=None),
            patch("tubby.runtime_setup.install_ollama", return_value=Path("ollama")) as install,
            patch("tubby.runtime_setup.start_ollama") as start,
            patch("tubby.runtime_setup._wait_for_ollama") as wait,
            patch(
                "tubby.runtime_setup.list_installed_models",
                return_value=(installed_model,),
            ),
            patch("tubby.runtime_setup.download_transcription_model"),
            patch("tubby.runtime_setup.save_preferred_model"),
            patch("tubby.runtime_setup.inspect_runtime", return_value=ready_status),
        ):
            provision_runtime(SetupOptions())

        install.assert_called_once()
        start.assert_called_once_with(Path("ollama"))
        wait.assert_called_once()

    def test_setup_reuses_an_installed_report_model(self) -> None:
        installed_model = OllamaModel.inferred("qwen3:4b")
        ready_status = RuntimeStatus(
            ollama_executable=Path("ollama"),
            ollama_running=True,
            models=(installed_model,),
            whisper_model="small",
            whisper_ready=True,
            ffmpeg_executable=Path("ffmpeg"),
        )

        with (
            patch("tubby.runtime_setup._ollama_is_ready", return_value=True),
            patch("tubby.runtime_setup.find_ollama_executable", return_value=Path("ollama")),
            patch(
                "tubby.runtime_setup.list_installed_models",
                return_value=(installed_model,),
            ),
            patch("tubby.runtime_setup._pull_ollama_model") as pull_model,
            patch("tubby.runtime_setup.download_transcription_model"),
            patch("tubby.runtime_setup.save_preferred_model"),
            patch("tubby.runtime_setup.inspect_runtime", return_value=ready_status),
        ):
            provision_runtime(SetupOptions())

        pull_model.assert_not_called()

    def test_setup_downloads_only_missing_models(self) -> None:
        installed_model = OllamaModel.inferred("qwen3:4b")
        ready_status = RuntimeStatus(
            ollama_executable=Path("ollama"),
            ollama_running=True,
            models=(installed_model,),
            whisper_model="small",
            whisper_ready=True,
            ffmpeg_executable=Path("ffmpeg"),
        )

        with (
            patch("tubby.runtime_setup._ollama_is_ready", return_value=True),
            patch("tubby.runtime_setup.find_ollama_executable", return_value=Path("ollama")),
            patch(
                "tubby.runtime_setup.list_installed_models",
                side_effect=[(), (installed_model,)],
            ),
            patch("tubby.runtime_setup._pull_ollama_model") as pull_model,
            patch("tubby.runtime_setup.download_transcription_model") as download_speech,
            patch("tubby.runtime_setup.save_preferred_model") as save_model,
            patch("tubby.runtime_setup.inspect_runtime", return_value=ready_status),
        ):
            result = provision_runtime(SetupOptions())

        pull_model.assert_called_once()
        download_speech.assert_called_once_with("small")
        save_model.assert_called_once_with("qwen3:4b")
        self.assertEqual(result.selected_model, "qwen3:4b")

    def test_ollama_pull_stream_reports_progress(self) -> None:
        response = _StreamingResponse(
            b'{"status":"pulling manifest"}\n'
            b'{"status":"downloading","completed":50,"total":100}\n'
            b'{"status":"success"}\n'
        )
        updates: list[SetupProgress] = []

        with patch("tubby.runtime_setup.urlopen", return_value=response):
            _pull_ollama_model(
                "qwen3:4b",
                updates.append,
                base_url="http://127.0.0.1:11434",
            )

        self.assertTrue(any(update.ratio == 0.5 for update in updates))
        self.assertIn("qwen3:4b", updates[-1].message)


class SpeechModelCacheTests(unittest.TestCase):
    def test_speech_model_check_never_downloads_from_network(self) -> None:
        download_model = Mock(return_value="/cached/model")
        with patch(
            "tubby.media_transcript._whisper_download_model",
            return_value=download_model,
        ):
            self.assertTrue(transcription_model_is_downloaded("small"))

        download_model.assert_called_once_with("small", local_files_only=True)

    def test_missing_speech_model_returns_false(self) -> None:
        download_model = Mock(side_effect=OSError("not cached"))
        with patch(
            "tubby.media_transcript._whisper_download_model",
            return_value=download_model,
        ):
            self.assertFalse(transcription_model_is_downloaded("small"))


class _StreamingResponse(io.BytesIO):
    def __enter__(self) -> "_StreamingResponse":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


if __name__ == "__main__":
    unittest.main()
