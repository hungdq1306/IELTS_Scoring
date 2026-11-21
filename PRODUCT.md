# FogWrite

FogWrite provides IELTS Academic Writing Task 2 assessment and personalized practice. Scores are AI practice estimates, not official IELTS results.

## Classroom pilot

The deployed entry point is `app.pilot:app`. Clerk identifies accounts; PostgreSQL stores users, classes, submissions, leased jobs, results, practice and audit records. Roles are student, TA, teacher and admin, enforced by the backend. Consent is explicit.

Students join a class, write or paste an essay, submit it, review criterion scores and grounded feedback, then complete personalized practice. Drafts and timer state stay in browser storage scoped to the authenticated user. History is account-scoped; browser drafts are not synchronized across devices. Failed essay jobs release student credits; daily credits reset at midnight Vietnam time.

The pilot accepts the calibrated reference configuration and snapshots the active v1/v2 prompt and calibration settings per submission. Existing v1 benchmark results do not establish v2 accuracy. Practice results do not assign a new IELTS band.

## Local demo

`app.main:app` remains a separate cookie-session research/demo server. It exposes benchmark and assessment options excluded from the classroom pilot. See [documentation](docs/README.md).
