"""Reject confirmed question-only evidence before returning detailed scores."""
def reject_question_evidence(generation, request):
    import json
    from app.providers.base import ProviderError
    try:
        data=json.loads(generation.raw)
        evidence=[x.get("quote","") for detail in data.get("criterion_feedback",{}).values() for x in detail.get("evidence",[])]
        evidence += [x.get("original","") for key in ("grammar_corrections","language_suggestions") for x in data.get(key,[])]
        evidence += [(x.get("evidence") or {}).get("quote","") for x in data.get("paragraph_reviews",[])]
    except (ValueError,TypeError,AttributeError):
        return # Full schema validation supplies the appropriate error.
    if any(isinstance(q,str) and q and q in request.prompt and q not in request.essay for q in evidence):
        raise ProviderError("question_evidence_leak", "Grade rejected: an error quote or edit belongs to the question, not the student essay.",502,
                            attempts=generation.attempts,generation=generation)
