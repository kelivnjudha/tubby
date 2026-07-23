from __future__ import annotations

LANGUAGE_OPTIONS = (
    "English",
    "Thai",
    "Spanish",
    "French",
    "German",
    "Portuguese",
    "Indonesian",
    "Vietnamese",
    "Japanese",
    "Korean",
    "Chinese (Simplified)",
    "Hindi",
    "Italian",
    "Dutch",
    "Russian",
    "Turkish",
)

_LANGUAGE_CODES = {
    "english": "en",
    "thai": "th",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt",
    "indonesian": "id",
    "vietnamese": "vi",
    "japanese": "ja",
    "korean": "ko",
    "chinese (simplified)": "zh-Hans",
    "hindi": "hi",
    "italian": "it",
    "dutch": "nl",
    "russian": "ru",
    "turkish": "tr",
}


def language_code_for(language: str) -> str:
    """Return a YouTube caption language code for a report language."""
    return _LANGUAGE_CODES.get(language.strip().casefold(), "en")


def language_name_for_code(language_code: str) -> str:
    normalized = language_code.strip().casefold().replace("_", "-")
    base_code = normalized.split("-", 1)[0]
    for name, code in _LANGUAGE_CODES.items():
        normalized_code = code.casefold().replace("_", "-")
        if normalized in {normalized_code, normalized_code.split("-", 1)[0]}:
            return name.title()
        if base_code == normalized_code.split("-", 1)[0]:
            return name.title()
    return language_code.strip() or "Unknown"
