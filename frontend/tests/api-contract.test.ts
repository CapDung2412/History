import { describe, expect, it, vi } from "vitest";
import { getArtifact, getArtifactStory, recognizeImage, ApiError } from "@/lib/api";
import { artifact, recognition, story } from "./fixtures";

describe("backend API contract", () => {
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
});
