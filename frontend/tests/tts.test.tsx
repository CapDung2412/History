import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TtsControls } from "@/components/tts-controls";

const requestNarrationMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, requestNarration: requestNarrationMock };
});

class TestUtterance {
  lang = ""; voice: unknown; rate = 1; pitch = 1;
  onstart?: () => void;
  onend?: () => void;
  onboundary?: (event: { charIndex: number }) => void;
  onerror?: (event: { error: string }) => void;
  constructor(public text: string) {}
}

function mockSpeech(
  initialVoices: Array<{ lang: string; name: string; localService?: boolean }> = [
    { lang: "vi-VN", name: "Vietnamese test voice", localService: true },
  ],
) {
  let voices = initialVoices;
  const voiceListeners = new Set<() => void>();
  const synthesis = {
    speaking: true, paused: false,
    getVoices: vi.fn(() => voices),
    speak: vi.fn(), cancel: vi.fn(),
    pause: vi.fn(() => { synthesis.paused = true; }),
    resume: vi.fn(() => { synthesis.paused = false; }),
    addEventListener: vi.fn((event: string, listener: () => void) => {
      if (event === "voiceschanged") voiceListeners.add(listener);
    }),
    removeEventListener: vi.fn((event: string, listener: () => void) => {
      if (event === "voiceschanged") voiceListeners.delete(listener);
    }),
    setVoices(nextVoices: typeof initialVoices) {
      voices = nextVoices;
      voiceListeners.forEach((listener) => listener());
    },
  };
  vi.stubGlobal("speechSynthesis", synthesis);
  vi.stubGlobal("SpeechSynthesisUtterance", TestUtterance);
  return synthesis;
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  requestNarrationMock.mockReset();
});

function fallbackNarration(variant: "short" | "full" = "full") {
  return {
    artifact_id: "test",
    variant,
    status: "fallback_required",
    cache_status: "bypass",
    transcript: "Nội dung kiểm thử. Câu thứ hai.",
    asset_id: null,
    audio_url: null,
    mime_type: null,
    notice: "Dùng giọng đọc trình duyệt.",
  };
}

describe("Vietnamese narration", () => {
  it("pauses the 30-second listening limit while the student pauses audio", async () => {
    vi.useFakeTimers();
    const synthesis = mockSpeech();
    requestNarrationMock.mockResolvedValue(fallbackNarration("short"));
    render(<TtsControls text="Nội dung kiểm thử. Câu thứ hai." contentId="test" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Nghe 30 giây" })));
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

  it("updates captions on speech boundaries and stops when changing artifact", async () => {
    const synthesis = mockSpeech();
    requestNarrationMock.mockResolvedValue(fallbackNarration("full"));
    const { rerender, unmount } = render(<TtsControls text="Câu đầu tiên. Câu thứ hai." contentId="first" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" })));
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

  it("keeps readable captions when speech synthesis is unavailable", async () => {
    requestNarrationMock.mockRejectedValue(new Error("offline"));
    render(<TtsControls text="Nội dung vẫn đọc được." contentId="unsupported" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" })));
    expect(screen.getByRole("alert")).toHaveTextContent("chưa hỗ trợ chức năng đọc thành tiếng");
    expect(screen.getByText("Nội dung vẫn đọc được.")).toBeInTheDocument();
  });

  it("uses a cached server audio asset with seek and speed controls", async () => {
    mockSpeech();
    requestNarrationMock.mockResolvedValue({
      artifact_id: "test",
      variant: "full",
      status: "ready",
      cache_status: "hit",
      transcript: "Bản thuyết minh đã kiểm tra.",
      asset_id: "a".repeat(64),
      audio_url: `/api/v1/narrations/${"a".repeat(64)}/audio`,
      mime_type: "audio/wav",
      notice: "Sẵn sàng.",
    });
    const playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    const loadSpy = vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);

    render(<TtsControls text="Bản thuyết minh đã kiểm tra." contentId="test" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" })));

    expect(await screen.findByRole("slider", { name: "Tua bản thuyết minh" })).toBeInTheDocument();
    await waitFor(() => expect(playSpy).toHaveBeenCalledTimes(1));
    expect(loadSpy).toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "Tốc độ đọc" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("đã lưu đệm");
  });

  it("never reads Vietnamese text with an English browser voice", async () => {
    const synthesis = mockSpeech([
      { lang: "en-US", name: "English voice", localService: true },
    ]);
    requestNarrationMock.mockResolvedValue(fallbackNarration("full"));
    render(<TtsControls text="Tượng bà mẹ bằng mảnh bom." contentId="no-vi" />);

    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" })),
    );

    expect(synthesis.speak).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Thiết bị này chưa có giọng đọc tiếng Việt",
    );
  });

  it("waits for voiceschanged and then selects vi-VN", async () => {
    const synthesis = mockSpeech([]);
    requestNarrationMock.mockResolvedValue(fallbackNarration("full"));
    render(<TtsControls text="Tượng bà mẹ bằng mảnh bom." contentId="late-vi" />);

    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" })),
    );
    expect(synthesis.speak).not.toHaveBeenCalled();

    act(() => {
      synthesis.setVoices([
        { lang: "vi-VN", name: "Giọng Việt", localService: true },
      ]);
    });
    expect(synthesis.speak).toHaveBeenCalledTimes(1);
    expect(synthesis.speak.mock.calls[0][0]).toMatchObject({ lang: "vi-VN" });
  });

  it("lets the operating system choose vi-VN when the browser exposes no voices", async () => {
    vi.useFakeTimers();
    const synthesis = mockSpeech([]);
    requestNarrationMock.mockResolvedValue(fallbackNarration("full"));
    render(<TtsControls text="Tượng bà mẹ bằng mảnh bom." contentId="empty-voices" />);

    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Nghe đầy đủ" })),
    );
    expect(synthesis.speak).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1_200));
    expect(synthesis.speak).toHaveBeenCalledTimes(1);
    expect(synthesis.speak.mock.calls[0][0]).toMatchObject({ lang: "vi-VN" });
    expect((synthesis.speak.mock.calls[0][0] as TestUtterance).voice).toBeUndefined();
  });
});
