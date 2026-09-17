"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  PauseIcon,
  PlayIcon,
  StopIcon,
  VolumeIcon,
} from "@/components/icons";
import {
  ApiError,
  requestNarration,
  toAssetUrl,
  type NarrationResponse,
} from "@/lib/api";
import { useTextToSpeech } from "@/lib/tts";

interface TtsControlsProps {
  text: string;
  contentId: string;
}

type ServerState = "idle" | "loading" | "ready" | "fallback" | "error";
type Variant = "short" | "full";

let activeAudio: HTMLAudioElement | null = null;

export function TtsControls({ text, contentId }: TtsControlsProps) {
  const normalizedText = text.normalize("NFC");
  return (
    <TtsContent
      key={`${contentId}:${normalizedText}`}
      text={normalizedText}
      contentId={contentId}
    />
  );
}

function TtsContent({ text, contentId }: TtsControlsProps) {
  const speech = useTextToSpeech(text, contentId);
  const audioRef = useRef<HTMLAudioElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestInFlightRef = useRef(false);
  const pendingAutoPlayRef = useRef(false);
  const [serverState, setServerState] = useState<ServerState>("idle");
  const [narration, setNarration] = useState<NarrationResponse | null>(null);
  const [variant, setVariant] = useState<Variant>("full");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [notice, setNotice] = useState("");
  const audioUrl = toAssetUrl(narration?.audio_url);

  const stopAudio = useCallback((reset = true) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    if (reset) audio.currentTime = 0;
    if (activeAudio === audio) activeAudio = null;
    setIsPlaying(false);
    if (reset) setCurrentTime(0);
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    return () => {
      abortRef.current?.abort();
      if (audio) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
      }
      if (activeAudio === audio) activeAudio = null;
    };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = speech.rate;
  }, [speech.rate]);

  const startBrowserFallback = useCallback(
    (requestedVariant: Variant, message: string) => {
      pendingAutoPlayRef.current = false;
      stopAudio();
      setServerState(speech.state === "unsupported" ? "error" : "fallback");
      setNotice(message);
      if (requestedVariant === "short") speech.playShort();
      else speech.playFull();
    },
    [speech, stopAudio],
  );

  const playServerAudio = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (activeAudio && activeAudio !== audio) activeAudio.pause();
    activeAudio = audio;
    audio.playbackRate = speech.rate;
    try {
      await audio.play();
    } catch {
      setIsPlaying(false);
      setNotice("Âm thanh đã sẵn sàng. Em hãy nhấn Phát để bắt đầu.");
    }
  }, [speech.rate]);

  useEffect(() => {
    if (
      !pendingAutoPlayRef.current ||
      serverState !== "ready" ||
      !audioUrl
    ) return;
    const audio = audioRef.current;
    if (!audio) return;
    pendingAutoPlayRef.current = false;
    audio.load();
    void playServerAudio();
  }, [audioUrl, playServerAudio, serverState]);

  const requestAndPlay = useCallback(
    async (requestedVariant: Variant) => {
      if (requestInFlightRef.current) return;
      if (
        serverState === "ready" &&
        narration?.audio_url &&
        variant === requestedVariant
      ) {
        await playServerAudio();
        return;
      }
      if (
        serverState === "fallback" &&
        narration?.status === "fallback_required" &&
        variant === requestedVariant
      ) {
        startBrowserFallback(requestedVariant, narration.notice);
        return;
      }
      requestInFlightRef.current = true;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      pendingAutoPlayRef.current = false;
      speech.stop();
      stopAudio();
      setVariant(requestedVariant);
      setServerState("loading");
      setNotice("Đang chuẩn bị giọng đọc AI…");
      setNarration(null);
      setDuration(0);

      try {
        const response = await requestNarration(contentId, requestedVariant, controller.signal);
        if (controller.signal.aborted) return;
        setNarration(response);
        if (response.status === "ready" && response.audio_url) {
          pendingAutoPlayRef.current = true;
          setServerState("ready");
          setNotice(
            response.cache_status === "hit"
              ? "Đang dùng bản thuyết minh đã lưu đệm."
              : response.notice,
          );
          return;
        }
        startBrowserFallback(
          requestedVariant,
          response.notice || "Đang dùng giọng đọc có sẵn trên thiết bị.",
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof ApiError
            ? `${error.message} Đang chuyển sang giọng đọc của thiết bị.`
            : "Dịch vụ giọng đọc AI đang gián đoạn. Đang dùng giọng đọc của thiết bị.";
        startBrowserFallback(requestedVariant, message);
      } finally {
        if (abortRef.current === controller) requestInFlightRef.current = false;
      }
    },
    [
      contentId,
      narration,
      playServerAudio,
      serverState,
      speech,
      stopAudio,
      startBrowserFallback,
      variant,
    ],
  );

  if (!text.trim()) return null;

  const subtitle =
    serverState === "ready"
      ? narration?.transcript || text
      : speech.subtitle || narration?.transcript || text;
  const fallbackUnsupported = serverState === "error" && speech.state === "unsupported";
  const fallbackSpeechError = serverState === "fallback" && speech.state === "error";
  const fallbackHasNoVietnameseVoice =
    serverState === "fallback" && speech.state === "no_vietnamese_voice";

  return (
    <section className="tts-panel" aria-labelledby="tts-title">
      <div className="tts-heading">
        <span className="tts-icon" aria-hidden="true">
          <VolumeIcon />
        </span>
        <div>
          <h3 id="tts-title">Nghe thuyết minh</h3>
          <p>Ưu tiên giọng đọc AI từ máy chủ; trình duyệt là phương án dự phòng.</p>
        </div>
      </div>

      <div className="tts-actions" aria-label="Chọn độ dài thuyết minh">
        <button
          type="button"
          className="button button-primary button-compact"
          onClick={() => void requestAndPlay("short")}
          disabled={serverState === "loading"}
        >
          <PlayIcon />
          Nghe 30 giây
        </button>
        <button
          type="button"
          className="button button-secondary button-compact"
          onClick={() => void requestAndPlay("full")}
          disabled={serverState === "loading"}
        >
          <VolumeIcon />
          Nghe đầy đủ
        </button>
      </div>

      <audio
        ref={audioRef}
        src={serverState === "ready" ? audioUrl : undefined}
        preload={audioUrl ? "metadata" : "none"}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
        onDurationChange={(event) => setDuration(event.currentTarget.duration || 0)}
        onPlay={(event) => {
          if (activeAudio && activeAudio !== event.currentTarget) activeAudio.pause();
          activeAudio = event.currentTarget;
          setIsPlaying(true);
        }}
        onPause={() => setIsPlaying(false)}
        onEnded={() => {
          if (activeAudio === audioRef.current) activeAudio = null;
          setIsPlaying(false);
          setCurrentTime(0);
        }}
        onTimeUpdate={(event) => {
          const audio = event.currentTarget;
          if (variant === "short" && audio.currentTime >= 30) {
            audio.pause();
            audio.currentTime = 0;
          }
          setCurrentTime(audio.currentTime);
        }}
        onError={() => {
          if (audioUrl) {
            startBrowserFallback(
              variant,
              "File âm thanh chưa tải được. Đang dùng giọng đọc của thiết bị.",
            );
          }
        }}
      />

      {serverState === "ready" && audioUrl && (
        <div className="audio-player">
          <div className="audio-buttons">
            <button
              type="button"
              className="button button-secondary button-compact"
              onClick={() => {
                const audio = audioRef.current;
                if (!audio) return;
                if (audio.paused) void playServerAudio();
                else audio.pause();
              }}
            >
              {isPlaying ? <PauseIcon /> : <PlayIcon />}
              {isPlaying ? "Tạm dừng" : "Phát / tiếp tục"}
            </button>
            <button
              type="button"
              className="button button-ghost button-compact"
              onClick={() => stopAudio()}
            >
              <StopIcon />
              Dừng
            </button>
          </div>
          <label className="audio-timeline">
            <span className="visually-hidden">Tua bản thuyết minh</span>
            <span aria-hidden="true">{formatClock(currentTime)}</span>
            <input
              type="range"
              min="0"
              max={Math.max(variant === "short" ? Math.min(duration, 30) : duration, 0)}
              step="0.1"
              value={Math.min(currentTime, variant === "short" ? Math.min(duration, 30) : duration || 0)}
              disabled={!duration}
              aria-label="Tua bản thuyết minh"
              onChange={(event) => {
                const next = Number(event.target.value);
                if (audioRef.current) audioRef.current.currentTime = next;
                setCurrentTime(next);
              }}
            />
            <span aria-hidden="true">{formatClock(duration)}</span>
          </label>
        </div>
      )}

      {serverState === "fallback" && (
        <div className="tts-actions" aria-label="Điều khiển giọng đọc trình duyệt">
          {speech.state === "speaking" ? (
            <button type="button" className="button button-secondary button-compact" onClick={speech.pause}>
              <PauseIcon /> Tạm dừng
            </button>
          ) : speech.state === "paused" ? (
            <button type="button" className="button button-secondary button-compact" onClick={speech.resume}>
              <PlayIcon /> Tiếp tục
            </button>
          ) : null}
          <button type="button" className="button button-ghost button-compact" onClick={speech.stop}>
            <StopIcon /> Dừng
          </button>
        </div>
      )}

      <label className="speech-rate">
        <span>Tốc độ đọc</span>
        <select value={speech.rate} onChange={(event) => speech.setRate(Number(event.target.value))}>
          <option value="0.75">0,75×</option>
          <option value="1">1×</option>
          <option value="1.25">1,25×</option>
          <option value="1.5">1,5×</option>
        </select>
      </label>

      {notice && <p className="tts-notice" role="status">{notice}</p>}
      {fallbackUnsupported && (
        <p className="tts-unavailable" role="alert">
          Trình duyệt này chưa hỗ trợ chức năng đọc thành tiếng. Em vẫn có thể đọc toàn bộ phụ đề.
        </p>
      )}
      {fallbackSpeechError && (
        <p className="tts-unavailable" role="alert">
          Giọng đọc trên thiết bị đã bị gián đoạn. Em có thể thử lại hoặc đọc toàn bộ phụ đề.
        </p>
      )}
      {fallbackHasNoVietnameseVoice && (
        <p className="tts-unavailable" role="alert">
          Thiết bị này chưa có giọng đọc tiếng Việt. Hệ thống sẽ không dùng giọng tiếng Anh;
          em vẫn có thể đọc toàn bộ phụ đề.
        </p>
      )}

      <div className="tts-caption" aria-live="polite">
        <span>Phụ đề</span>
        <p>{subtitle}</p>
      </div>
    </section>
  );
}

function formatClock(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "0:00";
  const seconds = Math.floor(value);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
