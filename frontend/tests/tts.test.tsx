import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TtsControls } from "@/components/tts-controls";

class TestUtterance {
  lang = ""; voice: unknown; rate = 1; pitch = 1;
  onstart?: () => void;
  onend?: () => void;
  onboundary?: (event: { charIndex: number }) => void;
  onerror?: (event: { error: string }) => void;
  constructor(public text: string) {}
}

function mockSpeech() {
  const synthesis = {
    speaking: true, paused: false,
    getVoices: vi.fn(() => [{ lang: "vi-VN", name: "Vietnamese test voice" }]),
    speak: vi.fn(), cancel: vi.fn(),
    pause: vi.fn(() => { synthesis.paused = true; }),
    resume: vi.fn(() => { synthesis.paused = false; }),
  };
  vi.stubGlobal("speechSynthesis", synthesis);
  vi.stubGlobal("SpeechSynthesisUtterance", TestUtterance);
  return synthesis;
}

afterEach(() => vi.useRealTimers());

describe("Vietnamese narration", () => {
  it("pauses the 30-second listening limit while the student pauses audio", () => {
    vi.useFakeTimers();
    const synthesis = mockSpeech();
    render(<TtsControls text="Nội dung kiểm thử. Câu thứ hai." contentId="test" />);
    fireEvent.click(screen.getByRole("button", { name: "Nghe 30 giây" }));
    expect(synthesis.speak.mock.calls[0][0]).toMatchObject({ lang: "vi-VN" });
    act(() => vi.advanceTimersByTime(10_000));
    fireEvent.click(screen.getByRole("button", { name: "Tạm dừng" }));
    const callsAtPause = synthesis.cancel.mock.calls.length;
    act(() => vi.advanceTimersByTime(60_000));
    expect(synthesis.cancel).toHaveBeenCalledTimes(callsAtPause);
    fireEvent.click(screen.getByRole("button", { name: "Tiếp tục" }));
    act(() => vi.advanceTimersByTime(19_000));
    expect(screen.getByRole("button", { name: "Tạm dừng" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1_000));
    expect(screen.getByRole("button", { name: "Nghe 30 giây" })).toBeInTheDocument();
    expect(synthesis.cancel).toHaveBeenCalledTimes(callsAtPause + 1);
  });

  it("updates captions on speech boundaries and stops when changing artifact", () => {
    const synthesis = mockSpeech();
    const { rerender, unmount } = render(<TtsControls text="Câu đầu tiên. Câu thứ hai." contentId="first" />);
    fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" }));
    const utterance = synthesis.speak.mock.calls[0][0] as TestUtterance;
    act(() => utterance.onboundary?.({ charIndex: 14 }));
    expect(screen.getByText("Câu thứ hai.")).toBeInTheDocument();
    const count = synthesis.cancel.mock.calls.length;
    rerender(<TtsControls text="Hiện vật mới." contentId="second" />);
    expect(synthesis.cancel.mock.calls.length).toBeGreaterThan(count);
    expect(screen.getByRole("button", { name: "Nghe đầy đủ" })).toBeInTheDocument();
    unmount();
    expect(synthesis.cancel).toHaveBeenCalled();
  });

  it("keeps readable captions when speech synthesis is unavailable", () => {
    render(<TtsControls text="Nội dung vẫn đọc được." contentId="unsupported" />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "chưa hỗ trợ chức năng đọc thành tiếng",
    );
    expect(screen.getByText("Nội dung vẫn đọc được.")).toBeInTheDocument();
  });
});
