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


@dataclass(frozen=True)
class ModelRecommendation:
    name: str
    download_size: str
    profile: str
    best_for: str
    language_note: str
    tradeoff: str = ""
    language_warning: str = ""
    source_url: str = ""


MODEL_RECOMMENDATIONS = (
    ModelRecommendation(
        name="qwen3:4b",
        download_size="~2.5 GB",
        profile="Recommended - best overall",
        best_for="polished multilingual e-books, stories, and fully detailed reports",
        language_note="119 languages and dialects",
        source_url="https://ollama.com/library/qwen3:4b",
    ),
    ModelRecommendation(
        name="granite4.1:3b",
        download_size="~2.1 GB",
        profile="Best structured reports",
        best_for="evidence extraction, JSON reliability, and technical or business material",
        language_note="multilingual",
        source_url="https://ollama.com/library/granite4.1:3b",
    ),
    ModelRecommendation(
        name="qwen3.5:2b-q4_K_M",
        download_size="~1.9 GB",
        profile="Small modern option",
        best_for="low-memory machines and fast short or medium reports",
        language_note="broad multilingual support",
        tradeoff="less nuance on fully detailed long reports",
        source_url="https://ollama.com/library/qwen3.5:2b-q4_K_M",
    ),
    ModelRecommendation(
        name="qwen3:1.7b",
        download_size="~1.4 GB",
        profile="Smallest practical option",
        best_for="briefs and shorter videos on constrained hardware",
        language_note="119 languages and dialects",
        tradeoff="simpler prose and weaker long-report synthesis",
        source_url="https://ollama.com/library/qwen3:1.7b",
    ),
    ModelRecommendation(
        name="llama3.2:3b",
        download_size="~2.0 GB",
        profile="Fast summaries",
        best_for="concise summaries, rewriting, and story-style reports",
        language_note="8 officially supported languages",
        tradeoff="other report languages are unverified",
        language_warning=(
            "Official language support is limited to English, German, French, Italian, "
            "Portuguese, Hindi, Spanish, and Thai. Other report languages may be unreliable."
        ),
        source_url="https://ollama.com/library/llama3.2:3b",
    ),
    ModelRecommendation(
        name="phi4-mini:3.8b",
        download_size="~2.5 GB",
        profile="Technical reasoning",
        best_for="lectures with math, logic, or dense technical explanations",
        language_note="multilingual",
        source_url="https://ollama.com/library/phi4-mini:3.8b",
    ),
    ModelRecommendation(
        name="gemma3:4b",
        download_size="~3.3 GB",
        profile="Broad language coverage",
        best_for="reports where broad multilingual writing quality matters most",
        language_note="140+ languages",
        source_url="https://ollama.com/library/gemma3:4b",
    ),
    ModelRecommendation(
        name="ministral-3:3b",
        download_size="~3.0 GB",
        profile="Long structured reports",
        best_for="long-context consolidation and JSON-oriented output",
        language_note="dozens of languages",
        tradeoff="requires a current Ollama release",
        source_url="https://ollama.com/library/ministral-3:3b",
    ),
)

RECOMMENDED_MODEL = MODEL_RECOMMENDATIONS[0].name
DEFAULT_OLLAMA_URL = os.environ.get("TUBBY_OLLAMA_URL", "http://127.0.0.1:11434")

_MULTILINGUAL_FAMILIES = (
    "gemma4",
    "gemma3n",
    "gemma3",
    "qwen35",
    "qwen3",
    "qwen25",
    "qwen2",
    "qwen15",
    "qwen",
    "aya",
    "granite41",
    "granite4",
    "llama32",
    "phi4mini",
    "ministral3",
    "mistral3",
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
        return models_match(self.name, RECOMMENDED_MODEL)

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


def model_recommendation(model: OllamaModel | str) -> ModelRecommendation | None:
    name = model.name if isinstance(model, OllamaModel) else model
    return next(
        (
            recommendation
            for recommendation in MODEL_RECOMMENDATIONS
            if models_match(name, recommendation.name)
        ),
        None,
    )


def report_language_warning(model: OllamaModel) -> str:
    support = model.language_support
    if support == ModelLanguageSupport.ENGLISH_ONLY:
        return (
            f"{model.name} is classified as English-focused. "
            "Tubby disables other report languages for this model."
        )
    if support == ModelLanguageSupport.UNSUPPORTED:
        return f"{model.name} cannot generate Tubby reports."
    recommendation = model_recommendation(model)
    if recommendation is not None and recommendation.language_warning:
        return f"{model.name}: {recommendation.language_warning}"
    if support == ModelLanguageSupport.MULTILINGUAL:
        return ""
    return (
        f"Tubby cannot confirm multilingual report support for {model.name}. "
        "Non-English output may be unreliable."
    )


def setup_model_label(model: OllamaModel) -> str:
    recommendation = model_recommendation(model)
    if recommendation is not None:
        return (
            f"{recommendation.profile}; {recommendation.language_note}; "
            f"{recommendation.download_size} download"
        )

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


def model_selector_label(model: OllamaModel) -> str:
    recommendation = model_recommendation(model)
    if recommendation is not None:
        profile = recommendation.profile
    elif model.language_support == ModelLanguageSupport.MULTILINGUAL:
        profile = "Multilingual - not profiled"
    elif model.language_support == ModelLanguageSupport.ENGLISH_ONLY:
        profile = "English focused - not profiled"
    elif model.language_support == ModelLanguageSupport.UNSUPPORTED:
        profile = "Not compatible"
    else:
        profile = "Compatibility unverified"
    return f"{model.name} | {profile} | {model_size_label(model)}"


def model_selector_details(model: OllamaModel) -> str:
    recommendation = model_recommendation(model)
    if recommendation is not None:
        details = (
            f"Best for: {recommendation.best_for}. "
            f"Languages: {recommendation.language_note}."
        )
        if recommendation.tradeoff:
            details += f" Tradeoff: {recommendation.tradeoff}."
        return details

    support_details = {
        ModelLanguageSupport.MULTILINGUAL: "Multilingual report support is detected.",
        ModelLanguageSupport.ENGLISH_ONLY: "Tubby restricts this model to English reports.",
        ModelLanguageSupport.UNKNOWN: "Multilingual report support has not been verified.",
        ModelLanguageSupport.UNSUPPORTED: "This model cannot generate Tubby reports.",
    }
    parameter_details = (
        f" Parameters: {model.parameter_size}." if model.parameter_size else ""
    )
    return (
        "Tubby has no task-specific strength recommendation for this installed model. "
        f"{support_details[model.language_support]}{parameter_details}"
    )


def model_size_label(model: OllamaModel) -> str:
    if model.size_bytes:
        if model.size_bytes >= 1_000_000_000:
            return f"{model.size_bytes / 1_000_000_000:.1f} GB"
        if model.size_bytes >= 1_000_000:
            return f"{model.size_bytes / 1_000_000:.0f} MB"
        if model.size_bytes >= 1_000:
            return f"{model.size_bytes / 1_000:.0f} KB"
        return f"{model.size_bytes} bytes"

    recommendation = model_recommendation(model)
    if recommendation is not None:
        return recommendation.download_size
    if model.parameter_size:
        return f"{model.parameter_size} parameters"
    return "size unknown"


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

    choices = _setup_model_choices(usable, preferred, allow_install)
    if not choices:
        raise OllamaModelError(
            "No compatible Ollama model is available for Tubby report generation."
        )

    configured_selection = selection
    if configured_selection is None:
        configured_selection = os.environ.get("TUBBY_SETUP_MODEL_CHOICE")
    if interactive is None:
        interactive = input_stream.isatty() and not configured_selection

    if configured_selection:
        choice = _resolve_setup_selection(choices, configured_selection)
    elif len(choices) == 1:
        choice = choices[0]
    elif not interactive:
        choice = _unattended_setup_choice(choices, preferred)
    else:
        choice = _prompt_for_setup_model(choices, input_stream, output_stream)

    _write_setup_warning(choice.model, output_stream)
    return choice


def _setup_model_choices(
    installed_models: tuple[OllamaModel, ...],
    preferred: str,
    allow_install: bool,
) -> list[SetupModelChoice]:
    choices: list[SetupModelChoice] = []

    def add_choice(model: OllamaModel, installed: bool, *, first: bool = False) -> None:
        if any(models_match(choice.model.name, model.name) for choice in choices):
            return
        choice = SetupModelChoice(model, installed=installed)
        if first:
            choices.insert(0, choice)
        else:
            choices.append(choice)

    for recommendation in MODEL_RECOMMENDATIONS:
        installed = find_installed_model(installed_models, recommendation.name)
        if installed is not None:
            add_choice(installed, installed=True)
        elif allow_install:
            add_choice(OllamaModel.inferred(recommendation.name), installed=False)

    if not any(models_match(choice.model.name, preferred) for choice in choices):
        installed_preferred = find_installed_model(installed_models, preferred)
        if installed_preferred is not None:
            add_choice(installed_preferred, installed=True, first=True)
        elif allow_install:
            inferred_preferred = OllamaModel.inferred(preferred)
            if inferred_preferred.can_generate_reports:
                add_choice(inferred_preferred, installed=False, first=True)

    for model in installed_models:
        add_choice(model, installed=True)
    return choices


def _unattended_setup_choice(
    choices: list[SetupModelChoice],
    preferred: str,
) -> SetupModelChoice:
    installed_preferred = next(
        (
            choice
            for choice in choices
            if choice.installed and models_match(choice.model.name, preferred)
        ),
        None,
    )
    if installed_preferred is not None:
        return installed_preferred
    return next((choice for choice in choices if choice.installed), choices[0])


def _prompt_for_setup_model(
    choices: list[SetupModelChoice],
    input_stream: TextIO,
    output_stream: TextIO,
) -> SetupModelChoice:
    output_stream.write(
        "\nChoose the local Ollama model Tubby should use for reports.\n"
        "Every curated option supports Tubby's extraction and PDF workflow. Smaller models "
        "use less storage and memory, but may produce simpler long reports.\n\n"
    )
    for index, choice in enumerate(choices, start=1):
        recommendation = model_recommendation(choice.model)
        state = "installed" if choice.installed else "download"
        recommended = " (Recommended)" if choice.model.is_recommended else ""
        if recommendation is None:
            output_stream.write(
                f"  {index}. {choice.model.name}{recommended} "
                f"[{state}; {setup_model_label(choice.model)}]\n"
            )
            continue

        output_stream.write(
            f"  {index}. {choice.model.name}{recommended} "
            f"[{state}; {recommendation.download_size}]\n"
            f"     {recommendation.profile}: {recommendation.best_for}.\n"
            f"     Languages: {recommendation.language_note}."
        )
        if recommendation.tradeoff:
            output_stream.write(f" Tradeoff: {recommendation.tradeoff}.")
        output_stream.write("\n")

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
        return next((choice for choice in choices if choice.model.is_recommended), choices[0])
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
        help="choose an installed or curated compact report model during setup",
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
