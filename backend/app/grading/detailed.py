import json
from app.grading.aspects import ASPECTS
from app.grading.rubric import SYSTEM_PROMPT
from app.grading.schemas import word_count


DETAILED_PROMPT_VERSION = "task2-detailed-single-essay-v4"


def essay_paragraphs(essay: str) -> list[str]:
    from app.grading.payload import paragraph_spans
    return [essay[s['start']:s['end']] for s in paragraph_spans(essay)]


def detailed_input(request) -> str:
    from app.grading.payload import target_payload
    payload = target_payload(request.prompt, request.essay)
    if request.topic:
        payload['topic'] = request.topic
    return json.dumps(payload, ensure_ascii=False)


DETAILED_PROMPT = SYSTEM_PROMPT.replace("prompt, essay/paragraphs", "prompt, student_essay, metadata") + """

Provide diagnostics for up to 8 most relevant named aspects from the 16 below. These are practice diagnostics,
and must never be averaged mathematically into the four IELTS criterion bands. For non-opinion
prompts (e.g. causes/solutions), assess answer clarity rather than forcing an opinion stance.
Use the exact aspect names. Ground each explanation in observable qualities of this essay without
assuming every essay must contain personal anecdotes.
""" + "\n".join(f"{label}: {definition}." for group in ASPECTS.values() for label, definition in group) + """

The input contains one student_essay with [pN] paragraph labels when boundaries are verified, and measured metadata.
Labels are references, never part of a verbatim quote. When boundaries are unverified, do not infer a paragraphing fault.
Review up to the first six paragraphs with 1-based numbering: identify its role, state one
specific observation, and suggest one practical improvement. Supply a verbatim quote from that
exact paragraph when helpful, otherwise null. Never invent names, numbers, studies, or quotes.

Use grammar_corrections for genuine grammar, syntax, morphology, spelling, and punctuation errors.
Do not flag acceptable wording merely because an alternative sounds smoother. Put optional style,
clarity, and word-choice upgrades in language_suggestions with category word_choice, clarity, or style.
Copy every evidence quote and original edit span verbatim character-for-character from the essay.
Keep all scores within 0 to 9 in steps of 0.5, use lowercase paragraph roles (introduction, body,
conclusion, other), return at most 5 language suggestions, 5 genuine grammar corrections,
5 priorities/strengths/weaknesses per list, and up to 4 evidence quotes per criterion.
Evaluate all evidence before setting final criterion_scores.
""".strip()
