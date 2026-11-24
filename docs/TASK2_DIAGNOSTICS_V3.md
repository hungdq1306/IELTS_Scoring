# Task 2 criterion diagnostics

## Scope

This document describes criterion diagnostics in the classroom Task 2 pilot. Task 1 remains isolated.

## Implemented behavior

- Scoring defaults to -1 as an internal sentinel: omit ThinkingConfig entirely, matching the request configuration before commit 2648fc3. This does not promise a particular number of reasoning tokens. Practice stays at budget 0. Explicit historical budgets in queued submission snapshots are preserved.
- Vietnamese student feedback remains; English evidence summaries precede scores, followed by structured Vietnamese diagnostics. Quotes/rewrites remain English.
- V2 uses its own DiagnosticReview (aspect_name, score, strength_vi, weakness_vi), preserving the old v1 AspectReview and validation adapter. Fifteen substantive aspects exclude Appropriateness of Format. Paragraphing means unity and logical grouping, never a count-based score bonus.
- New diagnostics have explicit strength/gap content and a ceiling of parent band + 0.5. A diagnostic score exceeding that ceiling is bounded with its raw model proposal retained and displayed; the four criterion bands are never changed by this consistency rule. Missing concrete gaps or structurally invalid output still fail validation. Overall bands remain calculated from the four criteria, not diagnostic averages.
- Capacity: 10 sentence annotations, 8 corrections, 8 language suggestions, 15 diagnostics, 6 paragraph reviews. Existing quote grounding remains active.
- V2 removes the inherited word-count-based caps and inferred underdevelopment note. At least 250 words meets the minimum; length alone is neither reward nor penalty. Real irrelevance, repetition or weak development is evaluated from evidence. Under-250 practice responses remain accepted with a warning, without a mechanical score table. Technical input limits are unchanged.
- Viewer hierarchy: band/summary, visible diagnostics cards sorted by score, one practice CTA. Feedback prose is 15px, line height 1.65, ink #172B2A on white. Diagnostic cards use amber/mint accents. Legacy explanations remain readable without fabricated strengths or weaknesses.
- Cache revision is 3 and new submission snapshots include the V2 revision, avoiding reuse of prior grading configuration.

## Local checking

Open http://localhost:8000 and choose Sample feedback, then TR/CC/LR/GRA to inspect labelled illustrative diagnostics without an AI call. Real authenticated grading uses the development pilot backend. The sample is not benchmark evidence. Local scoring setting has been changed to the provider-default sentinel; other credentials/model configuration are preserved.
