from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from tubby.ollama_models import (
    ModelLanguageSupport,
    OllamaModel,
    OllamaModelError,
    choose_preferred_model,
    choose_setup_model,
    list_installed_models,
    load_preferred_model,
    models_match,
    ordered_report_models,
    report_language_warning,
    save_preferred_model,
)


class OllamaModelCompatibilityTests(unittest.TestCase):
    def test_qwen_family_is_multilingual_without_warning(self) -> None:
        model = _model("qwen3:4b", family="qwen3")

        self.assertTrue(model.can_generate_reports)
        self.assertEqual(model.language_support, ModelLanguageSupport.MULTILINGUAL)
        self.assertEqual(report_language_warning(model), "")

    def test_english_focused_model_restricts_report_languages(self) -> None:
        model = _model("codellama:7b", family="llama")

        self.assertEqual(model.language_support, ModelLanguageSupport.ENGLISH_ONLY)
        self.assertIn("English-focused", report_language_warning(model))

    def test_unknown_model_stays_available_with_warning(self) -> None:
        model = _model("custom-reporter:latest", family="custom")

        self.assertTrue(model.can_generate_reports)
        self.assertEqual(model.language_support, ModelLanguageSupport.UNKNOWN)
        self.assertIn("cannot confirm", report_language_warning(model))

    def test_embedding_model_cannot_generate_reports(self) -> None:
        model = OllamaModel(
            name="qwen3-embedding:4b",
            family="qwen3",
            capabilities=("embedding",),
        )

        self.assertFalse(model.can_generate_reports)
        self.assertEqual(model.language_support, ModelLanguageSupport.UNSUPPORTED)
        self.assertEqual(ordered_report_models((model,)), ())

    def test_cloud_model_is_not_offered_for_local_reports(self) -> None:
        model = _model("gemma4:31b-cloud", family="gemma4")

        self.assertFalse(model.can_generate_reports)
        self.assertEqual(model.language_support, ModelLanguageSupport.UNSUPPORTED)

    def test_latest_alias_matches_unqualified_model_name(self) -> None:
        self.assertTrue(models_match("gemma4:latest", "gemma4"))
        self.assertFalse(models_match("gemma4:e2b", "gemma4"))

    def test_preferred_installed_model_wins_over_recommendation(self) -> None:
        qwen = _model("qwen3:4b", family="qwen3")
        gemma = _model("gemma4:latest", family="gemma4")

        selected = choose_preferred_model((gemma, qwen), preferred="qwen3:4b")

        self.assertEqual(selected, qwen)

    def test_smallest_compatible_model_is_the_fallback(self) -> None:
        large = _model("qwen3:14b", family="qwen3", size_bytes=14_000)
        small = _model("qwen3:4b", family="qwen3", size_bytes=4_000)

        selected = choose_preferred_model((large, small), preferred="missing")

        self.assertEqual(selected, small)

    def test_gemma_variant_counts_as_the_recommended_family(self) -> None:
        gemma_variant = _model("gemma4:e2b", family="gemma4")
        output = StringIO()

        choice = choose_setup_model((gemma_variant,), output_stream=output)

        self.assertEqual(choice.model, gemma_variant)
        self.assertTrue(choice.installed)
        self.assertEqual(output.getvalue(), "")


class OllamaModelApiTests(unittest.TestCase):
    @patch("tubby.ollama_models.urlopen")
    def test_installed_models_are_parsed_from_ollama_tags(self, mocked_urlopen: object) -> None:
        payload = {
            "models": [
                {
                    "name": "qwen3:4b",
                    "size": 1234,
                    "details": {
                        "family": "qwen3",
                        "families": ["qwen3"],
                        "parameter_size": "4.0B",
                    },
                    "capabilities": ["completion", "thinking"],
                }
            ]
        }
        mocked_urlopen.return_value = _FakeResponse(json.dumps(payload).encode("utf-8"))

        installed = list_installed_models()

        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0].name, "qwen3:4b")
        self.assertEqual(installed[0].parameter_size, "4.0B")
        self.assertEqual(installed[0].size_bytes, 1234)
        self.assertEqual(
            installed[0].language_support,
            ModelLanguageSupport.MULTILINGUAL,
        )


class SetupModelChoiceTests(unittest.TestCase):
    def test_setup_recommends_gemma_when_other_models_are_installed(self) -> None:
        qwen = _model("qwen3:4b", family="qwen3")

        choice = choose_setup_model((qwen,), interactive=False)

        self.assertEqual(choice.model.name, "gemma4")
        self.assertFalse(choice.installed)

    def test_setup_can_continue_with_installed_multilingual_model_without_warning(
        self,
    ) -> None:
        qwen = _model("qwen3:4b", family="qwen3")
        output = StringIO()

        choice = choose_setup_model(
            (qwen,),
            interactive=True,
            input_stream=StringIO("2\n"),
            output_stream=output,
        )

        self.assertEqual(choice.model, qwen)
        self.assertTrue(choice.installed)
        self.assertNotIn("Warning:", output.getvalue())

    def test_setup_warns_when_selected_model_language_support_is_unknown(self) -> None:
        custom = _model("custom-reporter:latest", family="custom")
        output = StringIO()

        choice = choose_setup_model(
            (custom,),
            selection="custom-reporter:latest",
            output_stream=output,
        )

        self.assertTrue(choice.installed)
        self.assertIn("Warning:", output.getvalue())
        self.assertIn("cannot confirm", output.getvalue())

    def test_no_install_rejects_missing_explicit_model(self) -> None:
        with self.assertRaisesRegex(OllamaModelError, "not installed"):
            choose_setup_model(
                (),
                preferred="gemma4",
                allow_install=False,
                explicit=True,
            )

    def test_setup_rejects_explicit_embedding_model(self) -> None:
        with self.assertRaisesRegex(OllamaModelError, "cannot generate"):
            choose_setup_model(
                (),
                preferred="qwen3-embedding:4b",
                explicit=True,
            )

    def test_preferred_model_is_saved_in_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "TUBBY_CONFIG_DIR": temp_dir,
                    "TUBBY_OLLAMA_MODEL": "",
                },
            ):
                save_preferred_model("qwen3:8b")

                selected = load_preferred_model()

        self.assertEqual(selected, "qwen3:8b")


def _model(name: str, family: str, size_bytes: int = 0) -> OllamaModel:
    return OllamaModel(
        name=name,
        family=family,
        families=(family,),
        capabilities=("completion",),
        size_bytes=size_bytes,
    )


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
