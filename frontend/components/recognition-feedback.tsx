"use client";

import { useState } from "react";
import { CheckIcon } from "@/components/icons";
import { sendRecognitionFeedback } from "@/lib/api";
import type { RecognitionCandidate } from "@/lib/types";

interface RecognitionFeedbackProps {
  requestId: string;
  selectedItemId: string;
  candidates: RecognitionCandidate[];
  onResolved?: (itemId: string | null) => void;
}

type FeedbackState = "ask" | "correcting" | "submitting" | "done" | "error";

export function RecognitionFeedback({
  requestId,
  selectedItemId,
  candidates,
  onResolved,
}: RecognitionFeedbackProps) {
  const [state, setState] = useState<FeedbackState>("ask");
  const [message, setMessage] = useState("");

  async function submit(
    isCorrect: boolean,
    correction?: string,
    noneOfTheAbove = false,
  ) {
    setState("submitting");
    setMessage("");
    try {
      await sendRecognitionFeedback(requestId, {
        is_correct: isCorrect,
        selected_item_id: correction || (isCorrect ? selectedItemId : undefined),
        none_of_the_above: noneOfTheAbove,
      });
      setState("done");
      if (!isCorrect) onResolved?.(correction || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Chưa thể gửi phản hồi.");
      setState("error");
    }
  }

  if (state === "done") {
    return (
      <aside className="feedback-card feedback-done" role="status">
        <CheckIcon />
        <div>
          <strong>Cảm ơn em đã xác nhận!</strong>
          <p>Phản hồi này giúp đánh giá và cải thiện hệ thống nhận diện.</p>
        </div>
      </aside>
    );
  }

  const uniqueCandidates = Array.from(
    new Map(
      candidates.map((candidate) => [candidate.item_id, candidate]),
    ).values(),
  ).slice(0, 3);

  return (
    <aside className="feedback-card" aria-labelledby="feedback-title">
      <div>
        <p className="eyebrow">Cùng kiểm tra AI</p>
        <h2 id="feedback-title">AI nhận đúng không?</h2>
        <p>Một lựa chọn của em sẽ giúp nhóm nghiên cứu đo độ tin cậy thực tế.</p>
      </div>

      {(state === "ask" || state === "error") && (
        <div className="feedback-actions">
          <button
            type="button"
            className="button button-success"
            onClick={() => void submit(true)}
          >
            <CheckIcon /> Đúng
          </button>
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setState("correcting")}
          >
            Chưa đúng
          </button>
        </div>
      )}

      {state === "correcting" && (
        <div className="correction-options">
          <p>Vậy đâu là kết quả phù hợp hơn?</p>
          {uniqueCandidates
            .filter((candidate) => candidate.item_id !== selectedItemId)
            .map((candidate) => (
              <button
                type="button"
                key={candidate.item_id}
                onClick={() => void submit(false, candidate.item_id)}
              >
                {candidate.name}
              </button>
            ))}
          <button
            type="button"
            onClick={() => void submit(false, undefined, true)}
          >
            Không có kết quả phù hợp
          </button>
          <button type="button" className="text-button" onClick={() => setState("ask")}>
            Quay lại
          </button>
        </div>
      )}

      {state === "submitting" && (
        <p role="status" aria-live="polite">
          Đang gửi phản hồi…
        </p>
      )}
      {state === "error" && (
        <p className="inline-error" role="alert">
          {message}
        </p>
      )}
    </aside>
  );
}
