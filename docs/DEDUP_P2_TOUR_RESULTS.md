# Kết quả triển khai FogWrite — 24/11/2026

Nhánh: `feat/fogwrite-tour-local-demo`. Không commit, push hoặc sửa cấu hình bảo mật.
Giữ nguyên `.dockerignore` và `docs/LOCAL_DEMO_CLEANUP.md` có sẵn trước lượt làm việc.

## Những điểm đã phản biện và sửa trong plan

- Trạng thái DB là `COMPLETED`, không phải nhãn quản trị `DONE`.
- Cache xét cả tài khoản, lớp, toàn bộ đề/bài, model, thinking budget và snapshot cấu hình chấm. Chỉ đổi CRLF thành LF; giữ nguyên đoạn văn và khoảng trắng nội bộ để tránh tái sử dụng điểm cho cấu trúc bài khác.
- Không đoán cấu hình lịch sử: bài cũ có `content_hash = NULL` tiếp tục chấm mới. Kết quả mới sau migration có thể tái sử dụng; thay đổi ngữ cảnh chấm tạo cache miss. Khi thay đổi thuật toán/rubric ngoài snapshot, cần tăng `cache_revision`.
- Giữ hợp đồng phản hồi điểm hiện có. Cache trả 200, `reused: true`, thông báo tiếng Việt và nội dung nguồn để gạch chân đúng bài cũ; không tạo bài/job chấm mới, không trừ lượt. Nội dung giống hệt đang chờ được nối lại. Bảng mã yêu cầu giữ quy tắc idempotency cho cả hai trường hợp.
- Bài tập nằm trong JSON: bổ sung bảng ánh xạ ID đến bài viết, backfill bằng migration, và lưu cùng giao dịch hoàn tất sinh bài tập. Giữ quyền của chủ bài; không tự mở quyền làm bài cho teacher/TA/admin.
- Đáp án nháp và đáp án đã nộp đã có sẵn trong DB. Hash được suy ra từ hai bản này; phản hồi cũ không còn hợp lệ khi đáp án khác. Nháp trên trình duyệt có hash bản gốc để khôi phục an toàn sau tải lại.
- Ghi việc dùng gợi ý tại thời điểm nộp, có đối chiếu thời gian cho dữ liệu lịch sử. Thứ tự lần thử đầu dựa vào thời điểm nộp.
- Tour vốn đã có đúng thứ tự sáu bước. Giữ thứ tự, bổ sung điểm nhấn đề → bài → nộp trong cùng bước; 8 giây đọc sau hoạt cảnh, hover/input/ẩn tab tạm dừng. Tour vẫn là dữ liệu minh họa, không gọi AI hoặc sửa dữ liệu thật.
- Sửa mock theo module thực tế, chặn HTTP trong kiểm thử Task 1; unittest discovery dùng `-t .`. CI có job riêng cài dependency Task 1, chạy cả hai test runner, thêm tour typecheck và kiểm thử khôi phục giao diện.

## Kiểm chứng

- Toàn bộ Python không gọi AI thật: **118 passed, 1 deselected**, exit 0. Một cảnh báo deprecation của thư viện TestClient hiện có.
- Task 1: **18 passed** với pytest; **18 passed** với unittest discovery. Guard chặn outbound HTTP trong bộ kiểm thử.
- Frontend unit: **19 passed**; tour TypeScript, Vite build và build offline đạt.
- Browser: kiểm tra 5 vai trò × 4 kích thước, 3 luồng đổi tài khoản/lớp; help ở 5 trạng thái × 2 kích thước; smoke sáu màn hình ở 2 kích thước đạt.
- Kiểm thử mới trên browser ở 1440px và 390px: mở bài FAILED → sửa/nộp lại; cache khi còn 0 lượt; sửa đáp án và tải lại không hiện điểm cũ, đạt. Các API trong kiểm thử này là fixture offline.
- Tour được kiểm tra với dữ liệu build và máy chủ local, gồm Student/Teacher ở 1440px/390px, nhập liệu không bị ghi đè, giữ nháp, reduced motion, nhịp 8 giây và hover pause. Kiểm thử bổ sung xác nhận câu được sửa nằm trong bài mẫu bước trước.
- Sửa thêm lỗi thẻ hướng dẫn tràn màn hình khi đổi nhanh sang bước có nội dung dài: đo lại chiều cao trước khi vẽ.

## Migration và giới hạn

Migration `0005_content_cache` thêm hash, bảng mã yêu cầu và ánh xạ bài tập.
`alembic upgrade head --sql` cho PostgreSQL sinh SQL thành công, exit 0.
Chưa áp migration lên cơ sở dữ liệu thật hoặc kiểm tra thực thi PostgreSQL: Docker engine trên máy không hoạt động. Kiểm thử giao dịch hiện tại dùng SQLite tách biệt; không thay đổi DB đang dùng.
CI đã được cập nhật trong repo; chưa có lần chạy GitHub Actions từ thay đổi chưa push.
Không gọi Gemini thật, không đánh giá lại chất lượng chấm AI, không công bố accuracy/F1/MAPE Task 1 do người kiểm duyệt.

## Các file thay đổi

Backend:
- `backend/app/models.py`
- `backend/app/routers/pilot.py`
- `backend/app/worker.py`
- `backend/app/services/submission_cache.py` (mới)
- `backend/alembic/versions/0005_content_cache.py` (mới)

Frontend:
- `frontend/src/fogwrite.jsx`
- `frontend/src/pilot-api.js`
- `frontend/src/practice-batch.jsx`
- `frontend/src/components/StudioScreens.jsx`
- `frontend/src/components/tour/TourProvider.tsx`
- `frontend/src/components/tour/VirtualCursorOverlay.tsx`
- `frontend/src/components/tour/TourStage.tsx`
- `frontend/src/components/tour/TourSampleFeedbackModal.tsx`
- `frontend/src/components/tour/sample-data.ts` (mới, nội dung nguồn dùng chung)
- `frontend/src/components/tour/steps.ts`
- `frontend/src/components/tour/tour.css`
- `frontend/dist/app.js`, `frontend/dist/app.css`, `frontend/dist/index.html` (sinh lại)

Kiểm thử và CI:
- `backend/tests/test_cache_and_recovery.py` (mới, 16 trường hợp)
- `backend/tests/test_concurrency_and_guardrails.py`
- `backend/tests/test_rbac_and_ai_v2.py`
- `benchmarks/task1_extraction/test_pipeline.py`
- `scripts/fogwrite-recovery.test.cjs` (mới)
- `scripts/fogwrite-tour.test.cjs`
- `tests/test_dataset_integrity.py`
- `.github/workflows/pilot.yml`

Tài liệu: `docs/DEDUP_P2_TOUR_PLAN.md` và báo cáo này.

## Demo local

- Học sinh: http://127.0.0.1:5174/?tour=student
- Giáo viên: http://127.0.0.1:5174/?tour=teacher

Đây là demo giao diện có nhãn minh họa, không gọi Gemini. Backend cache/quyền/giao dịch được kiểm chứng bằng HTTP với DB tách biệt trong bộ kiểm thử, không phải hệ thống PostgreSQL đã triển khai.
