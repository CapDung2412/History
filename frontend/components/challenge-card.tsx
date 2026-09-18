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
  const questions = challenge
    ? challenge.questions?.length
      ? challenge.questions.slice(0, 3)
      : [challenge]
    : [];
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selected, setSelected] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState(0);
  const currentQuestion = questions[currentIndex];

  if (
    !challenge ||
    !currentQuestion ||
    !currentQuestion.options.length ||
    !currentQuestion.correct_option_id
  ) {
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

  const correct = selected === currentQuestion.correct_option_id;
  const isLastQuestion = currentIndex === questions.length - 1;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSubmitted(true);
    if (selected === currentQuestion.correct_option_id) {
      setScore((value) => value + 1);
    }
  }

  function nextQuestion() {
    setCurrentIndex((value) => value + 1);
    setSelected("");
    setSubmitted(false);
  }

  return (
    <section className="challenge-card" aria-labelledby="challenge-title">
      <div className="challenge-heading">
        <div>
          <p className="eyebrow eyebrow-light">Thử thách 30 giây</p>
          <h2 id="challenge-title">Hiểu và ghi nhớ</h2>
          <p className="challenge-progress">
            Câu {currentIndex + 1}/{questions.length}
          </p>
        </div>
        <span className="challenge-mark" aria-hidden="true">
          ?
        </span>
      </div>
      <form onSubmit={submit}>
        <fieldset disabled={submitted}>
          <legend>{currentQuestion.question}</legend>
          <div className="challenge-options">
            {currentQuestion.options.map((option) => (
              <label
                key={option.id}
                className={`challenge-option ${
                  selected === option.id ? "selected" : ""
                }`}
              >
                <input
                  type="radio"
                  name={`challenge-${currentQuestion.id}`}
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
            <p>{currentQuestion.explanation}</p>
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
            {!isLastQuestion && (
              <button
                type="button"
                className="button button-cream challenge-next"
                onClick={nextQuestion}
              >
                Câu tiếp theo
                <ArrowIcon />
              </button>
            )}
            {isLastQuestion && (
              <p className="challenge-score">
                Hoàn thành: {score}/{questions.length} câu đúng.
              </p>
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
