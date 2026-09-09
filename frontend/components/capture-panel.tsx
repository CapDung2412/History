"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { CameraDialog } from "@/components/camera-dialog";
import { ArrowIcon, CameraIcon, RotateIcon, UploadIcon } from "@/components/icons";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_IMAGE_BYTES = 12 * 1024 * 1024;

interface CapturePanelProps {
  busy: boolean;
  onAnalyze: (file: File) => void;
  resetToken?: number;
}

export function CapturePanel({
  resetToken = 0,
  ...props
}: CapturePanelProps) {
  return <CapturePanelContent key={resetToken} {...props} />;
}

function CapturePanelContent({
  busy,
  onAnalyze,
}: Omit<CapturePanelProps, "resetToken">) {
  const uploadRef = useRef<HTMLInputElement>(null);
  const cameraFallbackRef = useRef<HTMLInputElement>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  function chooseFile(nextFile?: File) {
    if (!nextFile) return;
    if (!ACCEPTED_TYPES.includes(nextFile.type)) {
      setError("Hãy chọn ảnh JPG, PNG hoặc WEBP.");
      return;
    }
    if (nextFile.size > MAX_IMAGE_BYTES) {
      setError("Ảnh lớn hơn 12 MB. Em hãy chọn ảnh có dung lượng nhỏ hơn.");
      return;
    }
    setError("");
    setFile(nextFile);
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(nextFile);
    });
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function resetImage() {
    setFile(null);
    setError("");
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
  }

  return (
    <section className="capture-section" id="nhan-dien" aria-labelledby="capture-title">
      <div className="section-heading section-heading-centered">
        <p className="eyebrow">Bắt đầu khám phá</p>
        <h2 id="capture-title">Chụp một chứng tích</h2>
        <p>
          Đưa hiện vật vào khung, chụp rõ nét. Ảnh chỉ được xử lý để nhận
          diện và không được lưu mặc định.
        </p>
      </div>

      {!previewUrl ? (
        <div className="capture-card">
          <div className="lens-illustration" aria-hidden="true">
            <span className="lens-ring lens-ring-one" />
            <span className="lens-ring lens-ring-two" />
            <CameraIcon />
          </div>
          <h3>Em muốn dùng ảnh nào?</h3>
          <p className="capture-copy">
            Ảnh đủ sáng, không rung và có trọn hiện vật sẽ giúp kết quả đáng
            tin cậy hơn.
          </p>
          <div className="capture-actions">
            <button
              type="button"
              className="button button-primary button-large"
              onClick={() => setCameraOpen(true)}
              disabled={busy}
            >
              <CameraIcon />
              Mở máy ảnh
            </button>
            <button
              type="button"
              className="button button-secondary button-large"
              onClick={() => uploadRef.current?.click()}
              disabled={busy}
            >
              <UploadIcon />
              Chọn ảnh có sẵn
            </button>
          </div>
          <p className="file-note">Hỗ trợ JPG, PNG và WEBP · tối đa 12 MB</p>
        </div>
      ) : (
        <div className="preview-card">
          <div className="preview-heading">
            <div>
              <p className="eyebrow">Kiểm tra ảnh</p>
              <h3>Hiện vật đã nằm trọn trong khung chưa?</h3>
            </div>
            <span className="privacy-chip">Không lưu ảnh</span>
          </div>
          <div className="preview-frame">
            {/* blob URLs cannot be handled by Next Image without extra processing. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={previewUrl} alt="Ảnh hiện vật chuẩn bị nhận diện" />
            <span className="preview-corner preview-corner-tl" aria-hidden="true" />
            <span className="preview-corner preview-corner-tr" aria-hidden="true" />
            <span className="preview-corner preview-corner-bl" aria-hidden="true" />
            <span className="preview-corner preview-corner-br" aria-hidden="true" />
          </div>
          <div className="preview-checklist" aria-label="Gợi ý kiểm tra ảnh">
            <span>Kiểm tra ánh sáng</span>
            <span>Kiểm tra độ rõ nét</span>
            <span>Tránh phản chiếu kính</span>
          </div>
          <div className="preview-actions">
            <button
              type="button"
              className="button button-secondary"
              onClick={resetImage}
              disabled={busy}
            >
              <RotateIcon />
              Chọn ảnh khác
            </button>
            <button
              type="button"
              className="button button-primary"
              onClick={() => file && onAnalyze(file)}
              disabled={busy || !file}
            >
              Phân tích ảnh
              <ArrowIcon />
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      <input
        ref={uploadRef}
        className="visually-hidden"
        type="file"
        aria-label="Chọn tệp ảnh hiện vật"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleInput}
        tabIndex={-1}
      />
      <input
        ref={cameraFallbackRef}
        className="visually-hidden"
        type="file"
        aria-label="Chụp bằng camera thiết bị"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        onChange={handleInput}
        tabIndex={-1}
      />
      <CameraDialog
        open={cameraOpen}
        onClose={() => setCameraOpen(false)}
        onCapture={chooseFile}
        onFallback={() => cameraFallbackRef.current?.click()}
      />
    </section>
  );
}
