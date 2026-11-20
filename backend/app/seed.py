from sqlalchemy import select

from app.guardrails import redact_pii
from app.models import ExerciseTemplate, Prompt, TeacherAnchor
from app.services.scorer import baseline_config


async def seed_defaults(database):
    """Run once after migrations, not on every HTTP server startup."""
    config = baseline_config()
    async with database.transaction() as session:
        for example in config['examples']:
            key = 'default-' + example['essay_id']
            if await session.get(TeacherAnchor, key) is None:
                session.add(TeacherAnchor(id=key, payload=example, version=1))
        defaults = [('default-context-choice', 'multiple_choice', 'Choose the word or grammatical form that best fits the full context.'),
                    ('default-guided-rewrite', 'sentence_rewriting', 'Rewrite a new sentence preserving meaning; optionally give a generic structure scaffold. Accept valid alternatives.'),
                    ('default-error-transfer', 'error_imitation', 'Correct the same verified error pattern in a new short passage.')]
        for key, kind, instruction in defaults:
            if await session.get(ExerciseTemplate, key) is None:
                session.add(ExerciseTemplate(id=key, kind=kind, instruction=instruction))
        prompts = [
            ('education-university', 'Education', 'Some people believe universities should focus on practical skills. Others believe academic knowledge is more important. Discuss both views and give your opinion.'),
            ('technology-education', 'Technology', 'Some people believe that artificial intelligence will improve education. To what extent do you agree or disagree?'),
            ('environment-transport', 'Environment', 'Governments should invest more in public transport than in building new roads. To what extent do you agree or disagree?'),
        ]
        for key, topic, text in prompts:
            if await session.get(Prompt, key) is None:
                session.add(Prompt(id=key, topic_tag=topic, prompt_text=text))
