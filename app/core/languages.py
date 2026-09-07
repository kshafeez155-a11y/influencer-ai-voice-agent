"""Languages supported by creator profiles and Cartesia speech synthesis."""

LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "pa": "Punjabi",
    "ar": "Arabic",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "zh": "Mandarin Chinese",
}


def normalise_languages(primary: str, supported: list[str]) -> tuple[str, list[str]]:
    clean_primary = primary.strip().lower()
    if clean_primary not in LANGUAGES:
        raise ValueError("Unsupported primary language.")
    clean_supported = []
    for value in supported:
        code = str(value).strip().lower()
        if code not in LANGUAGES:
            raise ValueError(f"Unsupported language: {code or 'empty'}.")
        if code not in clean_supported:
            clean_supported.append(code)
    if clean_primary not in clean_supported:
        clean_supported.insert(0, clean_primary)
    return clean_primary, clean_supported
