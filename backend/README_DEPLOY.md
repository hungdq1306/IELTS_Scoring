# FogWrite — hướng dẫn chạy pilot và deploy

Backend cho pilot dùng **Clerk + Neon PostgreSQL + FastAPI**. Frontend React được build trong Docker và phục vụ cùng backend. Vì vậy phương án mặc định **không cần tài khoản Vercel**, không có cookie chéo domain và không cần đặt API URL trong frontend.

Entry point deploy: **`app.pilot:app`**. `app.main:app` vẫn là demo/nghiên cứu cục bộ, không được dùng làm entry point public.

## 1. Những tài khoản và thông tin cần chuẩn bị

| Dịch vụ | Cần tạo/lấy gì | Dùng để làm gì |
|---|---|---|
| [GitHub](https://github.com/) | Dùng repo `hungdq1306/IELTS_Scoring` hiện có | Render lấy source; Actions chạy kiểm tra |
| [Neon](https://console.neon.tech/) | Project PostgreSQL; pooled URL và direct URL | Lưu tài khoản ứng dụng, lớp, bài, queue, kết quả |
| [Clerk](https://dashboard.clerk.com/) | Application; publishable key và issuer | Đăng nhập, session và xác thực danh tính |
| [Google AI Studio](https://aistudio.google.com/) | Project, API key, model được cấp quyền và quota thực tế | Scoring và nhận xét luyện tập |
| [Render](https://dashboard.render.com/) | Kết nối GitHub, tạo Docker Web Service | Chạy backend và frontend cùng origin |
| Nhà cung cấp domain/DNS | Domain bạn sở hữu, quyền thêm DNS records | Clerk production yêu cầu cấu hình domain riêng |
| [Google Cloud Console](https://console.cloud.google.com/) — tùy chọn | OAuth consent screen, Web OAuth client ID/secret | Chỉ cần nếu bật đăng nhập Google trong Clerk production |

Không cần Redis, Celery, Supabase, SMTP riêng hoặc Clerk Organizations. Lớp 30–40 học sinh được quản lý trong PostgreSQL của ứng dụng, không phải tổ chức Clerk.

Clerk production yêu cầu domain bạn sở hữu; Google OAuth production dùng credentials riêng. Vì thế **không cam kết tổng chi phí bằng 0**. Có thể thử local với Clerk development instance trước khi mua/cấu hình domain. Render Free có sleep/restart và không phải dịch vụ luôn sẵn sàng.

## 2. Điều kiện mở pilot

- Pilot này chỉ dành cho **người từ 18 tuổi trở lên**. Giáo viên phải xác nhận đối tượng lớp; checkbox không thay thế việc quản lý tuyển sinh. Không mở lớp dưới 18 tuổi bằng cấu hình Gemini Developer API này.
- Xác nhận cách Google sử dụng dữ liệu: `GEMINI_DATA_POLICY=free_product_improvement` nếu dùng unpaid service, hoặc `paid_no_training` khi đã thực sự cấu hình paid service tương ứng. Đây là thông báo do quản trị viên xác nhận, không phải cơ chế tự phát hiện billing.
- Không yêu cầu học sinh đưa tên, email, số điện thoại hay dữ liệu nhạy cảm vào essay. Redaction email/phone là best effort, không phải công cụ ẩn danh hóa hoàn chỉnh.
- Giáo viên/TA được phân công xem được bài trong lớp. Điểm là AI estimate cho Task 2, không phải IELTS chính thức.

## 3. Chuẩn bị máy và source

Cần Python 3.11+, Git; Node.js 22+ nếu build giao diện trên máy. Docker chỉ cần cho build container hoặc PostgreSQL test cục bộ.

Chạy PowerShell tại thư mục gốc repo:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
$env:PYTHONPATH = 'backend'
```

Nếu đã có `.env`, **giữ nguyên file và bổ sung** biến trong `backend/.env.example`; đừng copy đè mất API key hiện có. Không đưa `.env`, database URL hay API key vào Git hoặc chat.

## 4. Tạo Neon

1. Đăng nhập Neon, tạo project `fogwrite-pilot` và database dành riêng cho pilot.
2. Chọn region gần Render, dùng cùng region nếu có thể.
3. Trong Connect, lấy **pooled endpoint** cho ứng dụng và **direct endpoint** cho migrations. Khi dùng driver asyncpg, dùng scheme `postgresql+asyncpg://`.
4. Gán:

```dotenv
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST-pooler.REGION.aws.neon.tech/DB?sslmode=require
MIGRATION_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST.REGION.aws.neon.tech/DB?sslmode=require
```

Password có ký tự đặc biệt phải được URL-encode. Không đổi Neon sang Supabase transaction pooler mà giữ nguyên cấu hình driver; chúng có khác biệt về prepared statements.

Ứng dụng dùng kết nối ngắn, tối đa 10 session đồng thời trong mỗi process; không giữ session khi gọi AI. **Chạy một process/instance** theo cấu hình bên dưới. Khi cần scale, kiểm tra lại tổng connection budget, limiter và hành vi tải.

## 5. Tạo Clerk và thử local

1. Tạo application `FogWrite`, bật Email verification hoặc Google theo nhu cầu.
2. Ban đầu dùng Development instance. Copy publishable key `pk_test_...` và **issuer/Frontend API URL** từ dashboard/JWT settings. Issuer phải đúng với claim `iss` trong session token.
3. Bổ sung `.env`:

```dotenv
APP_ENV=development
FRONTEND_ORIGIN=http://localhost:5173
CLERK_PUBLISHABLE_KEY=pk_test_REPLACE_ME
CLERK_ISSUER=https://YOUR-INSTANCE.clerk.accounts.dev
```

Không cần `CLERK_SECRET_KEY`: ứng dụng chỉ verify session bằng public JWKS, không gọi Clerk user-management API. Backend tạo user nội bộ khi user đăng nhập lần đầu; không lấy role từ client/JWT metadata.

4. Nếu dùng audience tùy chỉnh trong Clerk token, đặt `CLERK_AUDIENCE` khớp audience đó; nếu không thì để trống.
5. Tạo bảng và seed **một lần**, trước khi chạy web:

```powershell
python -m alembic -c backend/alembic.ini upgrade head
python -m app.manage seed
```

Seed gồm 8 anchors mặc định đã khóa, 3 exercise templates theo ngữ cảnh/rewrite/transfer và đề mẫu. Server không tự chạy migrations khi khởi động. Source cần có `artifacts/dataset_v1/seed.jsonl`.

6. Chạy backend:

```powershell
python -m uvicorn app.pilot:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Terminal khác chạy giao diện:

```powershell
cd frontend
npm install
npm run dev
```

Mở **http://localhost:5173** đúng như `FRONTEND_ORIGIN`. Không dùng lẫn `127.0.0.1` và `localhost` cho frontend: authorized party trong token phải khớp origin.

Nếu chạy prebuilt frontend trực tiếp ở port 8000, đổi `FRONTEND_ORIGIN=http://localhost:8000`, restart backend và mở đúng URL đó.

## 6. Cấu hình Gemini

Trong AI Studio, tạo API key của project dành riêng cho pilot; kiểm tra model khả dụng và RPM/TPM/RPD của **chính project**. Gán:

```dotenv
GEMINI_API_KEY=REPLACE_ME
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_PRACTICE_ANSWER_MODEL=gemini-3.1-flash-lite
GEMINI_MAX_RPM=5
GEMINI_MAX_TPM=100000
GEMINI_MAX_RPD=200
GEMINI_MAX_CONCURRENT=2
GEMINI_DATA_POLICY=free_product_improvement
DAILY_SUBMISSION_LIMIT=5
DAILY_PRACTICE_LIMIT=30
ENABLE_PRACTICE_GEN=true
PRACTICE_ITEMS_PER_SET=4
```

Các con số là **budget cấu hình**, không phải lời khẳng định quota Google cấp. Giảm chúng nếu project thực tế có hạn mức thấp hơn. Nếu model không khả dụng, chọn model trong allowlist `providers/gemini.py` và chạy regression trước khi đổi cho lớp.

Budget áp dụng chung cho các worker và tồn tại trong PostgreSQL sau restart. Mỗi API attempt, kể cả retry, đều phải reserve quota. TPM dùng giới hạn ước lượng bảo thủ theo số byte input/schema + 8.192 output tokens; có thể chậm hơn quota thực tế. Daily provider budget theo ngày Pacific; quota học sinh là **rolling 24 giờ**.

40 bài với 5 RPM cần khoảng 8 phút ngân sách call cho scoring, chưa kể latency/retry. Practice chỉ sinh khi học sinh yêu cầu; có thêm generate + review và một call model nhỏ khi nộp cả bộ. Không hứa tất cả có kết quả ngay lập tức.

## 7. Cấp quyền giáo viên và tạo lớp

1. Giáo viên đăng nhập trên website. Trong Clerk Dashboard → Users, lấy **User ID** dạng `user_...`, không phải email.
2. Trên máy quản trị đã cấu hình đúng database:

```powershell
$env:PYTHONPATH = 'backend'
python -m app.manage grant-role --clerk-user-id user_REPLACE_ME --role teacher
```

3. Refresh trang. Trong panel FogWrite class pilot, tạo lớp `YP03`. Copy join code ngay và gửi riêng cho học sinh. DB chỉ lưu hash code; không thể xem lại code cũ. Mặc định code hết hạn sau 7 ngày và có 45 lượt tham gia.
4. Học sinh đăng nhập, xác nhận điều kiện pilot, nhập join code. Học sinh chỉ được nộp bài sau khi có membership đang active.
5. Cấp role TA qua CLI rồi phân công TA vào lớp bằng API teacher. TA không được sửa điểm hoặc thay anchors/templates. Role `admin` chỉ cấp qua trusted CLI tương tự.

API phát triển có tài liệu ở `http://localhost:8000/docs`. Production tắt `/docs` và `/openapi.json`. Backend có API quản lý roster/override/anchors/templates; giao diện quản trị đầy đủ chưa nằm trong MVP này. Có thể quản lý qua PowerShell/Postman với Bearer token lấy từ phiên Clerk của chính giáo viên, không lưu token trong tài liệu.

Ví dụ roster:

```powershell
# $teacherToken là token ngắn hạn của chính bạn; không commit hoặc chia sẻ.
$headers = @{ Authorization = "Bearer $teacherToken" }
Invoke-RestMethod 'https://YOUR-DOMAIN/api/teacher/classes' -Headers $headers
Invoke-RestMethod 'https://YOUR-DOMAIN/api/teacher/classes/CLASS_ID/members' -Headers $headers
$membership = @{user_id='INTERNAL_USER_UUID'; role='ta'; active=$true} | ConvertTo-Json
Invoke-RestMethod 'https://YOUR-DOMAIN/api/teacher/classes/CLASS_ID/members' -Method Put -Headers $headers -ContentType 'application/json' -Body $membership
```

## 8. Kiểm thử trước deploy

Test DB phải tên **`fogwrite_test`**. Test sẽ reset dữ liệu trong DB này; không trỏ vào database pilot.

```powershell
docker compose -f compose.pilot-test.yml up -d --wait
$env:TEST_DATABASE_URL='postgresql+asyncpg://fogwrite:local_test_only@127.0.0.1:55439/fogwrite_test'
$env:PYTHONPATH='backend'
python -m pytest -v backend/tests/test_concurrency_and_guardrails.py
python -m pytest -q backend/tests -m 'not live'
```

Không có `TEST_DATABASE_URL` thì suite dùng SQLite cho unit checks; kết quả đó **không chứng minh PostgreSQL concurrency**. Gemini được mock, không tốn API quota. GitHub Actions kiểm tra PostgreSQL và Docker image khi bạn push source.

## 9. Clerk production, domain và Google OAuth

1. Chuẩn bị domain, ví dụ `fogwrite.example.com`, và quyền quản lý DNS.
2. Clerk → tạo Production instance. Khai báo domain thực tế; thêm các CNAME records chính Clerk yêu cầu và chờ xác minh/TLS.
3. Copy **`pk_live_...`** và issuer production, ví dụ `https://clerk.example.com`. Không dùng issuer development cùng live key.
4. Nếu dùng Google login: tạo Google Cloud project, cấu hình OAuth consent screen và Web OAuth Client. Copy **chính xác** redirect URI từ Clerk Dashboard sang Google; nhập Client ID/Client Secret vào Clerk. Không đưa Google client secret vào frontend/repo.
5. Nếu OAuth app đang ở chế độ testing thì thêm email của đúng người tham gia vào test users hoặc hoàn tất các bước publishing/verification Google yêu cầu.
6. Không cần bật Clerk Organizations hoặc tính năng allowlist trả phí. Backend membership mới là cổng sử dụng tính năng chấm; có tài khoản Clerk chưa đồng nghĩa được tham gia lớp.

## 10. Deploy Render

1. Review `git diff`, commit/push các thay đổi bạn muốn đưa lên repo. Không commit `.env`, logs, database hoặc `.cache`.
2. Render → New → Web Service → kết nối GitHub repo này.
3. Chọn Docker, Dockerfile **`backend/Dockerfile`**, build context **repo root `.`**. Không đặt Root Directory thành `backend`, vì image cần build frontend và copy frozen anchors.
4. Chọn region gần Neon. Có thể dùng Free để thử có giám sát; lớp cần ổn định nên dùng instance luôn chạy.
5. Health check: **`/ready`**. Không dùng endpoint gọi Gemini làm health check.
6. Thêm environment variables từ `backend/.env.example`, tối thiểu:

| Biến | Giá trị production |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | Neon pooled URL, SSL |
| `MIGRATION_DATABASE_URL` | Neon direct URL, SSL |
| `FRONTEND_ORIGIN` | `https://fogwrite.example.com`, không có path/trailing slash |
| `CLERK_ISSUER` | Issuer production |
| `CLERK_PUBLISHABLE_KEY` | `pk_live_...` |
| `GEMINI_API_KEY` | API key server-side |
| `GEMINI_DATA_POLICY` | Policy bạn đã xác nhận với project |
| `GEMINI_MODEL`, `GEMINI_PRACTICE_ANSWER_MODEL` | Model đã kiểm tra quyền truy cập |
| `GEMINI_MAX_RPM`, `GEMINI_MAX_TPM`, `GEMINI_MAX_RPD` | Budget phù hợp quota thực tế |

7. Trước khi nhận traffic, chạy migrations + seed từ máy local với **đúng DB production** theo bước 5. Render Free không có shell; không phụ thuộc vào shell Render hoặc `preDeployCommand` trả phí.
8. Deploy image. Lệnh mặc định đã bind `0.0.0.0:$PORT`, `--workers 1` và tắt access log.
9. Render → Custom Domains → thêm domain, thêm DNS theo hướng dẫn Render và chờ HTTPS.
10. Mở đúng custom domain; xác nhận sign-in, join, submit, poll và restore từ History.

`render.yaml` là cấu hình Blueprint thay thế cho thao tác thủ công. Nó không tự tạo Neon/Clerk/API keys/domain hoặc chạy migration cho bạn.

Nếu chưa có domain, tiếp tục thử local. Không gọi một deploy dùng Clerk test key là production hoàn chỉnh.

## 11. Checklist mở lớp

- `/health` và `/ready` trả 200; `/api/benchmarks` và `/api/datasets` trả 404.
- Đăng nhập bằng **hai tài khoản khác nhau**; tài khoản B không xem được bài/job/practice của A.
- Thử giáo viên, TA và student; TA chỉ đọc lớp đã được phân công.
- Thu hồi membership rồi kiểm tra học sinh không đọc/nộp bài mới được.
- Chấm 1 bài thật bằng đúng model/key production; kiểm tra feedback, rounding và phí/quota.
- Sinh practice, trả lời toàn bộ, submit; kiểm tra model nhỏ trả nhận xét và rewrite chấp nhận cách diễn đạt hợp lệ.
- Refresh khi bài đang queued rồi mở từ History; không nộp trùng.
- Test double-click/retry và lượt nộp thứ 6; xác nhận queue không mất sau restart.
- Kiểm tra login Google/email trên desktop và điện thoại, không lỗi CSP/cookie.
- Xác nhận privacy, adult-only enrollment, quyền truy cập dữ liệu và bản sao lưu.

Các test tự động không thay thế bước đăng nhập Clerk live, Google OAuth, Gemini thật và build/deploy image Linux. Không gọi kiểm thử mock là bằng chứng chất lượng chấm.

## 12. Vận hành, retention, backup và rollback

- Quota student rolling 24h; attempts practice được giới hạn theo submission và theo ngày.
- Job có lease/heartbeat/fencing. Gọi AI có thể lặp khi crash sau khi provider đã xử lý; DB chỉ chấp nhận kết quả của lease hiện hành. Không cam kết exactly-once billing.
- Practice lỗi không xóa assessment. Lỗi có code an toàn; không log essay, raw model output hoặc token theo mặc định.
- Cleanup writing quá `RETENTION_DAYS` chạy theo giờ khi web worker đang hoạt động. Instance ngủ thì cleanup chạy khi service hoạt động lại; không cam kết xóa đúng phút thứ 30 ngày.
- Kiểm tra/xóa thủ công:

```powershell
python -m app.manage purge-expired
python -m app.manage purge-expired --apply
python -m app.manage delete-writing --clerk-user-id user_REPLACE_ME
python -m app.manage delete-writing --clerk-user-id user_REPLACE_ME --apply
```

- Delete-writing xóa bài, kết quả, practice và jobs liên quan; giữ auth/membership/audit. Xóa tài khoản Clerk cần quản trị viên thực hiện riêng theo quy trình của lớp.
- Khóa/mở quyền truy cập ứng dụng: `python -m app.manage set-active --clerk-user-id user_REPLACE_ME --active false` (mở lại bằng `true`). Không cần chờ JWT hết hạn để áp dụng trạng thái khóa trong DB.
- Nếu đề trùng đúng câu hỏi của anchor, bản pilot loại anchor cùng đề khỏi ví dụ gửi model và ghi phiên bản cấu hình riêng; vẫn chặn việc sao chép bài anchor. Cấu hình này và anchors/offsets của giáo viên là biến thể cần đánh giá, không tự thừa hưởng benchmark của baseline 8 anchors.
- Trước thay đổi schema hoặc buổi pilot quan trọng, dùng Neon backup/restore theo plan hiện có hoặc `pg_dump` từ direct endpoint. Lưu backup ở nơi riêng tư và thử restore vào database khác. Không coi tính năng backup free tier là vô hạn.
- Khi deploy lỗi, rollback image trên Render; **không tự downgrade DB** khi chưa kiểm tra migration tương thích. Giữ backup và migrations forward-only cho dữ liệu người dùng.
- Render Free có thể sleep/restart bất cứ lúc nào. UptimeRobot chỉ hữu ích để theo dõi availability, không bảo đảm worker luôn chạy hoặc thay thế paid compute.

## 13. Tùy chọn Vercel

Chỉ tách frontend sang Vercel khi cần. Khi đó dùng reverse proxy `/api/*` từ Vercel tới Render, `FRONTEND_ORIGIN` là origin frontend thật, Clerk production khai báo đúng domain frontend; cấu hình CSP cho frontend ở Vercel. Repo hiện chuẩn bị phương án cùng-origin trên Render để giảm tài khoản và bước triển khai.

## Tài liệu chính thức đã đối chiếu

- [Clerk production: domain, OAuth, DNS](https://clerk.com/docs/guides/development/deployment/production)
- [Clerk JavaScript quickstart](https://clerk.com/docs/js-frontend/getting-started/quickstart)
- [Gemini API terms: age and data use](https://ai.google.dev/gemini-api/terms)
- [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Neon connection pooling](https://neon.com/docs/connect/connection-pooling)
- [Render Free limitations](https://render.com/docs/free)
