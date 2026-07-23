from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from tubby.ollama_models import (
    MODEL_RECOMMENDATIONS,
    RECOMMENDED_MODEL,
    ModelLanguageSupport,
    OllamaModel,
    OllamaModelError,
    choose_preferred_model,
    choose_setup_model,
    list_installed_models,
    load_preferred_model,
    model_recommendation,
    model_selector_details,
    model_selector_label,
    model_size_label,
    models_match,
    ordered_report_models,
    report_language_warning,
    save_preferred_model,
    setup_model_label,
)


class OllamaModelCompatibilityTests(unittest.TestCase):
    def test_qwen_family_is_multilingual_without_warning(self) -> None:
        model = _model("qwen3:4b", family="qwen3")

        self.assertTrue(model.can_generate_reports)
        self.assertEqual(model.language_support, ModelLanguageSupport.MULTILINGUAL)
        self.assertEqual(report_language_warning(model), "")

    def test_every_curated_model_is_compatible_with_report_generation(self) -> None:
        for recommendation in MODEL_RECOMMENDATIONS:
            with self.subTest(model=recommendation.name):
                model = OllamaModel.inferred(recommendation.name)

                self.assertTrue(model.can_generate_reports)
                self.assertEqual(
                    model.language_support,
                    ModelLanguageSupport.MULTILINGUAL,
                )
                self.assertEqual(model_recommendation(model), recommendation)

    def test_llama_3_2_reports_its_official_language_limit(self) -> None:
        model = _model("llama3.2:3b", family="llama3.2")

        self.assertEqual(model.language_support, ModelLanguageSupport.MULTILINGUAL)
        self.assertIn("Official language support is limited", report_language_warning(model))
        self.assertIn("Thai", report_language_warning(model))

    def test_curated_selector_label_shows_recommendation_strength_and_size(self) -> None:
        model = _model("qwen3:4b", family="qwen3")

        label = model_selector_label(model)

        self.assertIn("qwen3:4b", label)
        self.assertIn("Recommended - best overall", label)
        self.assertIn("~2.5 GB", label)
        self.assertIn("polished multilingual e-books", model_selector_details(model))

    def test_unprofiled_selector_label_uses_installed_metadata(self) -> None:
        model = OllamaModel(
            name="custom-reporter:7b",
            family="custom",
            families=("custom",),
            capabilities=("completion",),
            parameter_size="7.0B",
            size_bytes=3_250_000_000,
        )

        self.assertEqual(model_size_label(model), "3.2 GB")
        self.assertIn("Compatibility unverified", model_selector_label(model))
        self.assertIn("no task-specific strength", model_selector_details(model))
        self.assertIn("7.0B", model_selector_details(model))

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

    def test_smallest_compatible_model_is_the_fallback_without_recommendation(
        self,
    ) -> None:
        large = _model("qwen3:14b", family="qwen3", size_bytes=14_000)
        small = _model("qwen3:1.7b", family="qwen3", size_bytes=1_700)

        selected = choose_preferred_model((large, small), preferred="missing")

        self.assertEqual(selected, small)

    def test_only_the_balanced_default_is_marked_recommended(self) -> None:
        balanced = _model("qwen3:4b", family="qwen3")
        larger = _model("qwen3:14b", family="qwen3")

        self.assertTrue(balanced.is_recommended)
        self.assertFalse(larger.is_recommended)

    def test_unattended_setup_reuses_compatible_installed_model(self) -> None:
        gemma_variant = _model("gemma4:e2b", family="gemma4")
        output = StringIO()

        choice = choose_setup_model(
            (gemma_variant,),
            interactive=False,
            output_stream=output,
        )

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
    def test_unattended_setup_reuses_installed_model_before_downloading(self) -> None:
        installed = _model("custom-reporter:latest", family="custom")
        output = StringIO()

        choice = choose_setup_model(
            (installed,),
            interactive=False,
            output_stream=output,
        )

        self.assertEqual(choice.model, installed)
        self.assertTrue(choice.installed)
        self.assertIn("multilingual", output.getvalue())

    def test_unattended_setup_uses_balanced_default_when_none_are_installed(
        self,
    ) -> None:
        choice = choose_setup_model((), interactive=False)

        self.assertEqual(choice.model.name, RECOMMENDED_MODEL)
        self.assertFalse(choice.installed)

    def test_interactive_setup_describes_and_selects_installed_recommendation(
        self,
    ) -> None:
        qwen = _model("qwen3:4b", family="qwen3")
        output = StringIO()

        choice = choose_setup_model(
            (qwen,),
            interactive=True,
            input_stream=StringIO("1\n"),
            output_stream=output,
        )

        self.assertEqual(choice.model, qwen)
        self.assertTrue(choice.installed)
        self.assertIn("Recommended", output.getvalue())
        self.assertIn("best overall", output.getvalue())
        self.assertIn("2.5 GB", output.getvalue())
        self.assertIn("119 languages", output.getvalue())
        self.assertNotIn("Warning:", output.getvalue())

    def test_setup_can_select_a_curated_model_for_download(self) -> None:
        choice = choose_setup_model(
            (),
            selection="granite4.1:3b",
            output_stream=StringIO(),
        )

        self.assertEqual(choice.model.name, "granite4.1:3b")
        self.assertFalse(choice.installed)
        self.assertIn("Best structured reports", setup_model_label(choice.model))

    def test_catalog_model_names_are_unique(self) -> None:
        names = [recommendation.name.casefold() for recommendation in MODEL_RECOMMENDATIONS]

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[0], RECOMMENDED_MODEL)

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
                preferred="qwen3:4b",
                allow_install=False,
                explicit=True,
            )

    def test_explicit_legacy_model_still_bypasses_the_catalog(self) -> None:
        choice = choose_setup_model(
            (),
            preferred="gemma4:e2b",
            explicit=True,
            output_stream=StringIO(),
        )

        self.assertEqual(choice.model.name, "gemma4:e2b")
        self.assertFalse(choice.installed)

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
