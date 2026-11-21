# FogWrite authentication UX handoff

## Root cause

`frontend/src/pilot-bootstrap.jsx` created a second DOM container (`pilot-account-root`) before the main root and mounted PilotAccount with its own React root. The real FogWrite application rendered separately underneath. Its public Sign in button had no shared account state, so it could remain visible while the separate panel displayed a teacher session.

The bootstrap import and bootstrap file are removed. The main root now wraps App in AuthProvider, using the existing Clerk JavaScript singleton. The previous PilotAccount source and its local stylesheet were left unmounted in the working tree to preserve concurrent backend integration edits; neither is imported into the production bundle.

## Delivered structure

- One Clerk-backed authorization context with loading, visitor, ready, expired and error states. Backend `/api/auth/me` supplies the role; Clerk supplies display name, email and avatar. No role comes from client metadata or a role switcher.
- A bottom-anchored UserProfileMenu with initials fallback, profile, official Clerk account settings, classes, authorized administration and official sign-out. Outside click, Escape, menu arrow keys, Home/End and visible focus are supported. Sign-out preserves the essay draft and removes stale assessment recovery state.
- Signed-in users see the application shell, including on `/`. Public visitors see only the marketing page or a deliberate public sample view. Protected requests are delayed until account initialization and required consent are complete. Invalid runtime configuration fails closed.
- The sidebar scrolls independently on short desktop screens. Tablet/mobile uses a navigation drawer, a backdrop, Escape handling and an inert main surface while the drawer is open. Profile remains accessible at the drawer bottom.
- `/classes` and `/join` provide real classroom create/join/list flows. Teacher/admin can review supported membership and essay data, rotate/copy invites, remove students, assign an already-authorized TA and review scores using existing routes. Repeated form submission is guarded immediately.
- `/profile` presents Clerk identity and backend role; `/admin` retains the existing authorized account/credit/settings APIs. Student direct access to the admin view does not render administrative tools.
- Consent is a dedicated, explicitly unchecked participation step, persisted via the existing consent endpoint. Decline signs out. Required consent is never granted automatically by mounting or refreshing the page.
- Existing essay, timer, autosave, batch practice and scoring request contracts are retained. Disabled submission now explains which input is missing. Browser history and assessment restoration after refresh remain supported.

## API contracts reused

| Purpose | Existing endpoint |
| --- | --- |
| Runtime configuration | GET /api/auth/config |
| Backend identity/role/classes | GET /api/auth/me |
| Persist adult/privacy acceptance | POST /api/auth/consent |
| Student join | POST /api/classes/join |
| Teacher/TA/admin class list | GET /api/teacher/classes |
| Create class | POST /api/teacher/classes |
| Rotate invite | POST /api/teacher/classes/:id/rotate-code |
| Members and class work | GET /api/teacher/classes/:id/students and /submissions |
| Membership changes | Existing assign-ta and remove-student routes |
| Score review | PATCH /api/teacher/assessments/:id/override |
| Administration | Existing /api/admin/users, /overview, /settings |

Account Settings uses Clerk.openUserProfile(), Sign Out uses Clerk.signOut(), and session changes use the existing addListener API. Reference: https://clerk.com/docs/js-frontend/reference/objects/clerk .

## Files

Created:
- frontend/src/auth-context.jsx
- frontend/src/components/UserProfileMenu.jsx
- frontend/src/components/AccountScreens.jsx
- frontend/src/components/account-shell.css
- scripts/fogwrite-auth.test.cjs
- this handoff and test screenshots under artifacts/auth-ui

Updated:
- frontend/src/fogwrite.jsx: one auth-aware root, request gating, routing and restoration
- frontend/src/components/StudioScreens.jsx: unified shell/profile/drawer, editor status
- frontend/src/routes.js: classes, join, profile, admin paths
- frontend/src/pilot-auth.js: retryable initialization and validated runtime mode
- frontend/src/pilot-api.js: unauthorized event/status handling and current class-selection wording
- scripts/fogwrite-ui.test.cjs and scripts/fogwrite-smoke.cjs: adapt existing regression checks
- frontend/dist: rebuilt production JS/CSS/HTML

Removed: frontend/src/pilot-bootstrap.jsx.

Backend files that were already being edited elsewhere in this workspace were not changed by this UI task. Deployment settings, database migrations, scoring and the IELTS rubric were not changed or deployed by this task.

## Verification

- Production esbuild bundle: PASS.
- Existing model/component checks: 16/16 PASS, including the batch practice regressions already present in the workspace.
- Browser integration with mocked Clerk and contract-shaped API responses: visitor/student/teacher/admin at 1440, 1024, 768 and 390 px: 16/16 PASS.
- Covered: no secondary root/panel; visitor makes no protected requests; signed-in pages have no redundant Sign in; profile anchoring; menu open/Escape; account-settings invocation; sign-out; teacher/admin create with duplicate-submit guard; class detail; student invalid/valid join; persistence after reload; consent persistence; expired-session fallback and retry; saved-assessment restoration on a signed-in refresh.
- Screenshots contain test identities and fixture class data only. They are not production-account screenshots.
- JS module syntax and git whitespace checks: PASS.
- Standalone ESLint and full TypeScript checking were not run: the repository has no configured lint/type-check scripts or installed CLI for these. The production build parses JSX/TSX; it is not a substitute for a full type check.

## Remaining dependencies and untested scenarios

- Real Clerk sign-in, session cookies and live backend permissions were not exercised. The browser integration uses intercepted responses and never sends credentials or essays to production.
- Backend role/ownership checks remain authoritative and unchanged. Actual teacher/admin permissions must still be verified against the deployed backend with authorized test accounts.
- The membership API supplies IDs, role and active state but no names/emails. The UI shows neutral member labels and explicitly explains that limitation. Named roster search needs a backend response addition; no unsupported endpoint was invented.
- Clipboard copying is wired to navigator.clipboard and reports failures, but was not checked against the production browser clipboard policy.
- There is no deployment in this change. Publish the rebuilt source through the existing deployment process when ready.

## Screenshots

- [Public landing](../artifacts/auth-ui/public.png)
- [Student classes/profile menu](../artifacts/auth-ui/student.png)
- [Teacher classes/profile menu](../artifacts/auth-ui/teacher.png)
- [Mobile student drawer/profile](../artifacts/auth-ui/mobile-student.png)
