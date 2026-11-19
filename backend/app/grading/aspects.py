ASPECTS = {
    "task_response": (
        ("Relevance to Prompt", "Coverage of every part of the prompt"),
        ("Clarity of Position", "Clarity of the answer or position required by the task"),
        ("Depth of Ideas", "Development and explanation of ideas"),
        ("Appropriateness of Format", "Suitability of the essay format"),
        ("Relevant & Specific Examples", "Relevance and specificity of support or examples"),
    ),
    "coherence_cohesion": (
        ("Logical Organization", "Logical progression of ideas"),
        ("Effective Introduction & Conclusion", "Effectiveness of opening and closing"),
        ("Supported Main Points", "Organization of supporting details around main points"),
        ("Cohesive Devices Usage", "Use of linking, referencing and substitution"),
        ("Paragraphing", "Paragraph unity and boundaries"),
    ),
    "lexical_resource": (
        ("Vocabulary Range", "Vocabulary range and flexibility"),
        ("Lexical Accuracy", "Precision, collocation and register"),
        ("Spelling and Word Formation", "Spelling and word formation"),
    ),
    "grammatical_range_accuracy": (
        ("Sentence Structure Variety", "Range and control of sentence structures"),
        ("Grammar Accuracy", "Grammar and syntax accuracy"),
        ("Punctuation Usage", "Punctuation accuracy"),
    ),
}
ASPECT_LABELS = tuple(label for group in ASPECTS.values() for label, _ in group)
LENGTH_ASPECT = "Appropriate Word Count"
