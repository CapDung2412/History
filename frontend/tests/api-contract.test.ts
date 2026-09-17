import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  getArtifact,
  getArtifactStory,
  recognizeImage,
  requestLearningContent,
  requestNarration,
} from "@/lib/api";
import { artifact, recognition, story } from "./fixtures";

describe("backend API contract", () => {
  it("normalizes decomposed Vietnamese from JSON responses to NFC", async () => {
    const golden = "Tư liệu trưng bày giới thiệu tượng bà mẹ bằng mảnh bom.";
    const decomposed = golden.normalize("NFD");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({
          ...artifact,
          name: decomposed,
          description: decomposed,
        }),
      ),
    );

    const normalized = await getArtifact(artifact.item_id);

    expect(normalized.name).toBe(golden);
    expect(normalized.description).toBe(golden);
    expect(normalized.name).toBe(normalized.name.normalize("NFC"));
  });

  it("reads authoritative item_id and preserves explicit unverified sources", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(Response.json(artifact))
      .mockResolvedValueOnce(Response.json(story))
      .mockResolvedValueOnce(Response.json(recognition())));
    expect(await getArtifact(artifact.item_id)).toMatchObject({ item_id: artifact.item_id, source_verified: false });
    expect((await getArtifactStory(artifact.item_id)).deep.source_verified).toBe(false);
    expect((await recognizeImage(new File(["jpeg"], "a.jpg", { type: "image/jpeg" }))).candidates[0].item_id).toBe(artifact.item_id);
  });

  it("never promotes a source string to verified status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ ...story, deep: { ...story.deep, source_verified: undefined } })));
    expect((await getArtifactStory(artifact.item_id)).deep.source_verified).toBe(false);
  });

  it("preserves safe structured server errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ detail: { code: "rate_limit", message: "Chờ một chút rồi thử lại." } }, { status: 429 })));
    await expect(getArtifact("test")).rejects.toMatchObject({ name: "ApiError", status: 429, code: "rate_limit" });
  });

  it("rejects unknown recognition states", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ ...recognition(), recognition_status: "guess" })));
    await expect(recognizeImage(new File(["jpeg"], "a.jpg"))).rejects.toBeInstanceOf(ApiError);
  });

  it("preserves a non-blocking image-quality warning", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({
      ...recognition(),
      quality: {
        ...recognition().quality,
        status: "warning",
        issues: [{ code: "strong_glare", message: "Có thể bị lóa.", severity: "warning" }],
      },
    })));
    expect((await recognizeImage(new File(["jpeg"], "a.jpg"))).quality.status).toBe("warning");
  });

  it("requests server-selected grounded learning content and narration", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(Response.json({
        artifact_id: artifact.item_id,
        data_status: "missing",
        source_status: "missing",
        generation_status: "fallback_missing_source",
        cache_status: "bypass",
        model: null,
        notice: "Chưa có nguồn kiểm chứng.",
        references: [{
          ref: "web.1",
          label: "Video tư liệu từ kênh chính thức",
          value: "Video cụ thể đã được backend đối chiếu nguồn.",
          source_status: "verified",
          url: "https://www.youtube.com/watch?v=AbCdEfGhI12",
        }],
        content: {
          factual_claims: [],
          storytelling: {
            quick: { text: artifact.name, claim_ids: [] },
            one_minute: { text: artifact.description, claim_ids: [] },
          },
          deep_sections: [],
          timeline: [],
          keywords: [{ term: "hiện vật", explanation: "Từ dữ liệu." }],
          related_videos: [
            {
              title: "Phim tư liệu kiểm thử",
              url: "https://www.youtube.com/watch?v=AbCdEfGhI12&list=tracking",
              channel_name: "Đài truyền hình kiểm thử",
              trust_level: "official",
              trust_reason: "Kênh chính thức của một cơ quan truyền hình.",
              relevance: "Liên quan trực tiếp đến hiện vật.",
              scope: "exact_artifact",
              evidence_refs: ["web.1"],
            },
            {
              title: "Video dạng liên kết ngắn",
              url: "https://www.youtu.be/9bZkp7q19f0?t=10",
              relevance: "Nguồn minh họa.",
              scope: "related_event",
              evidence_refs: [],
            },
            {
              title: "Video Shorts",
              url: "https://youtube.com/shorts/aqz-KE-bpKQ?feature=share",
              relevance: "Chi tiết liên quan.",
              scope: "site_or_museum",
              evidence_refs: [],
            },
            {
              title: "Video trực tiếp",
              url: "https://m.youtube.com/live/J---aiyznGQ?feature=share",
              relevance: "Một video cụ thể trên tên miền YouTube dành cho di động.",
              scope: "broader_context",
              evidence_refs: [],
            },
            {
              title: "Video trên YouTube Music",
              url: "https://music.youtube.com/watch?v=AbCdEfGhI12&utm_source=test",
              relevance: "Một trang video cụ thể.",
              scope: "broader_context",
              evidence_refs: [],
            },
            {
              title: "Không an toàn vì dùng HTTP",
              url: "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
              relevance: "Không được hiển thị.",
              scope: "broader_context",
              evidence_refs: [],
            },
            {
              title: "Tên miền giả mạo",
              url: "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ",
              relevance: "Không được hiển thị.",
              scope: "broader_context",
              evidence_refs: [],
            },
            {
              title: "Không phải trang video",
              url: "https://www.youtube.com/results?search_query=history",
              relevance: "Không được hiển thị.",
              scope: "broader_context",
              evidence_refs: [],
            },
            {
              title: "Phạm vi không hợp lệ",
              url: "https://www.youtube.com/watch?v=J---aiyznGQ",
              relevance: "Không được hiển thị.",
              scope: "unreviewed",
              evidence_refs: [],
            },
          ],
          mindmap: {
            central_label: artifact.name,
            branches: [{
              id: "identity",
              label: "Nhận diện",
              relation: "identified_by",
              evidence_refs: ["artifact.name"],
              nodes: [{
                id: "name",
                label: artifact.name,
                note: null,
                evidence_refs: ["artifact.name"],
              }],
            }],
          },
        },
      }))
      .mockResolvedValueOnce(Response.json({
        artifact_id: artifact.item_id,
        variant: "short",
        status: "fallback_required",
        cache_status: "bypass",
        transcript: artifact.name,
        asset_id: null,
        audio_url: null,
        mime_type: null,
        notice: "Dùng giọng đọc thiết bị.",
      }));
    vi.stubGlobal("fetch", fetchMock);

    const learning = await requestLearningContent(artifact.item_id);
    const narration = await requestNarration(artifact.item_id, "short");

    expect(learning.content.mindmap.central_label).toBe(artifact.name);
    expect(learning.content.related_videos).toEqual([
      expect.objectContaining({
        title: "Phim tư liệu kiểm thử",
        url: "https://www.youtube.com/watch?v=AbCdEfGhI12",
        channel_name: "Đài truyền hình kiểm thử",
        trust_level: "official",
        scope: "exact_artifact",
      }),
    ]);
    expect(learning.generation_status).toBe("fallback_missing_source");
    expect(narration.transcript).toBe(artifact.name);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });
});
