from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportStyleDefinition:
    label: str
    document_label: str
    synthesis_instruction: str
    max_output_tokens: int


_REPORT_STYLES = {
    "E-book": ReportStyleDefinition(
        label="E-book",
        document_label="E-book Edition",
        synthesis_instruction=(
            "Create a polished nonfiction e-book with a strong title, useful subtitle, "
            "inviting introduction, 5 to 8 logically ordered chapters, chapter takeaways, "
            "and a conclusive closing. Explain context and connections clearly while keeping "
            "every factual claim traceable to the extracted evidence."
        ),
        max_output_tokens=8192,
    ),
    "Story": ReportStyleDefinition(
        label="Story",
        document_label="Narrative Edition",
        synthesis_instruction=(
            "Retell the material as an engaging chronological narrative in 4 to 7 parts. "
            "Use scenes, progression, and transitions without inventing dialogue, motives, "
            "events, or sensory details. Clearly attribute opinions and uncertain claims."
        ),
        max_output_tokens=8192,
    ),
    "Short": ReportStyleDefinition(
        label="Short",
        document_label="Concise Edition",
        synthesis_instruction=(
            "Create a compact brief with 2 or 3 short sections. Remove repetition and minor "
            "examples, but retain every material fact, name, number, decision, action, and "
            "caveat needed to understand the source accurately."
        ),
        max_output_tokens=4096,
    ),
    "Fully detailed": ReportStyleDefinition(
        label="Fully detailed",
        document_label="Detailed Edition",
        synthesis_instruction=(
            "Create a comprehensive reference work with 7 to 12 substantial chapters. "
            "Preserve technical explanations, chronology, examples, names, numbers, competing "
            "views, decisions, actions, open questions, and caveats without unnecessary "
            "repetition."
        ),
        max_output_tokens=12288,
    ),
}

REPORT_STYLE_OPTIONS = tuple(_REPORT_STYLES)
DEFAULT_REPORT_STYLE = "E-book"


def get_report_style(value: str) -> ReportStyleDefinition:
    normalized = value.strip().casefold()
    aliases = {
        "ebook": "E-book",
        "e-book": "E-book",
        "story": "Story",
        "short": "Short",
        "concise": "Short",
        "detailed": "Fully detailed",
        "fully detailed": "Fully detailed",
    }
    label = aliases.get(normalized, value.strip())
    return _REPORT_STYLES.get(label, _REPORT_STYLES[DEFAULT_REPORT_STYLE])
