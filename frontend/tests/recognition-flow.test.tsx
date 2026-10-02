import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HeritageLensApp } from "@/components/heritage-lens-app";
import * as api from "@/lib/api";
import { artifact, challenge, recognition, secondCandidate, story } from "./fixtures";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  recognizeImage: vi.fn(), getArtifact: vi.fn(), getArtifactStory: vi.fn(),
  getArtifactChallenge: vi.fn(), sendRecognitionFeedback: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.recognizeImage).mockResolvedValue(recognition());
  vi.mocked(api.getArtifact).mockResolvedValue(artifact);
  vi.mocked(api.getArtifactStory).mockResolvedValue(story);
  vi.mocked(api.getArtifactChallenge).mockResolvedValue(challenge);
  vi.mocked(api.sendRecognitionFeedback).mockResolvedValue({ status: "recorded", request_id: recognition().request_id });
});

async function analyze() {
  const user = userEvent.setup();
  render(<HeritageLensApp />);
  const file = new File(["image bytes"], "photo.jpg", { type: "image/jpeg" });
  await user.upload(screen.getByLabelText("Chọn tệp ảnh hiện vật"), file);
  await user.click(screen.getByRole("button", { name: "Phân tích ảnh" }));
  return user;
}

describe("student recognition journey", () => {
  it("opens a curated artifact without requiring image recognition", async () => {
    const user = userEvent.setup();
    render(<HeritageLensApp />);
    await user.click(
      screen.getByRole("button", {
        name: "Khám phá Tượng Bà mẹ bằng mảnh bom",
      }),
    );

    expect(api.recognizeImage).not.toHaveBeenCalled();
    expect(api.getArtifact).toHaveBeenCalledWith("tuong-ba-me-bang-manh-bom");
    expect(
      await screen.findByRole("heading", { name: "Khám phá theo nhịp của em" }),
    ).toBeInTheDocument();
  });

  it("loads accepted content with the canonical item ID and follows a corrected result", async () => {
    const user = await analyze();
    expect(await screen.findByRole("heading", { name: "Đã nhận ra hiện vật" })).toBeInTheDocument();
    expect(api.getArtifact).toHaveBeenCalledWith(artifact.item_id);
    expect(screen.getByRole("tab", { name: /Nhìn nhanh/ })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: "Chưa đúng" }));
    vi.mocked(api.getArtifact).mockResolvedValue({ ...artifact, item_id: secondCandidate.item_id, name: secondCandidate.name });
    await user.click(screen.getByRole("button", { name: secondCandidate.name }));
    expect(await screen.findByRole("heading", { name: "Hiện vật em muốn khám phá" })).toBeInTheDocument();
    expect(api.getArtifact).toHaveBeenLastCalledWith(secondCandidate.item_id);
    expect(api.sendRecognitionFeedback).toHaveBeenCalledWith(recognition().request_id, expect.objectContaining({ is_correct: false, selected_item_id: secondCandidate.item_id }));
  });

  it("waits for Top-3 selection, then removes candidate buttons and opens the chosen story", async () => {
    const topThreeResult = recognition("needs_confirmation");
    topThreeResult.candidates.push({
      ...secondCandidate,
      item_id: "test-third-candidate",
      name: "Hiện vật thử nghiệm thứ ba",
      score: 0.52,
    });
    vi.mocked(api.recognizeImage).mockResolvedValue(topThreeResult);
    const user = await analyze();
    await screen.findByRole("heading", { name: "Em thấy hiện vật nào giống nhất?" });
    const candidateList = screen.getByRole("list", {
      name: "Các kết quả nhận diện gần nhất",
    });
    const candidateCards = within(candidateList).getAllByRole("listitem");
    expect(candidateCards).toHaveLength(3);
    candidateCards.forEach((card) => {
      expect(within(card).getByRole("img")).toBeInTheDocument();
    });
    expect(api.getArtifact).not.toHaveBeenCalled();
    vi.mocked(api.getArtifact).mockResolvedValue({ ...artifact, item_id: secondCandidate.item_id });
    await user.click(screen.getAllByRole("button", { name: "Chọn hiện vật này" })[1]);
    await screen.findByRole("heading", { name: "Hiện vật em muốn khám phá" });
    expect(api.getArtifact).toHaveBeenCalledWith(secondCandidate.item_id);
    expect(screen.queryByRole("button", { name: "Chọn hiện vật này" })).not.toBeInTheDocument();
  });

  it("shows retake guidance without opening low-confidence content", async () => {
    const result = recognition("rejected");
    result.quality = { ...result.quality, status: "failed", issues: [{ code: "dark", message: "Ảnh quá tối", guidance: "Di chuyển tới nơi đủ sáng." }] };
    vi.mocked(api.recognizeImage).mockResolvedValue(result);
    const user = await analyze();
    await screen.findByRole("heading", { name: "Ảnh cần được chụp lại" });
    expect(screen.getByText("Di chuyển tới nơi đủ sáng.")).toBeInTheDocument();
    expect(api.getArtifact).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Chụp hoặc chọn ảnh khác" }));
    expect(screen.getByRole("button", { name: "Mở máy ảnh" })).toBeEnabled();
  });

  it("records none-of-the-above without fetching an arbitrary artifact", async () => {
    vi.mocked(api.recognizeImage).mockResolvedValue(recognition("needs_confirmation"));
    const user = await analyze();
    await user.click(await screen.findByRole("button", { name: "Không có kết quả phù hợp" }));
    await screen.findByRole("heading", { name: "Không chọn một kết quả chưa phù hợp" });
    expect(api.sendRecognitionFeedback).toHaveBeenCalledWith(recognition().request_id, expect.objectContaining({ none_of_the_above: true, is_correct: false }));
    expect(api.getArtifact).not.toHaveBeenCalled();
  });

  it("reports network failure and allows retry", async () => {
    vi.mocked(api.recognizeImage).mockRejectedValue(new Error("Kết nối thử nghiệm bị ngắt"));
    const user = await analyze();
    expect(await screen.findByRole("alert")).toHaveTextContent("Kết nối thử nghiệm bị ngắt");
    await user.click(screen.getByRole("button", { name: "Thử lại" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Mở máy ảnh" })).toBeEnabled());
  });
});
