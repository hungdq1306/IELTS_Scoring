"""Exact, owner- and grading-context-scoped reuse; never collapse essay paragraphs."""
from app.guardrails import fingerprint


def content_hash(user_id, class_id, prompt, essay, snapshot, model):
    return fingerprint({'cache_revision': 2, 'user_id': user_id, 'class_id': class_id,
                        'prompt': prompt.replace('\r\n', '\n'), 'essay': essay.replace('\r\n', '\n'),
                        'snapshot': snapshot, 'model': model})


def answers_hash(answers):
    return fingerprint(sorted([{'exercise_id': row['exercise_id'], 'answer': row['answer']}
                               for row in answers], key=lambda row: row['exercise_id']))
