# DiSản Lens — Chụp một chứng tích, mở một câu chuyện

Website học tập dành cho học sinh và khách tham quan: chụp/tải ảnh thật, kiểm tra chất lượng, nhận diện hiện vật, đọc câu chuyện ba tầng, nghe thuyết minh và trả lời câu hỏi ngắn từ hồ sơ dữ liệu.

## Kiến trúc website

```text
frontend/ (Next.js + TypeScript + Tailwind)
  → multipart file → FastAPI /api/v1
    → kiểm tra kích thước, nội dung ảnh, chất lượng
    → src/clip/encoder.py (OpenCLIP được tải một lần/process)
    → src/vector_store/pinecone_client.py (index hiện có)
    → lấy dư vector → gom location.id → confidence gate
    → HeritageRepository → Supabase hoặc JSON gốc
    → hiện vật / câu chuyện / câu hỏi / phản hồi
```

CLIP mã hóa ảnh; JSON không được đưa trực tiếp vào CLIP. Pinecone giữ embedding và metadata tìm kiếm; nội dung đầy đủ được đọc lại từ repository theo ID. Website không tạo index, đổi namespace hoặc index lại ảnh. Index hiện dùng là `di-san-lens`, namespace `heritage-images-v1`, model `ViT-B-32:laion2b_s34b_b79k`, 512 chiều, cosine.

## Chạy nhanh website trên Windows

Yêu cầu Python 3.12 (đã kiểm thử), Node.js 20.9 trở lên; môi trường phát triển này dùng Node.js 24 LTS. Next.js yêu cầu Node >=20.9 theo [tài liệu cài đặt chính thức](https://nextjs.org/docs/app/getting-started/installation). Không cần bật PowerShell activation để dùng virtualenv.

Từ thư mục gốc, cài backend và chỉ tạo `.env` nếu chưa có:

```powershell
py -3.12 -m venv .venv
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m src.api
```

Trong `.env`, điền khóa Pinecone hiện có. Để trống `SUPABASE_URL` và `SUPABASE_SERVICE_ROLE_KEY` để dùng JSON. API: `http://127.0.0.1:8000`; OpenAPI: `http://127.0.0.1:8000/docs`.

Mở terminal thứ hai:

```powershell
cd frontend
npm ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

Website: `http://localhost:3000`. `frontend/.env.local` chỉ cần `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`. Khóa Pinecone và Supabase service-role chỉ nằm trong `.env` ở gốc.

Nếu máy chưa cài Node, bản portable đã tải trong workspace có thể được dùng bằng cách chạy từ thư mục gốc:

```powershell
$nodeDir = (Resolve-Path '.tools/node-v24.20.0-win-x64').Path
$env:Path = "$nodeDir;$env:Path"
cd frontend
npm.cmd run dev
```

Không cần tải lại dependencies nếu `.venv` và `frontend/node_modules` đã sẵn có. Khi chạy production local, dùng `npm run build` rồi `npm run start`. Backend chạy một worker để tái sử dụng model và request context phản hồi.

## Luồng sử dụng và dữ liệu lịch sử

- Mở camera sau hoặc chọn JPG/PNG/WEBP, xem trước rồi bấm phân tích. Camera trực tiếp cần HTTPS hoặc localhost; khi bị từ chối quyền/không có secure context, giao diện cung cấp camera thiết bị qua `capture="environment"`.
- Ảnh chất lượng thấp được hướng dẫn chụp lại trước khi chạy CLIP. Hệ thống chưa có detector đo khoảng cách hoặc độ phủ hiện vật; khung căn chỉ là hướng dẫn.
- Kết quả rõ ràng mở hồ sơ; kết quả cần xác nhận hiển thị tối đa ba hiện vật khác nhau và lựa chọn không phù hợp. Điểm thấp không được hiển thị như đáp án.
- Ba tầng gồm thông tin nhanh, mô tả gốc và nội dung đầy đủ/kèm góc ảnh. Dataset hiện chỉ có một description, nên hệ thống không tự sáng tác các trường vai trò/bối cảnh còn thiếu.
- Toàn bộ 583 hồ sơ hiện thiếu `historical_info.source`. Giao diện thông báo nguồn đang được bổ sung. Có một chuỗi nguồn cũng không tự chứng minh nội dung đã được kiểm chứng.
- Câu hỏi phân loại được tạo xác định từ `category`, phương án nhiễu lấy từ category thật của dataset. Không dùng LLM để tạo dữ kiện.
- Web Speech API ưu tiên giọng Việt, có nghe 30 giây/đầy đủ, tạm dừng, tiếp tục, dừng và văn bản đọc. Khả năng/giọng đọc phụ thuộc thiết bị; giao diện báo rõ khi trình duyệt không hỗ trợ Web Speech.
- Cỡ chữ và tương phản được lưu trên trình duyệt. Luồng hỗ trợ bàn phím, focus, dialog Escape và reduced motion.

## Confidence gate và chất lượng ảnh

Mặc định `CONFIDENCE_ACCEPT=0.72`, `CONFIDENCE_CANDIDATE=0.55`, `CONFIDENCE_MARGIN=0.08`, lấy dư `PINECONE_QUERY_OVERFETCH=50` vector trước khi gom theo ID. Mỗi hiện vật giữ góc có score cao nhất. `accepted` cần cả ngưỡng accept và khoảng cách Top-1/Top-2; thiếu đối thủ so sánh thì cần xác nhận. `needs_confirmation` đạt candidate nhưng chưa đạt accept/margin. Score được giới hạn trong [-1, 1], không phải phần trăm chính xác.

Giới hạn upload mặc định 12 MiB/25 triệu pixel, tối thiểu 320×320. Độ sáng dùng luminance trung bình và percentile; mờ dùng variance of Laplacian; vùng sáng gần trắng ít sắc độ là dấu hiệu có thể lóa. Các heuristic không phải bộ phát hiện vật thể hoặc phân biệt chắc chắn phản chiếu với nền trắng. Mọi ngưỡng có chú thích trong `.env.example`; cần hiệu chỉnh bằng ảnh điện thoại thật khác ảnh đã index trước khi đánh giá độ chính xác.

## Supabase (tùy chọn)

Áp dụng [migration](supabase/migrations/202609070001_initial_heritage.sql) bằng Supabase SQL Editor, hoặc dùng `psql` đã cài và biến môi trường kết nối riêng:

```powershell
psql "$env:SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/202609070001_initial_heritage.sql
```

Migration tạo hiện vật, ảnh, câu chuyện, nguồn, tags, câu hỏi/phương án, request/feedback và bảng sự kiện ẩn danh; có PK/FK/unique/index và RLS. Public chỉ đọc nội dung đã công bố; thao tác ghi và đáp án câu hỏi đi qua backend. Service-role key bỏ qua RLS, phải giữ phía server theo [tài liệu Supabase](https://supabase.com/docs/guides/database/postgres/row-level-security).

Importer giữ ID hiện tại, kiểm tra dataset trước khi import, phân trang khi đọc remote và upsert các bản ghi mới/thay đổi:

```powershell
# Chỉ đọc dataset local, không cần key, không gọi mạng.
.\.venv\Scripts\python.exe -m scripts.import_supabase
# Có SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY trong .env: xem thay đổi trước.
.\.venv\Scripts\python.exe -m scripts.import_supabase --compare-remote
# Áp dụng sau khi đã chạy migration.
.\.venv\Scripts\python.exe -m scripts.import_supabase --apply
```

Báo cáo phân biệt added/updated/skipped/errors. Dry-run local giả định database trống, không phải số bản ghi đã ghi thực tế. Import chạy lại không thêm trùng; các bảng được cập nhật theo thứ tự phụ thuộc. JSON fallback giúp đọc nội dung khi Supabase không sẵn sàng; lỗi dữ liệu/lập trình không bị che thành một kết quả thành công.

## Bảo mật và vận hành

Ảnh truy vấn được xử lý trong bộ nhớ, áp dụng EXIF orientation rồi bỏ metadata, không lưu mặc định. Thống kê SQLite tại `data/analytics.sqlite3` chỉ chứa UUID ngẫu nhiên, ID gợi ý, score, metrics, thời gian và phản hồi; không có tên/email/hồ sơ học sinh hoặc ảnh gốc. Dữ liệu này vẫn cần thời hạn lưu và quy trình xóa phù hợp khi triển khai chính thức.

Phản hồi phải gắn với request context phía server; một ID ngoài Top-3 bị từ chối. Request context có TTL, mặc định một giờ. Khởi động lại API có thể làm phiên phản hồi cũ hết hạn. API trả thông báo lỗi công khai, không trả stack trace/SDK secret. Chỉ cho phép CORS origins được cấu hình.

Khi truy cập từ điện thoại trong LAN, đặt API_HOST=0.0.0.0, thay URL API bằng IP máy chủ trong frontend/.env.local và thêm origin frontend tương ứng vào CORS_ORIGINS. Chạy Next bằng `npm run dev -- --hostname 0.0.0.0`. Khởi động lại frontend sau đổi biến public. Trước khi public internet, dùng HTTPS, reverse proxy có giới hạn body/rate/timeout, giới hạn concurrency và cấu hình proxy trust đúng; không bật nhiều worker tùy tiện vì mỗi worker tải một model và có request context riêng.

## Kiểm thử website

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Test mặc định dùng fake dịch vụ trong test và không gọi Pinecone/Supabase thật. Smoke test dưới đây là tùy chọn, cần backend đang chạy, ảnh mẫu thật và credential Pinecone; có ghi metrics ẩn danh qua API:

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_api --image "images/path/to/image.jpg" --expect-item "location-id"
# --feedback ghi thêm một phản hồi ẩn danh để kiểm tra toàn luồng.
```

Kiểm tra Chrome thật (cài thêm `requirements-smoke.txt`, frontend/backend đang chạy):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-smoke.txt
.\.venv\Scripts\python.exe -m scripts.smoke_browser --image "images/path/to/image.jpg"
```

Script kiểm tra 320px/390px/tablet/desktop, ảnh preview, request multipart thật và câu chuyện; screenshot/báo cáo nằm trong `reports/`. Camera vật lý, chất lượng nhận diện từ ảnh điện thoại mới và chất lượng giọng Việt cần nghiệm thu trên thiết bị mục tiêu.

## Thư mục website mới

```text
frontend/app/              Trang và giao diện Next.js
frontend/components/       Camera, kết quả, câu chuyện, TTS, thử thách
frontend/lib/              API client, types, TTS service
src/api/                  FastAPI, quality/confidence, runtime, request context
src/repositories/         JSON/Supabase adapters và thống kê SQLite
supabase/migrations/      Schema, constraints, indexes và RLS
scripts/import_supabase.py Import idempotent/dry-run
scripts/smoke_api.py       Nghiệm thu API thật tùy chọn
scripts/smoke_browser.py   Nghiệm thu Chrome thật tùy chọn
```

Công cụ dataset/CLI bên dưới vẫn được giữ lại.

## Dataset hiện tại

- `images/`: 957 ảnh JPG.
- `JSON/`: 583 JSON, mỗi file chứa `locations[]`; mỗi location chứa `images[]`.
- Quan hệ ảnh–metadata dựa trên `locations[].images[].filename`, không dựa vào tên JSON.
- Validator cảnh báo khi `historical_info.source` trống nhưng không coi đó là lỗi kỹ thuật.

## Cài đặt

Yêu cầu Python 3.11 hoặc 3.12. Trên Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Điền `PINECONE_API_KEY` trong `.env`. Không commit file này. Model OpenCLIP được tải ở lần chạy thực đầu tiên; CPU dùng được nhưng indexing sẽ chậm hơn CUDA.

## Kiểm tra dataset

```powershell
python -m src.dataset.validate_dataset
```

Báo cáo máy đọc được ghi vào `reports/dataset-validation.json`. Exit code là `1` khi có lỗi nghiêm trọng; cảnh báo thiếu nguồn không làm lệnh thất bại.

## Chuẩn hóa đường dẫn

Xem mapping mà không thay đổi dữ liệu:

```powershell
python -m src.dataset.normalize_paths
```

Áp dụng theo cơ chế an toàn bằng cách **copy** sang `data/images` và `data/metadata`; dữ liệu gốc được giữ nguyên:

```powershell
python -m src.dataset.normalize_paths --apply
```

Sau đó đặt `IMAGE_ROOT=data/images` và `JSON_ROOT=data/metadata` trong `.env`, rồi chạy validator lần nữa. Công cụ dừng nếu phát hiện collision và tạo `data/path-mapping.json`.

## Index Pinecone

Index hiện có đã chứa 957 vector. Không chạy lệnh ghi/index lại để sử dụng website. Các lệnh tạo/index dưới đây chỉ dành cho công việc bảo trì dataset riêng khi được chủ dự án cho phép.

Kiểm tra dataset mà không tải CLIP hoặc gọi Pinecone:

```powershell
python -m src.indexing.index_dataset --dry-run
```

Nếu index chưa tồn tại, cho phép tạo serverless index với dimension lấy trực tiếp từ model:

```powershell
python -m src.indexing.index_dataset --create-index --batch-size 32
```

Nếu index đã tồn tại, bỏ `--create-index`. Chương trình dừng nếu dimension hoặc metric không tương thích và không bao giờ tự xóa index.

## Tìm kiếm bằng ảnh

```powershell
python -m src.search.image_search --image "path/to/query.jpg" --top-k 5 --min-score 0.55
```

Điểm cosine thấp chỉ biểu thị mức tương đồng yếu, không phải nhận dạng chắc chắn.

## Test

```powershell
pytest -q
```

Các unit test không gọi Pinecone thật. Test tải model đầy đủ không chạy mặc định để tránh tải checkpoint lớn trong CI.

## Cấu trúc mã

```text
schemas/heritage-item.schema.json
src/config.py
src/dataset/catalog.py
src/dataset/validate_dataset.py
src/dataset/normalize_paths.py
src/clip/encoder.py
src/vector_store/pinecone_client.py
src/indexing/index_dataset.py
src/search/image_search.py
tests/
```

Metadata Pinecone gồm ID hiện vật/ảnh, tiêu đề, mô tả, danh mục, giai đoạn, địa điểm, tags, caption, đường dẫn tương đối, loại embedding, model và checksum. ID vector ổn định theo dạng `<location-id>:<image-id>`.
#   H i s t o r y  
 