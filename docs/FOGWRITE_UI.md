# FogWrite UI

## Entry and routes

`frontend/src/fogwrite.jsx` is the sole React entry, wrapped in `AuthProvider`. `auth-context.jsx`, `UserProfileMenu.jsx`, `AccountScreens.jsx` and `AdminScreen.jsx` provide Clerk identity and role-aware screens.

| Route | Purpose |
| --- | --- |
| `/`, `/overview` | Public landing or signed-in overview |
| `/topics`, `/practice` | Original prompt selection and timed writing |
| `/check` | Submit an existing Task 2 question and essay |
| `/assessment`, `/assessment/:criterion` | Grounded assessment and criterion details |
| `/skill-practice` | Personalized complete-set practice |
| `/history` | Account-scoped submissions |
| `/classes`, `/join` | Class membership and invitations |
| `/profile`, `/admin` | Account profile and authorized administration |

Clerk pilot mode offers the supported calibrated assessment configuration. Additional research configurations are available only in local demo mode. Sample feedback is explicitly illustrative and does not call Gemini.

Drafts use `fogwrite:draft:${userId}` with owner, mode, class, prompt, essay and countdown metadata. Continue draft restores `/practice` or `/check`. History requests and practice storage are account-scoped. In-flight restore/evaluate results from earlier sessions are discarded. Assessment renders a submitted snapshot. No cross-device draft synchronization is claimed.

The profile menu exposes identity, credits, classes, Clerk account settings and sign-out. Teacher/admin class management and TA read-only review follow backend permissions. Admin screens provide account filters/confirmation, safe settings, jobs/retry, usage and activity filters.

## Build and verification

From the repository root, `npm run build` runs Vite. An offline alternative is `node scripts/build-frontend.cjs` with `FOGWRITE_NODE_MODULES` pointing to installed esbuild/React dependencies. Both use the same source entry. `frontend/dist/` remains tracked for local startup without Node; Docker rebuilds it.

Run `node --test scripts/fogwrite-model.test.mjs scripts/fogwrite-ui.test.cjs`, `node scripts/fogwrite-auth.test.cjs` and `node scripts/fogwrite-smoke.cjs --offline`. Browser tests mock Clerk/API responses; see [verification](VERIFICATION.md) for their limits. PNG mascots are mapped in [MASCOT_ASSETS.md](MASCOT_ASSETS.md).
