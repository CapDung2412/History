"use client";

import { FormEvent, useState } from "react";
import { ArrowIcon, CheckIcon, RotateIcon } from "@/components/icons";
import type { Challenge } from "@/lib/types";

interface ChallengeCardProps {
  challenge: Challenge | null;
  onExploreAnother: () => void;
}

export function ChallengeCard({
  challenge,
  onExploreAnother,
}: ChallengeCardProps) {
  return <ChallengeContent key={challenge?.id || "missing"} challenge={challenge} onExploreAnother={onExploreAnother} />;
}

function ChallengeContent({
  challenge,
  onExploreAnother,
}: ChallengeCardProps) {
  const [selected, setSelected] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (!challenge || !challenge.options.length || !challenge.correct_option_id) {
    return (
      <section
        className="challenge-card challenge-empty"
        aria-labelledby="challenge-title"
      >
        <p className="eyebrow">Thử thách 30 giây</p>
        <h2 id="challenge-title">Câu hỏi đang được bổ sung</h2>
        <p>
          Dữ liệu hiện tại chưa đủ chắc chắn để tạo câu hỏi cho hiện vật này.
          DiSản Lens sẽ không tự thêm dữ kiện lịch sử.
        </p>
        <button
          type="button"
          className="button button-primary"
          onClick={onExploreAnother}
        >
          Khám phá hiện vật khác
          <ArrowIcon />
        </button>
      </section>
    );
  }

  const correct = selected === challenge.correct_option_id;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (selected) setSubmitted(true);
  }

  return (
    <section className="challenge-card" aria-labelledby="challenge-title">
      <div className="challenge-heading">
        <div>
          <p className="eyebrow eyebrow-light">Thử thách 30 giây</p>
          <h2 id="challenge-title">Hiểu và ghi nhớ</h2>
        </div>
        <span className="challenge-mark" aria-hidden="true">
          ?
        </span>
      </div>
      <form onSubmit={submit}>
        <fieldset disabled={submitted}>
          <legend>{challenge.question}</legend>
          <div className="challenge-options">
            {challenge.options.map((option) => (
              <label
                key={option.id}
                className={`challenge-option ${
                  selected === option.id ? "selected" : ""
                }`}
              >
                <input
                  type="radio"
                  name={`challenge-${challenge.id}`}
                  value={option.id}
                  checked={selected === option.id}
                  onChange={() => setSelected(option.id)}
                />
                <span className="radio-mark" aria-hidden="true" />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {!submitted ? (
          <button
            type="submit"
            className="button button-cream"
            disabled={!selected}
          >
            Kiểm tra đáp án
            <ArrowIcon />
          </button>
        ) : (
          <div
            className={`challenge-feedback ${correct ? "correct" : "incorrect"}`}
            role="status"
            aria-live="polite"
          >
            <div className="feedback-heading">
              {correct ? <CheckIcon /> : <RotateIcon />}
              <strong>{correct ? "Chính xác!" : "Chưa đúng rồi."}</strong>
            </div>
            <p>{challenge.explanation}</p>
            {!correct && (
              <button
                type="button"
                className="text-button text-button-light"
                onClick={() => {
                  setSubmitted(false);
                  setSelected("");
                }}
              >
                Thử lại câu này
              </button>
            )}
          </div>
        )}
      </form>
      <button
        type="button"
        className="button button-outline-light explore-another"
        onClick={onExploreAnother}
      >
        Khám phá hiện vật khác
        <ArrowIcon />
      </button>
    </section>
  );
}
