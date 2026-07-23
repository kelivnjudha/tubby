from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RECOMMENDED_MODEL = "gemma4"
DEFAULT_OLLAMA_URL = os.environ.get("TUBBY_OLLAMA_URL", "http://127.0.0.1:11434")

_MULTILINGUAL_FAMILIES = (
    "gemma4",
    "gemma3",
    "qwen3",
    "qwen25",
    "qwen2",
    "qwen15",
    "qwen",
    "aya",
)
_ENGLISH_FOCUSED_FAMILIES = (
    "codegemma",
    "codellama",
    "deepseekcoder",
    "starcoder",
    "sqlcoder",
    "tinyllama",
    "llama2",
    "gemma2",
    "phi3",
    "vicuna",
    "wizardlm",
)
_EMBEDDING_MARKERS = (
    "embedding",
    "embed",
    "allminilm",
    "bge",
    "mxbai",
    "nomicbert",
    "snowflakearctic",
)


class OllamaModelError(RuntimeError):
    """Raised when installed Ollama model information cannot be read."""


class ModelLanguageSupport(str, Enum):
    MULTILINGUAL = "multilingual"
    ENGLISH_ONLY = "english_only"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class OllamaModel:
    name: str
    family: str = ""
    families: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    parameter_size: str = ""
    size_bytes: int = 0

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "OllamaModel | None":
        name = str(value.get("name") or value.get("model") or "").strip()
        if not name:
            return None

        details = value.get("details")
        if not isinstance(details, dict):
            details = {}
        families = details.get("families")
        capabilities = value.get("capabilities")
        return cls(
            name=name,
            family=str(details.get("family") or "").strip(),
            families=tuple(str(item).strip() for item in families if str(item).strip())
            if isinstance(families, list)
            else (),
            capabilities=tuple(
                str(item).strip().casefold() for item in capabilities if str(item).strip()
            )
            if isinstance(capabilities, list)
            else (),
            parameter_size=str(details.get("parameter_size") or "").strip(),
            size_bytes=_positive_int(value.get("size")),
        )

    @classmethod
    def inferred(cls, name: str) -> "OllamaModel":
        family = name.split(":", 1)[0].strip()
        return cls(name=name.strip(), family=family, capabilities=("completion",))

    @property
    def can_generate_reports(self) -> bool:
        if _is_cloud_model(self.name):
            return False
        if any(
            marker in candidate
            for marker in _EMBEDDING_MARKERS
            for candidate in self._classification_candidates()
        ):
            return False
        if self.capabilities:
            return "completion" in self.capabilities
        return True

    @property
    def language_support(self) -> ModelLanguageSupport:
        if not self.can_generate_reports:
            return ModelLanguageSupport.UNSUPPORTED

        candidates = self._classification_candidates()
        if _matches_family(candidates, _MULTILINGUAL_FAMILIES):
            return ModelLanguageSupport.MULTILINGUAL
        if _matches_family(candidates, _ENGLISH_FOCUSED_FAMILIES):
            return ModelLanguageSupport.ENGLISH_ONLY
        return ModelLanguageSupport.UNKNOWN

    @property
    def is_recommended(self) -> bool:
        return _canonical_family(self.name.split(":", 1)[0]) == _canonical_family(RECOMMENDED_MODEL)

    def _classification_candidates(self) -> tuple[str, ...]:
        values = (self.name.split(":", 1)[0], self.family, *self.families)
        return tuple(candidate for value in values if (candidate := _canonical_family(value)))


@dataclass(frozen=True)
class SetupModelChoice:
    model: OllamaModel
    installed: bool


def _config_path() -> Path:
    override = os.environ.get("TUBBY_CONFIG_DIR")
    if override:
        return Path(override).expanduser() / "config.json"
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / "Tubby" / "config.json"
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "tubby" / "config.json"


def load_preferred_model() -> str:
    environment_model = os.environ.get("TUBBY_OLLAMA_MODEL", "").strip()
    if environment_model:
        return environment_model
    try:
        payload = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RECOMMENDED_MODEL
    if not isinstance(payload, dict):
        return RECOMMENDED_MODEL
    configured = str(payload.get("ollama_model") or "").strip()
    return configured or RECOMMENDED_MODEL


def save_preferred_model(model: str) -> None:
    selected = model.strip()
    if not selected:
        return

    target = _config_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["ollama_model"] = selected

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".tubby-config-",
            suffix=".json",
            dir=target.parent,
            delete=False,
        ) as temporary_file:
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


DEFAULT_MODEL = load_preferred_model()


def list_installed_models(
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout: float = 3,
) -> tuple[OllamaModel, ...]:
    request = Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise OllamaModelError(f"Ollama returned HTTP {exc.code} while listing models.") from exc
    except URLError as exc:
        raise OllamaModelError(
            f"Could not connect to Ollama at {base_url}. Start Ollama and refresh."
        ) from exc
    except TimeoutError as exc:
        raise OllamaModelError(f"Ollama did not respond within {timeout:g} seconds.") from exc
    except OSError as exc:
        raise OllamaModelError(f"Could not read Ollama's installed model list: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OllamaModelError("Ollama returned an unreadable model list.") from exc

    values = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise OllamaModelError("Ollama returned an unexpected model list.")

    models: list[OllamaModel] = []
    seen: set[str] = set()
    for value in values:
        model = OllamaModel.from_mapping(value) if isinstance(value, dict) else None
        if model is None or model.name.casefold() in seen:
            continue
        models.append(model)
        seen.add(model.name.casefold())
    return tuple(models)


def ordered_report_models(models: tuple[OllamaModel, ...]) -> tuple[OllamaModel, ...]:
    support_order = {
        ModelLanguageSupport.MULTILINGUAL: 0,
        ModelLanguageSupport.UNKNOWN: 1,
        ModelLanguageSupport.ENGLISH_ONLY: 2,
        ModelLanguageSupport.UNSUPPORTED: 3,
    }
    usable = (model for model in models if model.can_generate_reports)
    return tuple(
        sorted(
            usable,
            key=lambda model: (
                0 if model.is_recommended else 1,
                support_order[model.language_support],
                model.size_bytes or 2**63,
                model.name.casefold(),
            ),
        )
    )


def find_installed_model(
    models: tuple[OllamaModel, ...],
    requested: str,
) -> OllamaModel | None:
    return next((model for model in models if models_match(model.name, requested)), None)


def choose_preferred_model(
    models: tuple[OllamaModel, ...],
    preferred: str = DEFAULT_MODEL,
) -> OllamaModel | None:
    usable = ordered_report_models(models)
    selected = find_installed_model(usable, preferred)
    if selected is not None:
        return selected
    recommended = find_installed_model(usable, RECOMMENDED_MODEL)
    return recommended or (usable[0] if usable else None)


def models_match(left: str, right: str) -> bool:
    return _model_alias(left) == _model_alias(right)


def report_language_warning(model: OllamaModel) -> str:
    support = model.language_support
    if support == ModelLanguageSupport.MULTILINGUAL:
        return ""
    if support == ModelLanguageSupport.ENGLISH_ONLY:
        return (
            f"{model.name} is classified as English-focused. "
            "Tubby disables other report languages for this model."
        )
    if support == ModelLanguageSupport.UNSUPPORTED:
        return f"{model.name} cannot generate Tubby reports."
    return (
        f"Tubby cannot confirm multilingual report support for {model.name}. "
        "Non-English output may be unreliable."
    )


def setup_model_label(model: OllamaModel) -> str:
    support = model.language_support
    if support == ModelLanguageSupport.MULTILINGUAL:
        language_label = "multilingual reports supported"
    elif support == ModelLanguageSupport.ENGLISH_ONLY:
        language_label = "English reports only"
    elif support == ModelLanguageSupport.UNSUPPORTED:
        language_label = "not compatible with report generation"
    else:
        language_label = "multilingual support unverified"
    size = f", {model.parameter_size}" if model.parameter_size else ""
    return f"{language_label}{size}"


def choose_setup_model(
    models: tuple[OllamaModel, ...],
    preferred: str = RECOMMENDED_MODEL,
    *,
    allow_install: bool = True,
    explicit: bool = False,
    selection: str | None = None,
    interactive: bool | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> SetupModelChoice:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stderr
    installed_preferred = find_installed_model(models, preferred)
    usable = ordered_report_models(models)
    if installed_preferred is None and models_match(preferred, RECOMMENDED_MODEL):
        installed_preferred = next((model for model in usable if model.is_recommended), None)

    if explicit:
        if installed_preferred is not None:
            choice = SetupModelChoice(installed_preferred, installed=True)
        elif allow_install:
            choice = SetupModelChoice(OllamaModel.inferred(preferred), installed=False)
        else:
            raise OllamaModelError(
                f"Requested model '{preferred}' is not installed and model downloads are disabled."
            )
        if not choice.model.can_generate_reports:
            raise OllamaModelError(
                f"Requested model '{choice.model.name}' cannot generate Tubby reports."
            )
        _write_setup_warning(choice.model, output_stream)
        return choice

    if installed_preferred is not None and installed_preferred.can_generate_reports:
        choice = SetupModelChoice(installed_preferred, installed=True)
        _write_setup_warning(choice.model, output_stream)
        return choice

    choices: list[SetupModelChoice] = []
    inferred_preferred = OllamaModel.inferred(preferred)
    if allow_install and inferred_preferred.can_generate_reports:
        choices.append(SetupModelChoice(inferred_preferred, installed=False))
    choices.extend(SetupModelChoice(model, installed=True) for model in usable)
    if not choices:
        raise OllamaModelError(
            "No compatible Ollama model is available for Tubby report generation."
        )

    configured_selection = selection
    if configured_selection is None:
        configured_selection = os.environ.get("TUBBY_SETUP_MODEL_CHOICE")
    if interactive is None:
        interactive = input_stream.isatty() and not configured_selection

    if len(choices) == 1:
        choice = choices[0]
    elif configured_selection:
        choice = _resolve_setup_selection(choices, configured_selection)
    elif not interactive:
        choice = choices[0]
    else:
        choice = _prompt_for_setup_model(choices, input_stream, output_stream)

    _write_setup_warning(choice.model, output_stream)
    return choice


def _prompt_for_setup_model(
    choices: list[SetupModelChoice],
    input_stream: TextIO,
    output_stream: TextIO,
) -> SetupModelChoice:
    output_stream.write("\nChoose the Ollama model Tubby should use for reports:\n")
    for index, choice in enumerate(choices, start=1):
        install_label = "install" if not choice.installed else "installed"
        recommended = " (Recommended)" if choice.model.is_recommended else ""
        output_stream.write(
            f"  {index}. {choice.model.name}{recommended} "
            f"[{install_label}; {setup_model_label(choice.model)}]\n"
        )

    while True:
        output_stream.write("Select a model [1]: ")
        output_stream.flush()
        answer = input_stream.readline()
        if answer == "":
            return choices[0]
        try:
            return _resolve_setup_selection(choices, answer.strip() or "1")
        except OllamaModelError as exc:
            output_stream.write(f"{exc}\n")


def _resolve_setup_selection(
    choices: list[SetupModelChoice],
    selection: str,
) -> SetupModelChoice:
    normalized = selection.strip()
    if normalized.casefold() in {"recommended", "default"}:
        return choices[0]
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(choices):
            return choices[index]
    for choice in choices:
        if models_match(choice.model.name, normalized):
            return choice
    raise OllamaModelError(f"Invalid model selection '{selection}'.")


def _write_setup_warning(model: OllamaModel, output_stream: TextIO) -> None:
    warning = report_language_warning(model)
    if warning:
        output_stream.write(f"Warning: {warning}\n")


def _model_alias(value: str) -> str:
    normalized = value.strip().casefold()
    return normalized.removesuffix(":latest")


def _is_cloud_model(value: str) -> bool:
    normalized = value.strip().casefold()
    return normalized.endswith(":cloud") or normalized.endswith("-cloud")


def _canonical_family(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _matches_family(candidates: tuple[str, ...], families: tuple[str, ...]) -> bool:
    return any(candidate.startswith(family) for candidate in candidates for family in families)


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, number)


def _model_as_json(model: OllamaModel) -> dict[str, Any]:
    return {
        "name": model.name,
        "family": model.family,
        "families": list(model.families),
        "capabilities": list(model.capabilities),
        "parameter_size": model.parameter_size,
        "size_bytes": model.size_bytes,
        "can_generate_reports": model.can_generate_reports,
        "language_support": model.language_support.value,
    }


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Ollama models available to Tubby.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list installed Ollama models")
    list_parser.add_argument("--json", action="store_true", dest="as_json")

    choose_parser = subparsers.add_parser(
        "choose-setup",
        help="choose an installed model or the recommended model during setup",
    )
    choose_parser.add_argument("--preferred", default=RECOMMENDED_MODEL)
    choose_parser.add_argument("--explicit", action="store_true")
    choose_parser.add_argument("--no-install", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        models = list_installed_models()
        if arguments.command == "list":
            if arguments.as_json:
                print(json.dumps([_model_as_json(model) for model in models], ensure_ascii=False))
            else:
                for model in ordered_report_models(models):
                    print(f"{model.name}\t{setup_model_label(model)}")
            return 0

        choice = choose_setup_model(
            models,
            preferred=arguments.preferred,
            allow_install=not arguments.no_install,
            explicit=arguments.explicit,
        )
        try:
            save_preferred_model(choice.model.name)
        except OSError as exc:
            print(f"Warning: Could not save the preferred model: {exc}", file=sys.stderr)
        state = "installed" if choice.installed else "missing"
        print(f"{choice.model.name}\t{state}\t{choice.model.language_support.value}")
        return 0
    except OllamaModelError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
