from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tubby.downloader import ffmpeg_executable
from tubby.media_transcript import (
    DEFAULT_WHISPER_MODEL,
    download_transcription_model,
    transcription_model_is_downloaded,
)
from tubby.ollama_models import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    OllamaModel,
    find_installed_model,
    list_installed_models,
    ordered_report_models,
    save_preferred_model,
)

WINDOWS_INSTALL_SCRIPT_URL = "https://ollama.com/install.ps1"
MACOS_DOWNLOAD_URL = "https://ollama.com/download/Ollama-darwin.zip"
DOWNLOAD_USER_AGENT = "Tubby setup"


class SetupError(RuntimeError):
    """Raised when Tubby cannot prepare a required local dependency."""


@dataclass(frozen=True)
class SetupProgress:
    message: str
    ratio: float | None = None


@dataclass(frozen=True)
class RuntimeStatus:
    ollama_executable: Path | None
    ollama_running: bool
    models: tuple[OllamaModel, ...]
    whisper_model: str
    whisper_ready: bool
    ffmpeg_executable: Path | None

    @property
    def report_models(self) -> tuple[OllamaModel, ...]:
        return ordered_report_models(self.models)

    @property
    def needs_setup(self) -> bool:
        return not self.ollama_running or not self.report_models or not self.whisper_ready


@dataclass(frozen=True)
class SetupOptions:
    report_model: str = DEFAULT_MODEL
    whisper_model: str = DEFAULT_WHISPER_MODEL
    prepare_speech_model: bool = True


@dataclass(frozen=True)
class SetupResult:
    status: RuntimeStatus
    selected_model: str


ProgressCallback = Callable[[SetupProgress], None]


def inspect_runtime(
    whisper_model: str = DEFAULT_WHISPER_MODEL,
    *,
    base_url: str = DEFAULT_OLLAMA_URL,
) -> RuntimeStatus:
    models: tuple[OllamaModel, ...] = ()
    ollama_running = False
    try:
        models = list_installed_models(base_url=base_url, timeout=1.5)
        ollama_running = True
    except Exception:
        pass

    return RuntimeStatus(
        ollama_executable=find_ollama_executable(),
        ollama_running=ollama_running,
        models=models,
        whisper_model=whisper_model,
        whisper_ready=transcription_model_is_downloaded(whisper_model),
        ffmpeg_executable=ffmpeg_executable(),
    )


def provision_runtime(
    options: SetupOptions,
    progress: ProgressCallback | None = None,
    *,
    base_url: str = DEFAULT_OLLAMA_URL,
) -> SetupResult:
    report_model = options.report_model.strip() or DEFAULT_MODEL
    whisper_model = options.whisper_model.strip() or DEFAULT_WHISPER_MODEL

    _report(progress, "Checking local components...")
    executable = find_ollama_executable()
    ollama_running = _ollama_is_ready(base_url)

    if not ollama_running and executable is None:
        _report(progress, "Installing Ollama...")
        executable = install_ollama(progress)

    if not ollama_running:
        _report(progress, "Starting Ollama...")
        start_ollama(executable)
        _wait_for_ollama(base_url)

    _report(progress, "Reading installed Ollama models...")
    try:
        models = list_installed_models(base_url=base_url, timeout=5)
    except Exception as exc:
        raise SetupError(f"Ollama started, but Tubby could not read its models: {exc}") from exc

    installed_model = find_installed_model(ordered_report_models(models), report_model)
    if installed_model is None:
        _pull_ollama_model(report_model, progress, base_url=base_url)
        try:
            models = list_installed_models(base_url=base_url, timeout=10)
        except Exception as exc:
            raise SetupError(f"The model downloaded, but Tubby could not verify it: {exc}") from exc
        installed_model = find_installed_model(ordered_report_models(models), report_model)
        if installed_model is None:
            raise SetupError(f"Ollama did not report the downloaded model '{report_model}'.")

    save_preferred_model(installed_model.name)

    if options.prepare_speech_model:
        _report(progress, f"Preparing speech model {whisper_model}...")
        try:
            download_transcription_model(whisper_model)
        except Exception as exc:
            raise SetupError(f"Could not prepare speech model '{whisper_model}': {exc}") from exc

    status = inspect_runtime(whisper_model, base_url=base_url)
    _report(progress, "Tubby is ready.", 1.0)
    return SetupResult(status=status, selected_model=installed_model.name)


def find_ollama_executable() -> Path | None:
    override = os.environ.get("TUBBY_OLLAMA_EXECUTABLE", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate.resolve()

    command = shutil.which("ollama")
    if command:
        return Path(command).resolve()

    candidates: list[Path] = []
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe")
    elif sys.platform == "darwin":
        candidates.extend(
            (
                Path("/Applications/Ollama.app/Contents/Resources/ollama"),
                Path.home() / "Applications/Ollama.app/Contents/Resources/ollama",
                Path("/opt/homebrew/bin/ollama"),
                Path("/usr/local/bin/ollama"),
            )
        )

    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def install_ollama(progress: ProgressCallback | None = None) -> Path:
    if sys.platform == "win32":
        return _install_ollama_windows(progress)
    if sys.platform == "darwin":
        return _install_ollama_macos(progress)
    raise SetupError(
        "Automatic Ollama installation is available in the Windows and macOS desktop apps. "
        "Install Ollama manually or run Tubby's setup script on this platform."
    )


def start_ollama(executable: Path | None = None) -> None:
    resolved = executable or find_ollama_executable()
    if sys.platform == "darwin":
        app_path = _ollama_app_for_executable(resolved)
        if app_path is not None:
            _run_checked(["/usr/bin/open", "-g", str(app_path)], "Could not launch Ollama")
            return

    if resolved is None:
        raise SetupError("Ollama was installed, but its executable could not be found.")

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        subprocess.Popen(
            [str(resolved), "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise SetupError(f"Could not start Ollama: {exc}") from exc


def _install_ollama_windows(progress: ProgressCallback | None) -> Path:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise SetupError("Windows PowerShell is required to install Ollama.")

    with tempfile.TemporaryDirectory(prefix="tubby-ollama-") as temporary_dir:
        script_path = Path(temporary_dir) / "install.ps1"
        _download_file(
            WINDOWS_INSTALL_SCRIPT_URL,
            script_path,
            progress,
            "Downloading the official Ollama installer",
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _run_checked(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            "Ollama installation failed",
            creationflags=creation_flags,
        )

    executable = _wait_for_ollama_executable()
    if executable is None:
        raise SetupError("Ollama finished installing, but Tubby could not find ollama.exe.")
    return executable


def _install_ollama_macos(progress: ProgressCallback | None) -> Path:
    if shutil.which("ditto") is None or shutil.which("codesign") is None:
        raise SetupError("Required macOS system tools are unavailable.")

    with tempfile.TemporaryDirectory(prefix="tubby-ollama-") as temporary_dir:
        temporary_root = Path(temporary_dir)
        archive_path = temporary_root / "Ollama-darwin.zip"
        extracted_root = temporary_root / "extracted"
        extracted_root.mkdir()
        _download_file(
            MACOS_DOWNLOAD_URL,
            archive_path,
            progress,
            "Downloading the official Ollama app",
        )
        if not zipfile.is_zipfile(archive_path):
            raise SetupError("The downloaded Ollama package is not a valid ZIP archive.")

        _report(progress, "Verifying the Ollama app...")
        _run_checked(
            ["/usr/bin/ditto", "-x", "-k", str(archive_path), str(extracted_root)],
            "Could not unpack Ollama",
        )
        source_app = extracted_root / "Ollama.app"
        if not source_app.is_dir():
            raise SetupError("The official Ollama archive did not contain Ollama.app.")
        _run_checked(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(source_app)],
            "The Ollama app signature could not be verified",
        )
        if Path("/usr/sbin/spctl").is_file():
            _run_checked(
                ["/usr/sbin/spctl", "--assess", "--type", "execute", str(source_app)],
                "macOS did not accept the Ollama app signature",
            )

        applications_dir = _writable_applications_directory()
        destination_app = applications_dir / "Ollama.app"
        if destination_app.exists():
            raise SetupError(
                f"An incomplete Ollama app already exists at {destination_app}. "
                "Move it out of Applications, then run Tubby setup again."
            )
        _report(progress, f"Installing Ollama in {applications_dir}...")
        _run_checked(
            ["/usr/bin/ditto", str(source_app), str(destination_app)],
            "Could not copy Ollama into Applications",
        )
        _run_checked(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(destination_app)],
            "The installed Ollama app signature could not be verified",
        )

    executable = destination_app / "Contents" / "Resources" / "ollama"
    if not executable.is_file():
        raise SetupError("Ollama was copied, but its command-line executable is missing.")
    return executable.resolve()


def _pull_ollama_model(
    model: str,
    progress: ProgressCallback | None,
    *,
    base_url: str,
) -> None:
    _report(progress, f"Downloading report model {model}...")
    request = Request(
        f"{base_url.rstrip('/')}/api/pull",
        data=json.dumps({"model": model, "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": DOWNLOAD_USER_AGENT},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3600) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                event = json.loads(raw_line.decode("utf-8"))
                if not isinstance(event, dict):
                    continue
                error = str(event.get("error") or "").strip()
                if error:
                    raise SetupError(f"Ollama could not download '{model}': {error}")
                status = str(event.get("status") or "Downloading model").strip()
                total = _positive_int(event.get("total"))
                completed = _positive_int(event.get("completed"))
                ratio = completed / total if total and completed <= total else None
                _report(progress, f"{model}: {status}", ratio)
    except SetupError:
        raise
    except HTTPError as exc:
        raise SetupError(
            f"Ollama returned HTTP {exc.code} while downloading '{model}'."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SetupError(f"The '{model}' download was interrupted: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SetupError("Ollama returned unreadable model-download progress.") from exc


def _download_file(
    url: str,
    destination: Path,
    progress: ProgressCallback | None,
    label: str,
) -> None:
    request = Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response, destination.open("wb") as output:
            total = _positive_int(response.headers.get("Content-Length"))
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                ratio = downloaded / total if total else None
                _report(progress, f"{label}...", ratio)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SetupError(f"{label} failed: {exc}") from exc


def _run_checked(
    command: list[str],
    failure_message: str,
    *,
    creationflags: int = 0,
) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise SetupError(f"{failure_message}: {exc}") from exc
    if result.returncode == 0:
        return
    details = (result.stderr or result.stdout).strip()
    suffix = f": {details}" if details else f" (exit code {result.returncode})"
    raise SetupError(f"{failure_message}{suffix}")


def _wait_for_ollama(base_url: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _ollama_is_ready(base_url):
            return
        time.sleep(0.75)
    raise SetupError("Ollama did not become ready within 45 seconds.")


def _ollama_is_ready(base_url: str) -> bool:
    try:
        list_installed_models(base_url=base_url, timeout=1)
    except Exception:
        return False
    return True


def _wait_for_ollama_executable(timeout: float = 20) -> Path | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        executable = find_ollama_executable()
        if executable is not None:
            return executable
        time.sleep(0.5)
    return None


def _writable_applications_directory() -> Path:
    system_applications = Path("/Applications")
    if system_applications.is_dir() and os.access(system_applications, os.W_OK):
        return system_applications
    user_applications = Path.home() / "Applications"
    user_applications.mkdir(parents=True, exist_ok=True)
    return user_applications


def _ollama_app_for_executable(executable: Path | None) -> Path | None:
    if executable is None:
        return None
    for parent in executable.parents:
        if parent.name == "Ollama.app" and parent.is_dir():
            return parent
    return None


def _positive_int(value: object) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, parsed)


def _report(
    callback: ProgressCallback | None,
    message: str,
    ratio: float | None = None,
) -> None:
    if callback is not None:
        callback(SetupProgress(message=message, ratio=ratio))
