import type {
  Artifact,
  ArtifactStory,
  Challenge,
  FeedbackPayload,
  FeedbackResponse,
  RecognitionResponse,
  QualityIssue,
} from "@/lib/types";

const DEFAULT_API_URL = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 60_000;
// The first CPU request may also load the CLIP weights into memory.
const RECOGNITION_TIMEOUT_MS = 180_000;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_URL).replace(
    /\/$/,
    "",
  );
}

export function toAssetUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path) || path.startsWith("blob:")) return path;
  return `${getApiBaseUrl()}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function fetchJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = "";
      let code: string | undefined;
      try {
        const body = (await response.json()) as {
          detail?: string | { message?: string; code?: string };
          message?: string;
          code?: string;
        };
        if (typeof body.detail === "string") detail = body.detail;
        else if (body.detail) {
          detail = body.detail.message || "";
          code = body.detail.code;
        }
        detail ||= body.message || "";
        code ||= body.code;
      } catch {
        // The public message below intentionally hides non-JSON server details.
      }

      throw new ApiError(
        detail || publicErrorMessage(response.status),
        response.status,
        code,
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        "Quá trình phân tích mất nhiều thời gian hơn dự kiến. Em hãy thử lại.",
        undefined,
        "request_timeout",
      );
    }
    throw new ApiError(
      "Không thể kết nối tới hệ thống nhận diện. Hãy kiểm tra mạng và thử lại.",
      undefined,
      "network_error",
    );
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

function publicErrorMessage(status: number): string {
  if (status === 413) return "Ảnh có dung lượng quá lớn. Em hãy chọn ảnh nhỏ hơn.";
  if (status === 415 || status === 422)
    return "Tệp này chưa phù hợp. Hãy chọn ảnh JPG, PNG hoặc WEBP.";
  if (status === 404) return "Không tìm thấy thông tin hiện vật này.";
  if (status === 429)
    return "Hệ thống đang nhận nhiều yêu cầu. Em hãy chờ một chút rồi thử lại.";
  if (status >= 500)
    return "Hệ thống đang tạm gián đoạn. Em hãy thử lại sau ít phút.";
  return "Yêu cầu chưa thể hoàn thành. Em hãy kiểm tra lại và thử lần nữa.";
}

export async function recognizeImage(file: File): Promise<RecognitionResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  const raw = await fetchJson<unknown>("/api/v1/recognitions", {
    method: "POST",
    body: form,
  }, RECOGNITION_TIMEOUT_MS);
  return normalizeRecognition(raw);
}

export async function getArtifact(id: string): Promise<Artifact> {
  const raw = await fetchJson<unknown>(
    `/api/v1/artifacts/${encodeURIComponent(id)}`,
  );
  return normalizeArtifact(raw);
}

export async function getArtifactStory(id: string): Promise<ArtifactStory> {
  const raw = await fetchJson<unknown>(
    `/api/v1/artifacts/${encodeURIComponent(id)}/story`,
  );
  return normalizeStory(raw);
}

export async function getArtifactChallenge(
  id: string,
): Promise<Challenge | null> {
  const raw = await fetchJson<unknown>(
    `/api/v1/artifacts/${encodeURIComponent(id)}/challenge`,
  );
  if (raw == null) return null;
  return normalizeChallenge(raw);
}

export function sendRecognitionFeedback(
  requestId: string,
  payload: FeedbackPayload,
): Promise<FeedbackResponse> {
  return fetchJson<FeedbackResponse>(
    `/api/v1/recognitions/${encodeURIComponent(requestId)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ApiError(
      "Dữ liệu từ hệ thống chưa đúng định dạng. Em hãy thử lại.",
      undefined,
      "invalid_response",
    );
  }
  return value as UnknownRecord;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function normalizeCandidate(value: unknown) {
  const raw = asRecord(value);
  const itemId = stringValue(
    raw.item_id || raw.location_id || raw.artifact_id || raw.id,
  );
  if (!itemId) throw new ApiError("Kết quả nhận diện thiếu mã hiện vật.");
  return {
    item_id: itemId,
    location_id: nullableString(raw.location_id) || undefined,
    name: stringValue(raw.name || raw.title, "Hiện vật chưa đặt tên"),
    title: nullableString(raw.title) || undefined,
    category: stringValue(raw.category, "artifact"),
    period: nullableString(raw.period),
    historical_period: nullableString(
      raw.historical_period || raw.period,
    ),
    year: nullableNumber(raw.year),
    score: numberValue(raw.score),
    image_url: nullableString(raw.image_url || raw.thumbnail_url),
    image_caption: nullableString(raw.image_caption || raw.caption),
  };
}

function normalizeRecognition(value: unknown): RecognitionResponse {
  const raw = asRecord(value);
  const rawStatus = stringValue(raw.recognition_status || raw.status);
  if (![
    "accepted",
    "needs_confirmation",
    "rejected",
  ].includes(rawStatus)) {
    throw new ApiError("Hệ thống trả về trạng thái nhận diện không hợp lệ.");
  }

  const qualityRaw = asRecord(raw.quality || {});
  const metricsRaw = asRecord(qualityRaw.metrics || {});
  const qualityStatusValue = stringValue(qualityRaw.status, "failed");
  const qualityStatus = ["passed", "warning", "failed"].includes(
    qualityStatusValue,
  )
    ? (qualityStatusValue as "passed" | "warning" | "failed")
    : "failed";
  const issues = arrayValue(qualityRaw.issues).map<QualityIssue>((value, index) => {
    if (typeof value === "string") {
      return { code: `quality_${index}`, message: value };
    }
    const issue = asRecord(value);
    return {
      code: stringValue(issue.code, `quality_${index}`),
      message: stringValue(issue.message, "Ảnh cần được chụp lại."),
      guidance: nullableString(issue.guidance),
      severity:
        issue.severity === "warning" || issue.severity === "error"
          ? issue.severity
          : undefined,
    };
  });
  const candidatesRaw = raw.top_candidates || raw.candidates || raw.results;
  const candidates = arrayValue(candidatesRaw).map(normalizeCandidate);
  const selectedRaw = raw.selected_item || raw.selected;
  const timingsRaw =
    typeof raw.processing_ms === "number"
      ? { total: raw.processing_ms }
      : asRecord(raw.timings_ms || raw.processing_ms || {});
  const metrics = Object.fromEntries(
    Object.entries(metricsRaw).filter(([, metric]) => typeof metric === "number"),
  ) as RecognitionResponse["quality"]["metrics"];

  return {
    request_id: stringValue(raw.request_id),
    quality: { status: qualityStatus, metrics, issues },
    recognition_status: rawStatus as RecognitionResponse["recognition_status"],
    confidence_label: stringValue(
      raw.confidence_label,
      rawStatus === "accepted"
        ? "Độ tin cậy cao"
        : rawStatus === "needs_confirmation"
          ? "Cần xác nhận"
          : "Chưa đủ dữ liệu",
    ),
    top_score: nullableNumber(raw.top_score),
    score_margin: nullableNumber(raw.score_margin),
    candidates,
    selected_item: selectedRaw ? normalizeCandidate(selectedRaw) : null,
    timings_ms: Object.fromEntries(
      Object.entries(timingsRaw).filter(
        ([, timing]) => typeof timing === "number",
      ),
    ) as RecognitionResponse["timings_ms"],
  };
}

function normalizeImage(value: unknown, index: number) {
  const raw = asRecord(value);
  return {
    id: stringValue(raw.id || raw.image_id, `image-${index}`),
    url: nullableString(raw.url),
    image_url: nullableString(raw.image_url || raw.url),
    filename: nullableString(raw.filename),
    caption: stringValue(raw.caption, "Ảnh tư liệu của hiện vật"),
    view: nullableString(raw.view),
    year: nullableNumber(raw.year),
    alt_text: nullableString(raw.alt_text),
  };
}

function normalizeArtifact(value: unknown): Artifact {
  const raw = asRecord(value);
  const history = asRecord(raw.historical_info || {});
  const location = raw.location ? asRecord(raw.location) : null;
  return {
    item_id: stringValue(raw.item_id),
    slug: stringValue(raw.slug) || undefined,
    name: stringValue(raw.name || history.title, "Hiện vật chưa đặt tên"),
    title: nullableString(raw.title || history.title) || undefined,
    category: stringValue(raw.category, "artifact"),
    tags: arrayValue(raw.tags).filter(
      (tag): tag is string => typeof tag === "string",
    ),
    historical_period: nullableString(
      raw.historical_period || history.historical_period,
    ),
    period: nullableString(raw.period || history.historical_period),
    year: nullableNumber(raw.year ?? history.year),
    description: stringValue(raw.description || history.description),
    event: nullableString(raw.event || history.event),
    source: nullableString(raw.source || history.source),
    source_verified:
      typeof raw.source_verified === "boolean"
        ? raw.source_verified
        : false,
    location: location
      ? {
          address: nullableString(location.address),
          city: nullableString(location.city),
          province: nullableString(location.province),
          country: nullableString(location.country),
        }
      : null,
    images: arrayValue(raw.images).map(normalizeImage),
  };
}

function normalizeStory(value: unknown): ArtifactStory {
  const raw = asRecord(value);
  const quick = asRecord(raw.quick || {});
  const overview = asRecord(raw.overview || {});
  const deep = asRecord(raw.deep || {});
  const primaryImage = quick.primary_image || quick.image;
  const sources = arrayValue(deep.sources)
    .map((source) => {
      if (typeof source === "string") return source;
      if (typeof source === "object" && source !== null) {
        const record = source as UnknownRecord;
        return stringValue(record.label || record.title || record.url);
      }
      return "";
    })
    .filter(Boolean);
  return {
    item_id: stringValue(raw.item_id),
    quick: {
      title: stringValue(quick.title, "Hiện vật chưa đặt tên"),
      category: stringValue(quick.category, "artifact"),
      period: nullableString(quick.period || quick.historical_period),
      year: nullableNumber(quick.year),
      image: primaryImage ? normalizeImage(primaryImage, 0) : null,
    },
    overview: {
      description: nullableString(overview.description),
      event: nullableString(overview.event),
      what_it_is: nullableString(overview.what_it_is),
      role: nullableString(overview.role),
      context: nullableString(overview.context),
      significance: nullableString(overview.significance),
      paragraphs: arrayValue(overview.paragraphs).filter(
        (paragraph): paragraph is string => typeof paragraph === "string",
      ),
    },
    deep: {
      description: stringValue(deep.description),
      event: nullableString(deep.event || overview.event),
      people: arrayValue(deep.people).filter(
        (person): person is string => typeof person === "string",
      ),
      related_events: arrayValue(deep.related_events).filter(
        (event): event is string => typeof event === "string",
      ),
      images: arrayValue(deep.images).map(normalizeImage),
      source: nullableString(deep.source) || sources.join(" · ") || null,
      source_verified: deep.source_verified === true,
    },
  };
}

function normalizeChallenge(value: unknown): Challenge {
  const raw = asRecord(value);
  const options = arrayValue(raw.options).map((value, index) => {
    const option = asRecord(value);
    return {
      id: stringValue(option.id || option.option_id, `option-${index}`),
      label: stringValue(option.label || option.text),
      isCorrect: option.is_correct === true,
    };
  });
  const correctOptionId =
    stringValue(raw.correct_option_id) ||
    options.find((option) => option.isCorrect)?.id ||
    "";
  return {
    id: stringValue(raw.id || raw.challenge_id),
    item_id: stringValue(raw.item_id),
    type: stringValue(raw.type, "single_choice") as Challenge["type"],
    question: stringValue(raw.question),
    options: options.map(({ id, label }) => ({ id, label })),
    correct_option_id: correctOptionId,
    explanation: stringValue(raw.explanation),
    source_field: stringValue(raw.source_field),
  };
}
