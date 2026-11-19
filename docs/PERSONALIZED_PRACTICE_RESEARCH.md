# Personalized practice research and implementation audit

Research checked 18 November 2026. This is a research-inspired engineering MVP, not a replication or an educational effectiveness study.

## Primary study

[Ren, Dong and Zhang (2025), From Errors to Excellence](https://doi.org/10.1080/2331186X.2025.2588512) investigated feedback plus personalized corrective exercises in an eight-week writing course. Its convenience sample contained 44 English-major undergraduates: 25 received both interventions and 19 received AI feedback alone. Exercises reproduced recurrent error patterns in new material for learners to identify and correct. Human instructors remained involved in assessment. The reported advantages varied across assessment occasions; the study does not justify promising a universal improvement. Small, context-specific groups and the quasi-experimental design limit generalization. Direct publisher access returned HTTP 403; indexed publisher methodology and discussion were consulted. This implementation does not reproduce the original intervention protocol, model, population, or outcome measures.

## Supporting references and adaptations

| Primary source | Practical idea | Adaptation and limit |
|---|---|---|
| [English grammar MCQ generation](https://github.com/ZanichelliEditore/english-grammar-multiple-choice-generation) | Separate grammatical validity, ambiguity and distractor quality from format compliance | Distinct options and key membership checked in code; Gemini separately reviews correctness, ambiguity and distractors. Published results from that project are not our results. |
| [ERRANT](https://github.com/chrisjbryant/errant) | Classify edits between original and corrected text | Borrow the distinction between error types and supporting edits. ERRANT is not installed and is not a truth detector for proposed corrections. |
| [AdaptiveQG](https://github.com/nlpcui/AdaptiveQG), [Cui and Sachan, ACL 2023](https://aclanthology.org/2023.acl-long.567/) | Use learner history to control exercise generation | Repository model/evaluator code and the paper were inspected; the master branch has no root README. Use a small, explicit practice-history heuristic instead of importing knowledge tracing or training models. |
| [Cambridge Write & Improve](https://help.writeandimprove.com/en/articles/1104369-how-does-write-improve-work), [learning resources](https://www.cambridgeenglish.org/learning-english/) | Writing practice should promote feedback use and revision | Preserve before/after paragraphs and allow return to grading. We do not reproduce Cambridge technology, training data, or proficiency calibration. |

No code from these repositories was copied. Source versions may change. Their datasets and licenses are not implicitly transferred to this application.

## Existing implementation audit

- Grading: backend/app/main.py, POST /api/writing/task2/evaluate. Existing detailed grading and FS0/FS1/FS2 prompts and benchmark MAE/QWK are retained.
- Response: backend/app/api_models.py and app/grading schemas; scores, criterion feedback, grammar corrections and paragraph reviews already exist. A nullable submission_id links to optional practice.
- Provider: backend/app/providers/gemini.py, backend-only credentials, structured responses and shared quota/pacing.
- Persistence: SQLite via benchmark.store.connect; practice uses results/_practice.sqlite3 with the existing connection pattern. No existing durable browser learning history was available, so isolated tables were added.
- Frontend: frontend/src/main.jsx results now embed PracticeWorkspace; original grading Feedback remains accessible.
- Tests: backend/tests; grading benchmarks remain separate from backend/benchmark/practice.py.
- Writing9 and Lexibot grades are weak context, not human-confirmed error labels. No lecturer gold collection is assumed.

## Engineering interpretation

Evidence verification only proves that a quote occurs in the essay. It does not prove that the language is wrong. Keep these checks separate: exact evidence and schema checks, followed by independent automated semantic review, followed by future lecturer review. Optional style suggestions are excluded. Discourse weaknesses retain paragraph context and are practiced through paragraph revision.

Select at most five approved, high-impact/repeated weaknesses. A single real weakness can support recognition, controlled correction and a new-context imitation passage; do not invent additional diagnoses to fill slots. New learners start at level one. Three prior correct practice responses permit a modest stage preference of two; this is not a proficiency estimate.

Recognition, controlled correction, independent rewriting and transfer/revision form the scaffold. All six supported exercise types are schema-validated. MCQs and identified spans use deterministic checking; reviewed reference answers are matched locally; other free text uses a separate Gemini evaluator. Multiple valid rewrites are allowed, and no exercise receives an IELTS band.

## Evidence and limitations

Machine reviewers can share generator biases. Prompt-injection screening and source checks reduce risk but cannot establish perfect linguistic correctness or security. Offline validity is distinct from student learning. Lecturer CSVs deliberately leave human labels blank; future controlled and delayed transfer assessments require separate approval and actual participants. The new tables prepare observations but do not assign groups.
