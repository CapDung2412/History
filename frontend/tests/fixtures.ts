import type { Artifact, ArtifactStory, Challenge, RecognitionCandidate, RecognitionResponse } from "@/lib/types";

// Test-only content. Production content always comes from the repository API.
export const candidate: RecognitionCandidate = {
  item_id: "test-radio", name: "Máy vô tuyến thử nghiệm", category: "artifact",
  period: "Giai đoạn thử nghiệm", score: 0.9, image_url: "/media/test.jpg",
};
export const secondCandidate: RecognitionCandidate = {
  ...candidate, item_id: "test-map", name: "Bản đồ thử nghiệm", score: 0.64,
};
export const artifact: Artifact = {
  item_id: candidate.item_id, name: candidate.name, category: "artifact", tags: [],
  description: "Mô tả kiểm thử chỉ dùng trong bài kiểm tra giao diện.",
  source: "Một tài liệu chưa kiểm chứng", source_verified: false,
  images: [{ id: "test-image", caption: "Ảnh kiểm thử", url: "/media/test.jpg" }],
};
export const story: ArtifactStory = {
  item_id: artifact.item_id,
  quick: { title: artifact.name, category: artifact.category, period: candidate.period },
  overview: { paragraphs: [artifact.description] },
  deep: { description: artifact.description, images: artifact.images, source: artifact.source, source_verified: false },
};
export const challenge: Challenge = {
  id: "test-challenge", item_id: artifact.item_id, type: "category",
  question: "Hiện vật kiểm thử thuộc loại nào?",
  options: [{ id: "artifact", label: "Hiện vật" }, { id: "photo", label: "Ảnh tư liệu" }],
  correct_option_id: "artifact", explanation: "Trường category của hồ sơ kiểm thử ghi artifact.",
};
export function recognition(status: RecognitionResponse["recognition_status"] = "accepted"): RecognitionResponse {
  return {
    request_id: "7ca2f971-aa02-4f47-84d8-37b46d0c4fc0",
    quality: { status: "passed", metrics: { width: 800, height: 600 }, issues: [] },
    recognition_status: status,
    confidence_label: status === "accepted" ? "Tương đồng cao" : "Cần kiểm tra",
    top_score: 0.9, score_margin: 0.26,
    candidates: [candidate, secondCandidate],
    selected_item: status === "accepted" ? candidate : null,
    timings_ms: { total: 1200 },
  };
}
