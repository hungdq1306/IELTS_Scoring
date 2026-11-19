import json
import re
from app.grading.aspects import ASPECTS
from app.grading.rubric import SYSTEM_PROMPT
from app.grading.schemas import word_count


DETAILED_PROMPT_VERSION = "task2-detailed-v3"


def essay_paragraphs(essay: str) -> list[str]:
    return [block.strip() for block in re.split(r"\r?\n(?:[ \t]*\r?\n)+", essay) if block.strip()]


def detailed_input(request) -> str:
    payload = request.model_dump(exclude_defaults=True)
    essay_text = payload.pop("essay")
    count = word_count(essay_text)
    payload["paragraphs"] = essay_paragraphs(essay_text)
    payload["word_count"] = count
    if count < 250:
        payload["length_note"] = (
            f"Essay is under 250 words ({count} words; {250 - count} words short). "
            "Assess strictly for underdeveloped arguments, missing extension, and reduced evidence."
        )
    return json.dumps(payload, ensure_ascii=False)


DETAILED_PROMPT = SYSTEM_PROMPT.replace("prompt, essay/paragraphs", "prompt, paragraphs") + """

Provide a diagnostic for each of the 16 named aspects below. These are practice diagnostics,
and must never be averaged mathematically into the four IELTS criterion bands. For non-opinion
prompts (e.g. causes/solutions), assess answer clarity rather than forcing an opinion stance.
Use the exact aspect names. Ground each explanation in observable qualities of this essay without
assuming every essay must contain personal anecdotes.
""" + "\n".join(f"{label}: {definition}." for group in ASPECTS.values() for label, definition in group) + """

The input contains the student essay as an ordered array of paragraphs alongside measured word_count.
Review each of the first twelve paragraphs with 1-based numbering: identify its role, state one
specific observation, and suggest one practical improvement. Supply a verbatim quote from that
exact paragraph when helpful, otherwise null. Never invent names, numbers, studies, or quotes.

Use grammar_corrections for genuine grammar, syntax, morphology, spelling, and punctuation errors.
Do not flag acceptable wording merely because an alternative sounds smoother. Put optional style,
clarity, and word-choice upgrades in language_suggestions with category word_choice, clarity, or style.
Copy every evidence quote and original edit span verbatim character-for-character from the essay.
Keep all scores within 0 to 9 in steps of 0.5, use lowercase paragraph roles (introduction, body,
conclusion, other), return at most 8 language suggestions, 5 priorities/strengths/weaknesses per list,
and up to 4 evidence quotes per criterion. Evaluate all evidence before setting final criterion_scores.
""".strip()
