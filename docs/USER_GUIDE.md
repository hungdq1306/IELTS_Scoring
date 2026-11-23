# FogWrite user guide

The application includes a Vietnamese guide at `/guide`, with the exact English button labels used in the UI. It is available before sign-in through the landing page, in the studio sidebar, and from Overview. On mobile, open navigation to reach it.

The guide covers:

- Student sign-in/consent, joining and selecting a class, timed Writing Practice, Check My Essay, submission confirmation and queue recovery.
- Overall and TR/CC/LR/GRA feedback, grounded highlights, complete-set exercises, saved answers, paragraph revision, progress, History and draft recovery.
- Teacher classroom setup, invitation rotation, roster search, member removal, TA assignment and score reviews; assigned TAs have read-only review access.
- Admin account management, operational metrics, failed assessment retry, audit logs and opt-in class quota changes.
- Searchable questions about credits, draft storage, elapsed timers, connectivity, missing exercises and AI score limitations.

Local demo mode is explicitly distinguished from authenticated classrooms. The sample assessment is illustrative and makes no AI request. Real grading/practice requests require the configured AI service and consume provider quota. The local demo uses browser-session history; classroom permissions and credits require the pilot application.

Run `RUN_GUIDE_DEMO.cmd` and open <http://127.0.0.1:8000/guide> for an offline UI demo using the checked-in production bundle. This local-only server never calls an AI provider and explains unavailable actions. It supports sample feedback, topics, the timer and browser drafts; History starts empty. For real local AI grading, stop this preview and run `RUN_FOGWRITE.cmd` on the same port. For authenticated classrooms use `RUN_FOGWRITE_CLERK.cmd` with the existing Clerk/database setup.

Validation: build with `node scripts/build-frontend.cjs`; run `node scripts/fogwrite-guide.test.cjs` for public/demo/student/teacher/admin guide navigation, role content, FAQ search, sample feedback and mobile layout. These browser tests mock API/Clerk; they do not establish live authorization or AI accuracy.
