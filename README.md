# DiSản Lens — Chụp một chứng tích, mở một câu chuyện

Website học tập dành cho học sinh và khách tham quan: chụp/tải ảnh thật, kiểm tra chất lượng, nhận diện hiện vật, đọc câu chuyện ba tầng, nghe thuyết minh và trả lời câu hỏi ngắn từ dữ liệu hiện vật.

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
    → ảnh danh sách: thumbnail WebP có ETag → lightbox mới tải ảnh gốc
    → nội dung học tập: evidence gate → fallback JSON hoặc OpenAI Responses → SQLite cache
    → thuyết minh: văn bản an toàn → OpenAI Speech → WAV cache → Web Speech fallback
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

Trong `.env`, điền khóa Pinecone hiện có. OpenAI là tùy chọn: dùng tên chuẩn `OPENAI_API_KEY`, hoặc giữ `CHATGPT_API_KEY` đang có vì backend hỗ trợ alias này. Không thêm khóa vào `frontend/.env.local` và không dùng tiền tố `NEXT_PUBLIC_`. Để trống `SUPABASE_URL` và `SUPABASE_SERVICE_ROLE_KEY` để dùng JSON. API: `http://127.0.0.1:8000`; OpenAPI: `http://127.0.0.1:8000/docs`.

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
- Kết quả rõ ràng mở trang thông tin; kết quả cần xác nhận hiển thị tối đa ba hiện vật khác nhau và lựa chọn không phù hợp. Điểm thấp không được hiển thị như đáp án.
- Ba tầng gồm thông tin nhanh, câu chuyện khoảng một phút và khám phá sâu. Nội dung một phút không lặp nguyên văn phần nhanh; phần sâu đi thẳng vào chất liệu, tác nhân, hoạt động, diễn biến, điểm nổi bật, hệ quả và ý nghĩa lịch sử, kèm claim, nguồn và mindmap mở sẵn. Nội dung không dùng lời bình kiểu “giúp học sinh/người xem hiểu”; dataset hiện chỉ có một description cho mỗi hiện vật nên hệ thống không kéo dài câu chữ hoặc tự sáng tác dữ kiện còn thiếu.
- Toàn bộ 583 bản ghi hiện thiếu `historical_info.source`. Khi khóa OpenAI được cấu hình, endpoint nội dung học tập dùng `web_search` để tìm nguồn tham khảo rồi kiểm tra lại evidence trước khi cache; nếu dịch vụ AI không khả dụng, hệ thống trả nội dung xác định từ JSON. Một chuỗi nguồn không tự chứng minh nội dung đã được kiểm chứng; chỉ nguồn có `source_status=verified` mới được xem là đã qua quy trình biên tập.
- Câu hỏi phân loại được tạo xác định từ `category`, phương án nhiễu lấy từ category thật của dataset. Không dùng LLM để tạo dữ kiện.
- Thuyết minh ưu tiên OpenAI Speech phía server, dùng chỉ dẫn đọc hoàn toàn bằng tiếng Việt, trả URL WAV thay vì nhúng audio vào JSON và cache theo nội dung/model/giọng/ngôn ngữ/chỉ dẫn/phiên bản cấu hình. Giao diện có nghe 30 giây/đầy đủ, phát, tạm dừng, tiếp tục, dừng, tua và tốc độ 0,75×–1,5×. Nếu server lỗi, Web Speech chỉ chọn giọng có mã ngôn ngữ tiếng Việt và đặt chính xác `vi-VN`; nếu thiết bị không có giọng Việt, hệ thống báo rõ và giữ phụ đề, tuyệt đối không tự chuyển sang giọng tiếng Anh.
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

Ảnh truy vấn được xử lý trong bộ nhớ, áp dụng EXIF orientation rồi bỏ metadata, không lưu mặc định. Thống kê SQLite tại `data/analytics.sqlite3` chỉ chứa UUID ngẫu nhiên, ID gợi ý, score, metrics, thời gian và phản hồi; không có tên, email, dữ liệu định danh học sinh hoặc ảnh gốc. Dữ liệu này vẫn cần thời hạn lưu và quy trình xóa phù hợp khi triển khai chính thức.

Phản hồi phải gắn với request context phía server; một ID ngoài Top-3 bị từ chối. Request context có TTL, mặc định một giờ. Khởi động lại API có thể làm phiên phản hồi cũ hết hạn. API trả thông báo lỗi công khai, không trả stack trace/SDK secret. Chỉ cho phép CORS origins được cấu hình.

Khóa OpenAI chỉ được nạp ở backend và trường cấu hình khóa bị ẩn khỏi `repr`. Trình duyệt chỉ gửi ID hiện vật và lựa chọn `short`/`full`, không được gửi prompt, model, transcript hoặc đường dẫn cache. Endpoint AI/TTS có giới hạn body, rate limit và concurrency riêng. Mô tả/caption/nguồn được đóng gói là dữ liệu không tin cậy; structured output bị kiểm tra lại bằng Pydantic, evidence reference, quan hệ mindmap, năm và URL trước khi cache. Backend yêu cầu Responses API dùng công cụ `web_search` để đối chiếu bối cảnh; URL do mô hình trả về chỉ được chấp nhận nếu URL đó thực sự có trong kết quả công cụ. Khóa cache nội dung gồm fingerprint của prompt, chế độ web-search và JSON Schema; khóa cache âm thanh gồm cả chỉ dẫn phát âm, nên thay đổi quy tắc không tái sử dụng kết quả cũ. Cache AI/audio/thumbnail nằm dưới `data/`, không ghi đè JSON và không được Git theo dõi.

Adapter server bám theo [Responses API với JSON Schema](https://developers.openai.com/api/reference/cli/resources/responses/methods/create) và [Speech API](https://developers.openai.com/api/reference/cli/resources/audio/subresources/speech/methods/create); request nội dung đặt `store=false`. Việc giữ khóa trong biến môi trường phía server tuân theo [khuyến nghị an toàn API key của OpenAI](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety).

API mới:

- `POST /api/v1/artifacts/{item_id}/learning-content`: nội dung có schema, trạng thái nguồn/generation/cache và evidence references.
- `POST /api/v1/artifacts/{item_id}/narrations` với JSON `{ "variant": "short" | "full" }`: transcript an toàn và URL WAV hoặc yêu cầu fallback.
- `GET /api/v1/narrations/{sha256}/audio`: file WAV cache, hỗ trợ ETag và byte range.
- `GET /media/{relative_path}?width=320|640|960|1280`: thumbnail WebP cache; bỏ `width` mới tải bản gốc.

Các biến OpenAI/TTS/cache được mô tả bằng placeholder trong `.env.example`: `OPENAI_API_KEY`/`CHATGPT_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_CONTENT_MODEL`, `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`, `OPENAI_MAX_OUTPUT_TOKENS`, `AI_PROMPT_VERSION`, `AI_SCHEMA_VERSION`, `AI_CACHE_SQLITE_PATH`, `AI_CONTENT_RATE_LIMIT_PER_MINUTE`, `MAX_CONCURRENT_AI_GENERATIONS`, `TTS_CACHE_DIR`, `TTS_LANGUAGE`, `TTS_FORMAT`, `TTS_CONFIG_VERSION`, `TTS_RATE_LIMIT_PER_MINUTE`, `MAX_CONCURRENT_TTS_GENERATIONS` và `THUMBNAIL_CACHE_DIR`.

Khi truy cập từ điện thoại trong LAN, đặt API_HOST=0.0.0.0, thay URL API bằng IP máy chủ trong frontend/.env.local và thêm origin frontend tương ứng vào CORS_ORIGINS. Chạy Next bằng `npm run dev -- --hostname 0.0.0.0`. Khởi động lại frontend sau đổi biến public. Trước khi public internet, dùng HTTPS, reverse proxy có giới hạn body/rate/timeout, giới hạn concurrency và cấu hình proxy trust đúng; không bật nhiều worker tùy tiện vì mỗi worker tải một model và có request context riêng.

## Kiểm thử website

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.check_secrets
.\.venv\Scripts\python.exe -m scripts.benchmark_media
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

Script kiểm tra 320/390/768/1024/1440px, horizontal overflow, ảnh preview, request multipart thật, lightbox/Escape/focus/cache ảnh gốc và câu chuyện; screenshot/báo cáo nằm trong `reports/`. Camera vật lý, chất lượng nhận diện từ ảnh điện thoại mới, screen reader và chất lượng giọng Việt vẫn cần nghiệm thu trên thiết bị mục tiêu.

`scripts.benchmark_media` không gọi AI, CLIP hay Pinecone. Nó so tổng byte ảnh gốc với WebP 640px trên nhóm hiện vật có nhiều ảnh nhất và đo cả lần tạo lạnh/lần đọc cache. Có thể xem JSON tại `reports/media-performance.json`.

Để thử TTS thật mà không lộ khóa: khởi động lại backend sau khi cấu hình khóa, mở website rồi nhấn **Nghe 30 giây** một lần; phản hồi thứ hai của cùng hiện vật phải có `cache_status=hit`. Không dùng `curl -v`, không in biến môi trường và không chụp màn hình terminal chứa header. Thử này có dùng quota OpenAI. Với dữ liệu hiện vật thiếu nguồn đã xác minh, yêu cầu nội dung sẽ dùng `web_search` rồi hiển thị các trang tham khảo thành liên kết; nếu tìm kiếm hoặc kiểm tra nguồn thất bại, website vẫn trả nội dung xác định từ JSON thay vì để trống.

## Thư mục website mới

```text
frontend/app/              Trang và giao diện Next.js
frontend/components/       Camera, kết quả, câu chuyện, TTS, thử thách
frontend/lib/              API client, types, TTS service
src/api/                  FastAPI, quality/confidence, runtime, request context
src/repositories/         JSON/Supabase adapters và thống kê SQLite
supabase/migrations/      Schema, constraints, indexes và RLS
scripts/import_supabase.py Import idempotent/dry-run
scripts/benchmark_media.py Đo payload thumbnail và tốc độ cache, không gọi dịch vụ ngoài
scripts/check_secrets.py    Quét source/build/staged/history, chỉ in vị trí và giá trị đã che
scripts/smoke_api.py       Nghiệm thu API thật tùy chọn
scripts/smoke_browser.py   Nghiệm thu Chrome thật tùy chọn
src/ai/                   Structured output, evidence gate, OpenAI adapters và cache
src/api/media.py          Ảnh gốc an toàn và thumbnail WebP theo kích thước
```

Công cụ dataset/CLI bên dưới vẫn được giữ lại.

## Dataset hiện tại

- `images/`: 957 ảnh JPG.
- `JSON/`: 583 JSON, mỗi file chứa `locations[]`; mỗi location chứa `images[]`.
- Quan hệ ảnh–metadata dựa trên `locations[].images[].filename`, không dựa vào tên JSON.
- JSON được đọc bắt buộc bằng UTF-8 và mọi chuỗi được chuẩn hóa Unicode NFC tại ranh giới backend/frontend. Validator báo lỗi nếu phát hiện dấu hiệu mojibake và cảnh báo nếu văn bản chưa ở NFC.
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
 #   H i s t o r y  
 #   H i s t o r y  
 #   H i s t o r y  
 