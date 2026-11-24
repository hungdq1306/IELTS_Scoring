# Interactive cursor tours

## Demo đang chạy

- Student: <http://127.0.0.1:5174/?tour=student>
- Teacher: <http://127.0.0.1:5174/?tour=teacher>
- Vite thật ở 5174; API preview chỉ đọc ở 8001. Server 5173 có sẵn không bị dừng.
- Không cần đăng nhập cho hai link demo. Tạo lớp/join/override và feedback trong tour
  là dữ liệu minh họa có nhãn, không gửi bài, gọi Gemini hoặc trừ credit thật.

## Khớp với code hiện tại

Frontend chính dùng JSX; module tour có sẵn dùng TSX và được giữ nguyên định dạng.
Route Overview là `/overview`, không phải landing `/`. Luồng Student có 6 bước:
`/overview` → `/classes` → `/check` → `/assessment` → `/practice` → `/history`.
Luồng Teacher có 4 bước: tạo/mời lớp → roster → bài viết/override ở `/classes`,
rồi xem credit ở `/check`. `/skill-practice` là drill sau assessment, độc lập với
trang viết 40 phút `/practice`. Mã mẫu `FOG1XXXX` có định dạng tám ký tự của app.
Quota 3/20 và reset 00:00 Việt Nam đã đối chiếu với `backend/app/entitlements.py`;
đây là mặc định có thể được quản trị viên thay đổi.

## Khởi động lại

Hai terminal, từ repository root. Không chạy lại nếu các cổng đã có server:

```powershell
# Terminal 1: API preview chỉ đọc; không phải backend chấm bài thật.
$env:FOGWRITE_PREVIEW_PORT='8001'
node scripts/preview-guide.cjs
```

```powershell
# Terminal 2: Vite dev server.
$env:FOGWRITE_API_PROXY='http://127.0.0.1:8001'
npm run dev --prefix frontend -- --port 5174
```

App thật vẫn mặc định proxy FastAPI ở `127.0.0.1:8000` khi không đặt
`FOGWRITE_API_PROXY`. Không sửa `.env` hoặc cấu hình xác thực để chạy demo này.

The floating **Hướng dẫn sử dụng** button opens a role chooser. Tours normally advance about 4.5 seconds after the current target appears; Next/Back or interaction pauses playback. Auto-play resumes it. Escape/Skip restores the original route and focus. Reduced-motion preference disables animation and initial playback. A hidden browser tab pauses playback.

New authenticated users see onboarding once after consent. Completion/skip is stored under `fogwrite:tour_done:${backendUserId}`. Demo/anonymous sessions do not write completion flags. Switching accounts closes an active tour. Query links launch either presentation without granting that account any role.

The tour renders an explicitly labeled sandbox using the actual Overview and EssayEditor components, plus isolated class/roster/history examples. It does not create classes, join classes, save overrides, write drafts, send essays, or call an AI provider. The feedback example shows Overall 6.5, TR/CC 6.5, LR 6.0, GRA 7.0. Its teacher-style coaching is clearly illustrative, not attributed as actual teacher feedback. Existing drafts remain in the application state while the sandbox is mounted.

`/practice` means timed essay writing. Personalized drills are a separate post-assessment flow at `/skill-practice`; the tour explains this distinction and shows a sample drill alongside the timed editor.

## Targets

| Screen | Components / targets |
| --- | --- |
| Overview / account | `Overview`, `UserProfileMenu`: `credits-badge` |
| Classes | `ClassesScreen`: `join-class-input`, `teacher-create-class`, `teacher-invite-controls`, `teacher-class-roster`, `teacher-class-submissions` |
| Check My Essay | `EssayEditor`: `essay-workspace` |
| Assessment sample | `TourSampleFeedbackModal`: `sample-band-scores`, `sample-error-highlight` |
| Writing Practice | `EssayEditor`: `practice-workspace` |
| History | App history and sandbox journal: `writing-journal` |

`TourProvider.tsx` handles cross-route history events, observer-based target readiness (2.5-second timeout), autoplay, completion and cleanup. `VirtualCursorOverlay.tsx` observes target size/scroll, animates a custom SVG cursor, shows click rings and positions a keyboard-accessible step card. Only controls explicitly marked `data-tour-preview="click"` inside `data-tour-sandbox` can receive simulated clicks.

## Build và kiểm thử

```powershell
npm run typecheck:tour --prefix frontend
npm run build --prefix frontend
npm run test --prefix frontend
$env:FOGWRITE_TOUR_BASE_URL='http://127.0.0.1:5174'
$env:FOGWRITE_TOUR_LIVE='1'
npm run test:tour --prefix frontend
```

Đã cài các dependency được khai báo trong workspace và kiểm tra bằng Vite 7.2.2
thật. Launcher nhận cả dependency hoisted ở `node_modules/` của workspace và
`--port` tùy chọn. Esbuild fallback chỉ dành cho checkout offline; không được coi
là kiểm tra TypeScript. `typecheck:tour` dùng TypeScript với React 19 types cho
module TSX; không tuyên bố typecheck toàn bộ code JSX hiện có. Không thêm thư viện
runtime tour; chỉ thêm công cụ kiểm tra type trong devDependencies.

Playwright tour test chạy Student/Teacher ở 1440 và 390 px: điều hướng, cursor,
spotlight, sample correction tự mở, back/next/skip/replay, auto-play, reduced motion,
per-user completion và giữ draft. Live mode dùng Vite/API preview thật cho các
luồng anonymous; nhánh auth dùng fixture Clerk/account riêng. Có kiểm tra HTTP lỗi
ở local origin và không có API mutation do tour. Mã mời ngừng gõ mẫu khi người dùng
focus/tự nhập; editor có lớp mẫu và bài >250 từ; timer mẫu bắt đầu khi vào practice.

HTTP `/`, `/overview`, `/classes`, hai query launch và `/api/auth/config` đã được
kiểm tra trên server live. Preview server hỗ trợ refresh/deep link của tất cả
route, nhưng không cung cấp chức năng lớp học hoặc chấm AI thật.

Lưu ý khi có build song song: fixture auth đọc một snapshot build riêng bằng
`FOGWRITE_TOUR_ASSET_ROOT`; tránh việc một build khác thay `frontend/dist` giữa
lượt test. Các luồng guest trong live mode vẫn tải trực tiếp Vite server.

Các micro-action mới: Step 3 đưa con trỏ tới lớp mẫu sau khi xem editor; Step 5
chọn đáp án mẫu và mở feedback; Teacher Step 3 đưa con trỏ xuống phần override.
Input pause chạy sau React onChange để việc tắt auto-play không khôi phục nhầm
ký tự cũ trong ô đang nhập. Bài mẫu và confirm dialog luôn ghi rõ không gửi AI.

## Kết quả xác minh của lượt này

- Vite 7.2.2 build thật và `typecheck:tour`: exit 0.
- Unit/UI: 19/19 pass; test build-assets hỗ trợ cả Vite hash assets và esbuild.
- Tour Playwright live: Student/Teacher tại 1440/390 px pass; thao tác nhập mã khi
  auto-play đang bật giữ nguyên nội dung và tự pause; auth completion/draft/replay/
  reduced-motion fixtures và tự chuyển bước đều pass. Không có mutation do tour
  hoặc HTTP lỗi trên local origin trong các luồng này.
- Đã kiểm tra screenshot feedback desktop và override teacher mobile khi animation
  ổn định. Ảnh kiểm tra nằm ở `.cache/tour-ui/`.
- Bộ `test:auth` rộng hơn bị gián đoạn khi một build khác thay `frontend/dist`
  giữa lượt chạy; không tính lượt đó là pass. Tour auth fixtures đã pass với snapshot
  riêng. Chưa kiểm thử đăng nhập Clerk thật hoặc class CRUD trên FastAPI thật.
- Working tree đã có nhiều thay đổi của các phần khác; không gom chúng thành commit.
