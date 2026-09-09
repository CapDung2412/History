"use client";

import { useEffect, useRef, useState } from "react";
import { CameraIcon, CloseIcon } from "@/components/icons";

interface CameraDialogProps {
  open: boolean;
  onClose: () => void;
  onCapture: (file: File) => void;
  onFallback: () => void;
}

export function CameraDialog({
  open,
  onClose,
  onCapture,
  onFallback,
}: CameraDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [status, setStatus] = useState<"starting" | "ready" | "error">(
    "starting",
  );
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    const video = videoRef.current;
    const previousFocus = document.activeElement as HTMLElement | null;
    if (dialog && !dialog.open) dialog.showModal();

    let cancelled = false;
    async function startCamera() {
      setStatus("starting");
      setError("");
      try {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
          throw new Error("camera_unavailable");
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        if (!cancelled) setStatus("ready");
      } catch {
        if (!cancelled) {
          stopStream(streamRef.current);
          streamRef.current = null;
          setStatus("error");
          setError(
            "Không mở được camera trực tiếp. Em vẫn có thể dùng camera của thiết bị bằng nút bên dưới.",
          );
        }
      }
    }

    void startCamera();
    return () => {
      cancelled = true;
      stopStream(streamRef.current);
      streamRef.current = null;
      if (video) video.srcObject = null;
      if (dialog?.open) dialog.close();
      previousFocus?.focus();
    };
  }, [open]);

  function closeDialog() {
    stopStream(streamRef.current);
    streamRef.current = null;
    dialogRef.current?.close();
    onClose();
  }

  function captureFrame() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setError("Chưa thể chụp ảnh. Em hãy thử lại.");
          return;
        }
        onCapture(
          new File([blob], `di-san-lens-${Date.now()}.jpg`, {
            type: "image/jpeg",
          }),
        );
        closeDialog();
      },
      "image/jpeg",
      0.92,
    );
  }

  return (
    <dialog
      ref={dialogRef}
      className="camera-dialog"
      aria-labelledby="camera-title"
      onCancel={(event) => {
        event.preventDefault();
        closeDialog();
      }}
      onClose={() => {
        stopStream(streamRef.current);
        streamRef.current = null;
        onClose();
      }}
    >
      <div className="camera-dialog-inner">
        <div className="camera-dialog-header">
          <div>
            <p className="eyebrow eyebrow-light">Ống kính nhận diện</p>
            <h2 id="camera-title">Đưa hiện vật vào khung</h2>
          </div>
          <button
            type="button"
            className="icon-button icon-button-light"
            onClick={closeDialog}
            aria-label="Đóng camera"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="camera-viewport">
          <video
            ref={videoRef}
            muted
            playsInline
            className="camera-video"
            aria-label="Hình ảnh trực tiếp từ camera"
          />
          <div className="camera-frame" aria-hidden="true">
            <span className="corner corner-tl" />
            <span className="corner corner-tr" />
            <span className="corner corner-bl" />
            <span className="corner corner-br" />
          </div>
          {status === "starting" && (
            <div className="camera-overlay" role="status">
              Đang mở camera…
            </div>
          )}
          {status === "error" && (
            <div className="camera-overlay camera-error" role="alert">
              <p>{error}</p>
              <button
                type="button"
                className="button button-cream"
                onClick={() => {
                  closeDialog();
                  onFallback();
                }}
              >
                Dùng camera thiết bị
              </button>
            </div>
          )}
        </div>

        <p className="camera-tip">
          Giữ chắc điện thoại, tránh ánh đèn phản chiếu và chụp trọn hiện vật.
        </p>
        <button
          type="button"
          className="shutter-button"
          onClick={captureFrame}
          disabled={status !== "ready"}
          aria-label="Chụp ảnh"
        >
          <span className="shutter-ring">
            <CameraIcon />
          </span>
          Chụp ảnh
        </button>
      </div>
    </dialog>
  );
}

function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop());
}
