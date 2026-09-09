"use client";

import { useEffect, useRef, useState } from "react";
import { AnalysisLoader } from "@/components/analysis-loader";
import { CapturePanel } from "@/components/capture-panel";
import { ChallengeCard } from "@/components/challenge-card";
import { AlertIcon, ArrowIcon, CheckIcon, RotateIcon } from "@/components/icons";
import { RecognitionFeedback } from "@/components/recognition-feedback";
import { RecognitionResult } from "@/components/recognition-result";
import { StoryExplorer } from "@/components/story-explorer";
import {
  getArtifact,
  getArtifactChallenge,
  getArtifactStory,
  recognizeImage,
  sendRecognitionFeedback,
} from "@/lib/api";
import type {
  Artifact,
  ArtifactStory,
  Challenge,
  RecognitionResponse,
} from "@/lib/types";

type View =
  | "capture"
  | "analyzing"
  | "result"
  | "loading_content"
  | "experience"
  | "no_match"
  | "error";

interface ExperienceData {
  artifact: Artifact;
  story: ArtifactStory;
  challenge: Challenge | null;
}

export function HeritageLensApp() {
  const [view, setView] = useState<View>("capture");
  const [result, setResult] = useState<RecognitionResponse | null>(null);
  const [experience, setExperience] = useState<ExperienceData | null>(null);
  const [selectedByUser, setSelectedByUser] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [resetToken, setResetToken] = useState(0);
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (view !== "capture") {
      outputRef.current?.focus({ preventScroll: true });
      outputRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [view]);

  async function analyze(file: File) {
    setView("analyzing");
    setError("");
    setNotice("");
    setExperience(null);
    setSelectedByUser(false);
    try {
      const recognition = await recognizeImage(file);
      setResult(recognition);
      if (recognition.recognition_status === "accepted") {
        const selected = recognition.selected_item || recognition.candidates[0];
        if (!selected) {
          setView("result");
          return;
        }
        setView("loading_content");
        await loadExperience(selected.item_id);
      } else {
        setView("result");
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Chưa thể phân tích ảnh. Em hãy thử lại.",
      );
      setView("error");
    }
  }

  async function loadExperience(itemId: string) {
    try {
      const [artifactResult, storyResult, challengeResult] =
        await Promise.allSettled([
          getArtifact(itemId),
          getArtifactStory(itemId),
          getArtifactChallenge(itemId),
        ]);

      if (artifactResult.status === "rejected") throw artifactResult.reason;
      const artifact = artifactResult.value;
      const story =
        storyResult.status === "fulfilled"
          ? storyResult.value
          : storyFromArtifact(artifact);
      const challenge =
        challengeResult.status === "fulfilled" ? challengeResult.value : null;

      if (storyResult.status === "rejected" || challengeResult.status === "rejected") {
        setNotice(
          "Một phần nội dung mở rộng đang tạm gián đoạn. Thông tin hiện vật vẫn được lấy từ kho dữ liệu gốc.",
        );
      }
      setExperience({ artifact, story, challenge });
      setView("experience");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Chưa thể tải nội dung hiện vật.",
      );
      setView("error");
    }
  }

  async function selectCandidate(itemId: string | null) {
    if (!result) return;
    setSelecting(true);
    setSelectedByUser(true);
    setNotice("");
    const topItemId = result.candidates[0]?.item_id;

    try {
      await sendRecognitionFeedback(result.request_id, {
        is_correct: Boolean(itemId && itemId === topItemId),
        selected_item_id: itemId || undefined,
        none_of_the_above: itemId == null,
      });
    } catch {
      setNotice(
        "Hiện chưa lưu được phản hồi của em, nhưng em vẫn có thể tiếp tục khám phá.",
      );
    }

    if (!itemId) {
      setSelecting(false);
      setView("no_match");
      return;
    }

    setView("loading_content");
    await loadExperience(itemId);
    setSelecting(false);
  }

  function reset() {
    setView("capture");
    setResult(null);
    setExperience(null);
    setError("");
    setNotice("");
    setSelecting(false);
    setSelectedByUser(false);
    setResetToken((current) => current + 1);
    window.setTimeout(() => {
      document.getElementById("nhan-dien")?.scrollIntoView({ behavior: "smooth" });
    });
  }

  return (
    <>
      <CapturePanel
        busy={view === "analyzing" || view === "loading_content" || selecting}
        onAnalyze={(file) => void analyze(file)}
        resetToken={resetToken}
      />

      <div ref={outputRef} tabIndex={-1} className="recognition-output">
        {view === "analyzing" && <AnalysisLoader />}
        {view === "loading_content" && <ContentLoader />}
        {view === "result" && result && (
          <RecognitionResult
            result={result}
            onSelect={(itemId) => void selectCandidate(itemId)}
            onRetry={reset}
            selecting={selecting}
          />
        )}
        {view === "experience" && result && experience && (
          <div className="experience-stack">
            {notice && (
              <p className="service-notice" role="status">
                {notice}
              </p>
            )}
            <RecognitionResult
              result={result}
              onSelect={(itemId) => void selectCandidate(itemId)}
              onRetry={reset}
              confirmedItemId={selectedByUser ? experience.artifact.item_id : undefined}
            />
            {!selectedByUser && (
              <RecognitionFeedback
                requestId={result.request_id}
                selectedItemId={experience.artifact.item_id}
                candidates={result.candidates}
                onResolved={(itemId) => {
                  setSelectedByUser(true);
                  if (!itemId) setView("no_match");
                  else {
                    setView("loading_content");
                    void loadExperience(itemId);
                  }
                }}
              />
            )}
            <StoryExplorer artifact={experience.artifact} story={experience.story} />
            <ChallengeCard challenge={experience.challenge} onExploreAnother={reset} />
          </div>
        )}
        {view === "no_match" && (
          <NoMatchResult notice={notice} onRetry={reset} />
        )}
        {view === "error" && <ErrorResult message={error} onRetry={reset} />}
      </div>
    </>
  );
}

function ContentLoader() {
  return (
    <section className="content-loader" aria-labelledby="content-loader-title">
      <span className="content-loader-mark" aria-hidden="true">
        <CheckIcon />
      </span>
      <p className="eyebrow">Đã nhận diện</p>
      <h2 id="content-loader-title">Đang mở câu chuyện hiện vật…</h2>
      <p role="status" aria-live="polite">
        DiSản Lens đang lấy nội dung từ kho dữ liệu lịch sử.
      </p>
    </section>
  );
}

function NoMatchResult({
  notice,
  onRetry,
}: {
  notice: string;
  onRetry: () => void;
}) {
  return (
    <section className="result-card result-rejected" aria-labelledby="no-match-title">
      <div className="result-status-icon result-status-neutral" aria-hidden="true">
        <CheckIcon />
      </div>
      <p className="eyebrow">{notice ? "Lựa chọn của em" : "Đã ghi nhận phản hồi"}</p>
      <h2 id="no-match-title">Không chọn một kết quả chưa phù hợp</h2>
      <p className="result-lead">
        Cảm ơn em. Hệ thống sẽ không đoán tên hiện vật. Em hãy thử chụp chính
        diện, đủ sáng và đưa hiện vật vào trọn khung.
      </p>
      {notice && <p className="inline-error">{notice}</p>}
      <button type="button" className="button button-primary" onClick={onRetry}>
        <RotateIcon />
        Thử ảnh khác
      </button>
    </section>
  );
}

function ErrorResult({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section className="result-card result-error" aria-labelledby="error-title">
      <div className="result-status-icon result-status-warning" aria-hidden="true">
        <AlertIcon />
      </div>
      <p className="eyebrow">Kết nối bị gián đoạn</p>
      <h2 id="error-title">Chưa thể hoàn thành nhận diện</h2>
      <p className="result-lead" role="alert">
        {message}
      </p>
      <p>Ảnh của em không được lưu lại sau yêu cầu này.</p>
      <button type="button" className="button button-primary" onClick={onRetry}>
        Thử lại
        <ArrowIcon />
      </button>
    </section>
  );
}

function storyFromArtifact(artifact: Artifact): ArtifactStory {
  return {
    item_id: artifact.item_id,
    quick: {
      title: artifact.title || artifact.name,
      category: artifact.category,
      period: artifact.historical_period || artifact.period,
      year: artifact.year,
      image: artifact.images[0] || null,
    },
    overview: {
      description: artifact.description,
      event: artifact.event,
      paragraphs: artifact.description ? [artifact.description] : [],
    },
    deep: {
      description: artifact.description,
      event: artifact.event,
      images: artifact.images,
      source: artifact.source,
      source_verified: artifact.source_verified,
    },
  };
}
