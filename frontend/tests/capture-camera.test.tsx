import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CapturePanel } from "@/components/capture-panel";
import { CameraDialog } from "@/components/camera-dialog";

describe("camera and upload", () => {
  it("rejects unsupported files and oversize images before sending", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const onAnalyze = vi.fn();
    render(<CapturePanel busy={false} onAnalyze={onAnalyze} />);
    const input = screen.getByLabelText("Chọn tệp ảnh hiện vật");
    await user.upload(input, new File(["pdf"], "file.pdf", { type: "application/pdf" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Hãy chọn ảnh JPG, PNG hoặc WEBP.");
    const large = new File(["image"], "large.jpg", { type: "image/jpeg" });
    Object.defineProperty(large, "size", { value: 13 * 1024 * 1024 });
    await user.upload(input, large);
    expect(screen.getByRole("alert")).toHaveTextContent("Ảnh lớn hơn 12 MB");
    expect(onAnalyze).not.toHaveBeenCalled();
  });

  it("offers the native camera input when browser permission is denied", async () => {
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(new DOMException("Denied", "NotAllowedError")) } });
    const user = userEvent.setup();
    render(<CapturePanel busy={false} onAnalyze={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Mở máy ảnh" }));
    const fallbackInput = screen.getByLabelText("Chụp bằng camera thiết bị");
    const click = vi.spyOn(fallbackInput, "click");
    await user.click(await screen.findByRole("button", { name: "Dùng camera thiết bị" }));
    expect(click).toHaveBeenCalledOnce();
    expect(fallbackInput).toHaveAttribute("capture", "environment");
    expect(screen.getByRole("button", { name: "Mở máy ảnh" })).toHaveFocus();
  });

  it("stops camera tracks when the dialog unmounts", async () => {
    const stop = vi.fn();
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) } });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const { unmount } = render(<CameraDialog open onClose={vi.fn()} onCapture={vi.fn()} onFallback={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Chụp ảnh" })).toBeEnabled());
    unmount();
    expect(stop).toHaveBeenCalled();
  });

  it("stops a stream that arrives after the dialog has closed", async () => {
    const stop = vi.fn();
    let resolveStream!: (stream: unknown) => void;
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockImplementation(() => new Promise((resolve) => { resolveStream = resolve; })) } });
    const { unmount } = render(<CameraDialog open onClose={vi.fn()} onCapture={vi.fn()} onFallback={vi.fn()} />);
    unmount();
    resolveStream({ getTracks: () => [{ stop }] });
    await waitFor(() => expect(stop).toHaveBeenCalledOnce());
  });
});
