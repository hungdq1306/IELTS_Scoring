# Personalized practice API

Base URL: http://127.0.0.1:8000/api. Grade first using the existing evaluation endpoint; retain the HttpOnly ielts_practice_session cookie and response submission_id. Browser requests must send credentials on the same origin.

| Method | Path | Behavior |
|---|---|---|
| GET | /practice/submissions | List up to 30 owned saved assessments |
| GET | /writing/task2/{submission_id}/submission | Restore original question, essay and grade |
| POST | /writing/task2/{submission_id}/exercises | Generate once, return cached ready batch thereafter |
| GET | /writing/task2/{submission_id}/exercises | Read public exercises without generation |
| POST | /exercises/{exercise_id}/answer | Check answer and reveal feedback/key after submission |
| GET | /exercises/{exercise_id}/feedback | Restore last submitted feedback; 404 before any answer |
| POST | /exercises/{exercise_id}/hint | Persist hint use, no Gemini request |
| POST | /writing/task2/{submission_id}/revision | Evaluate a paragraph with an approved source weakness |
| GET | /writing/task2/{submission_id}/progress | Read persisted practice outcomes and revisions |

Answer body:

```json
{"answer":"helps","request_id":"unique-request-0001"}
```

Revision body additionally contains paragraph_number (one-based). Request IDs are 8–80 letters, digits, underscores or hyphens. Reusing a request ID with another body returns 409. Answers have a 5,000-character maximum. Whitespace-only answers should not be sent by clients.

Public errors include evidence, category, offsets and reviewability. Public exercises include question, options, source linkage, objective, difficulty, validation_status, completion and attempts. They exclude correct_answer, alternatives, target_span, detailed correction and hint until the appropriate action. Answer responses distinguish deterministic and Gemini evaluation, return correct/incorrect/partially_correct, explanation, suggested improvement and target/meaning/new-error checks; human_reviewed is false.

No numeric grading scores are sent to the practice generation prompt. No overall IELTS band is assigned to an exercise or paragraph revision.

## Errors and operational limits

401: absent/expired session. 404: resource not owned or no feedback yet. 409: duplicate/conflicting/in-flight request, generation/attempt/revision limit, or no approved revision weakness. 422: invalid request/schema. Provider exceptions retain existing HTTP mapping: quota/rate limits, DNS/network/configuration, timeout and malformed structured outputs are shown by the frontend. Failed generation leaves grading available.

A ready batch may contain fewer than three or zero exercises. This is an intentional validated outcome. A pending operation left by a crashed process requires operator inspection of practice_calls and batch state before any manual reset; never automatically reset and rebill it.

Generation ordinarily costs two logical requests: draft plus independent review; one if all source errors fail evidence checks. MCQ, span selection, hint, history and exact reviewed-answer matches cost zero calls. Nonmatching free-text evaluation and paragraph revision ordinarily cost one request each. Provider retries may add attempts; the configured daily budget and pacing are shared with grading.
