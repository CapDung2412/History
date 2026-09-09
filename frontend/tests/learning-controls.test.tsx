import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StoryExplorer } from "@/components/story-explorer";
import { ChallengeCard } from "@/components/challenge-card";
import { AccessibilityToolbar } from "@/components/accessibility-toolbar";
import { artifact, challenge, story } from "./fixtures";

describe("reading and learning controls", () => {
  it("supports keyboard tabs and keeps unverified sources marked as pending", async () => {
    const user = userEvent.setup();
    render(<StoryExplorer artifact={artifact} story={story} />);
    const quick = screen.getByRole("tab", { name: /Nhìn nhanh/ });
    quick.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Câu chuyện/ })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveTextContent(artifact.description);
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: /Khám phá sâu/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Nguồn đã được ghi lại nhưng chưa được kiểm chứng đầy đủ.")).toBeInTheDocument();
    await user.keyboard("{Home}");
    expect(quick).toHaveFocus();
  });

  it("explains both incorrect and correct answers and allows a retry", async () => {
    const user = userEvent.setup();
    render(<ChallengeCard challenge={challenge} onExploreAnother={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Kiểm tra đáp án" })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "Ảnh tư liệu" }));
    await user.click(screen.getByRole("button", { name: "Kiểm tra đáp án" }));
    expect(screen.getByRole("status")).toHaveTextContent("Chưa đúng rồi.");
    expect(screen.getByRole("status")).toHaveTextContent(challenge.explanation);
    await user.click(screen.getByRole("button", { name: "Thử lại câu này" }));
    await user.click(screen.getByRole("radio", { name: "Hiện vật" }));
    await user.click(screen.getByRole("button", { name: "Kiểm tra đáp án" }));
    expect(screen.getByRole("status")).toHaveTextContent("Chính xác!");
  });

  it("does not fabricate a question when challenge data is missing", () => {
    render(<ChallengeCard challenge={null} onExploreAnother={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Câu hỏi đang được bổ sung" })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("applies accessibility controls even when browser storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("Blocked", "SecurityError"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("Blocked", "SecurityError"); });
    render(<AccessibilityToolbar />);
    fireEvent.click(screen.getByRole("button", { name: "Tăng cỡ chữ" }));
    expect(document.documentElement.dataset.textScale).toBe("large");
    fireEvent.click(screen.getByRole("button", { name: "Tương phản" }));
    expect(document.documentElement.dataset.contrast).toBe("high");
    expect(screen.getByRole("button", { name: "Tương phản" })).toHaveAttribute("aria-pressed", "true");
  });
});
