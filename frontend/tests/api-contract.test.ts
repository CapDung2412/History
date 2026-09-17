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
        references: [],
        content: {
          factual_claims: [],
          storytelling: {
            quick: { text: artifact.name, claim_ids: [] },
            one_minute: { text: artifact.description, claim_ids: [] },
          },
          deep_sections: [],
          timeline: [],
          keywords: [{ term: "hiện vật", explanation: "Từ dữ liệu." }],
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
    expect(learning.generation_status).toBe("fallback_missing_source");
    expect(narration.transcript).toBe(artifact.name);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });
});
