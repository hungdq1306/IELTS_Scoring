Supplemental references in the lecturer dataset layout

The six new references use the same top-level fields as processed/essays.jsonl. All essay and prompt text is preserved, including source hard line wraps; paragraph_count describes the four or five logical paragraphs, not every wrapped line.

Files:
- supplemental/essays.jsonl: six new references, lecturer_09 through lecturer_14.
- processed/essays_with_supplemental.jsonl: eight original lecturer records followed by six supplemental references, 14 total.
- supplemental/lecturer_09.json through lecturer_14.json: individual readable records in the same layout.
- supplemental/raw/: original user-supplied records before layout conversion.

Reference topics:
- lecturer_09: environmental damage and government/individual action; user-confirmed overall range 8.5–9.0.
- lecturer_10: preserving minority languages; user-confirmed overall 9.0.
- lecturer_11: university versus employment after school.
- lecturer_12: entertaining versus educational museums.
- lecturer_13: equal male/female university admissions.
- lecturer_14: local versus international help.

The scores object contains the AI criterion estimates already given in the conversation. These are explicitly marked overall_source=agent_assessment, score_source=previous_ai_agent_assessment_in_conversation and scores_verified=false. The user's confirmed overall labels for 09 and 10 are preserved separately in provenance.user_confirmed_overall_band_range. No lecturer criterion marks have been invented or claimed verified.

comments, suggestions and inline_feedback are empty arrays. revised_sample_essay is null. post_suggestion_essay equals original_essay because no corrections were provided. Empty annotations mean unavailable, not a claim that an examiner found no errors.

This is a data-layout export. It extends the original eight-document contract with IDs 09–14, nullable document IDs and an explicit agent_assessment score source. The existing CuratedEssay validator is intentionally restricted to authenticated documents 01–08 and is not the validator for this supplemental export. Existing FS5/FS7 loaders and manifests remain unchanged; these six records are not automatically inserted into production prompts. If used as calibration references later, exclude their texts from evaluation data.

Regenerate from the project root in PowerShell:

```powershell
$env:PYTHONPATH='backend'
python -m benchmark.prepare_supplemental_lecturer
```

Verification: six source-text matches, all top-level field sets match the existing lecturer layout, all word counts checked with the application tokenizer, empty annotation arrays checked, all original eight records preserved unchanged in the combined export, and 14 unique IDs.
