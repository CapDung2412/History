"use client";

import {
  PauseIcon,
  PlayIcon,
  StopIcon,
  VolumeIcon,
} from "@/components/icons";
import { useTextToSpeech } from "@/lib/tts";

interface TtsControlsProps {
  text: string;
  contentId: string;
}

export function TtsControls({ text, contentId }: TtsControlsProps) {
  return <TtsContent key={`${contentId}:${text}`} text={text} contentId={contentId} />;
}

function TtsContent({ text, contentId }: TtsControlsProps) {
  const speech = useTextToSpeech(text, contentId);

  if (!text.trim()) return null;

  return (
    <section className="tts-panel" aria-labelledby="tts-title">
      <div className="tts-heading">
        <span className="tts-icon" aria-hidden="true">
          <VolumeIcon />
        </span>
        <div>
          <h3 id="tts-title">Nghe thuyết minh</h3>
          <p>Giọng đọc được cung cấp bởi trình duyệt của thiết bị.</p>
        </div>
      </div>

      {speech.state === "unsupported" ? (
        <p className="tts-unavailable" role="status">
          Trình duyệt này chưa hỗ trợ chức năng đọc thành tiếng. Em có thể theo dõi
          toàn bộ nội dung ở phần phụ đề bên dưới.
        </p>
      ) : (
        <div className="tts-actions">
          {speech.state === "idle" || speech.state === "error" ? (
            <>
              <button
                type="button"
                className="button button-primary button-compact"
                onClick={speech.playShort}
              >
                <PlayIcon />
                Nghe 30 giây
              </button>
              <button
                type="button"
                className="button button-secondary button-compact"
                onClick={speech.playFull}
              >
                <VolumeIcon />
                Nghe đầy đủ
              </button>
            </>
          ) : (
            <>
              {speech.state === "speaking" ? (
                <button
                  type="button"
                  className="button button-secondary button-compact"
                  onClick={speech.pause}
                >
                  <PauseIcon />
                  Tạm dừng
                </button>
              ) : (
                <button
                  type="button"
                  className="button button-secondary button-compact"
                  onClick={speech.resume}
                >
                  <PlayIcon />
                  Tiếp tục
                </button>
              )}
              <button
                type="button"
                className="button button-ghost button-compact"
                onClick={speech.stop}
              >
                <StopIcon />
                Dừng
              </button>
            </>
          )}
        </div>
      )}

      <div className="tts-caption" aria-live="polite">
        <span>Phụ đề</span>
        <p>{speech.subtitle}</p>
      </div>
      {speech.state === "error" && (
        <p className="inline-error" role="alert">
          Chưa thể phát thuyết minh. Em hãy kiểm tra âm lượng hoặc thử lại.
        </p>
      )}
    </section>
  );
}
