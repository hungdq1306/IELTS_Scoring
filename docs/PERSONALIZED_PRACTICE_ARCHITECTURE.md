# Personalized practice architecture

## Shared validation

`app/practice/schemas.py`, `diagnosis.py` and `prompts.py` define the taxonomy, exercise contracts, deterministic evidence/answer checks and provider instructions used by both implementations. Errors must be grounded in the learner essay; exercises require independent semantic review. Optional style is accepted only in the high-band refinement path. Empty output remains possible when no candidate passes validation.

## Classroom pilot

`services/drill_gen.py` drafts and reviews practice after the learner requests it. `routers/pilot.py` checks account/class ownership and creates durable jobs. `worker.py` runs generation, complete-set answers and revisions. PostgreSQL `PracticeSet` and `Job` records retain results. The frontend `practice-batch.jsx` uses account-scoped local drafts and submits only a complete answer set.

For essays at band 8 or above without suitable normal exercises, an additional generation/review pass can create lexical-precision and nuanced-cohesion refinement. These are optional upgrades, not assertions that correct language is wrong. Practice feedback never assigns a new IELTS band. MCQ correctness follows the reviewed key; free-text feedback uses the configured smaller evaluator.

## Local research/demo

`practice/service.py`, `store.py`, `routes.py` and `batch.py` implement the separate cookie-session SQLite adapter exposed by `app.main:app`. They remain covered by tests and benchmark tooling. They are not the persistence/queue implementation of the classroom pilot.

See [API](PERSONALIZED_PRACTICE_API.md), [system architecture](ARCHITECTURE.md) and [historical evaluation](archive/PERSONALIZED_PRACTICE_EVALUATION.md).
