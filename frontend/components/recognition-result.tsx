"use client";

import { useState } from "react";
import {
  AlertIcon,
  ArrowIcon,
  CheckIcon,
  RotateIcon,
} from "@/components/icons";
import { toAssetUrl } from "@/lib/api";
import {
  formatCategory,
  formatDuration,
  formatPeriod,
  formatSimilarity,
} from "@/lib/format";
import type {
  RecognitionCandidate,
  RecognitionResponse,
} from "@/lib/types";

interface RecognitionResultProps {
  result: RecognitionResponse;
  onSelect: (itemId: string | null) => void;
  onRetry: () => void;
  selecting?: boolean;
  confirmedItemId?: string;
}

export function RecognitionResult({
  result,
  onSelect,
  onRetry,
  selecting = false,
  confirmedItemId,
}: RecognitionResultProps) {
  if (result.recognition_status === "rejected") {
    return <RejectedResult result={result} onRetry={onRetry} />;
  }

  if (result.recognition_status === "needs_confirmation" && !confirmedItemId) {
    return (
      <ConfirmationResult
        result={result}
        onSelect={onSelect}
        onRetry={onRetry}
        selecting={selecting}
      />
    );
  }

  const selected = confirmedItemId
    ? result.candidates.find((candidate) => candidate.item_id === confirmedItemId)
    : result.selected_item || result.candidates[0];
  return (
    <section className="result-card result-accepted" aria-labelledby="accepted-title">
      <div className="result-status-icon result-status-success" aria-hidden="true">
        <CheckIcon />
      </div>
      <p className="eyebrow">{confirmedItemId ? "Em đã chọn kết quả phù hợp" : result.confidence_label}</p>
      <h2 id="accepted-title">{confirmedItemId ? "Hiện vật em muốn khám phá" : "Đã nhận ra hiện vật"}</h2>
      {selected ? (
        <CandidateSummary candidate={selected} />
      ) : (
        <p>Đang chuẩn bị thông tin hiện vật…</p>
      )}
      <TechnicalSummary result={result} />
    </section>
  );
}

function RejectedResult({
  result,
  onRetry,
}: Pick<RecognitionResultProps, "result" | "onRetry">) {
  const qualityFailed = result.quality.status === "failed";
  return (
    <section className="result-card result-rejected" aria-labelledby="rejected-title">
      <div className="result-status-icon result-status-warning" aria-hidden="true">
        <AlertIcon />
      </div>
      <p className="eyebrow">{result.confidence_label}</p>
      <h2 id="rejected-title">
        {qualityFailed
          ? "Ảnh cần được chụp lại"
          : "Chưa đủ dữ liệu để nhận diện"}
      </h2>
      <p className="result-lead">
        {qualityFailed
          ? "Em hãy làm theo gợi ý bên dưới để DiSản Lens quan sát hiện vật rõ hơn."
          : "Hệ thống sẽ không đoán khi độ tương đồng còn thấp. Em hãy thử một góc chụp rõ và gần hơn."}
      </p>
      {result.quality.issues.length > 0 && (
        <ul className="quality-issues">
          {result.quality.issues.map((issue) => (
            <li key={`${issue.code}-${issue.message}`}>
              <AlertIcon />
              <div>
                <strong>{issue.message}</strong>
                {issue.guidance && <p>{issue.guidance}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="button button-primary" onClick={onRetry}>
        <RotateIcon />
        Chụp hoặc chọn ảnh khác
      </button>
      <TechnicalSummary result={result} />
    </section>
  );
}

function ConfirmationResult({
  result,
  onSelect,
  onRetry,
  selecting,
}: RecognitionResultProps) {
  const unique = Array.from(
    new Map(
      result.candidates.map((candidate) => [candidate.item_id, candidate]),
    ).values(),
  ).slice(0, 3);

  return (
    <section className="confirmation-section" aria-labelledby="confirmation-title">
      <div className="section-heading section-heading-centered">
        <p className="eyebrow">{result.confidence_label}</p>
        <h2 id="confirmation-title">Em thấy hiện vật nào giống nhất?</h2>
        <p>
          Ảnh có vài kết quả gần nhau. Hãy quan sát hình dáng và tên hiện vật
          rồi chọn một đáp án phù hợp.
        </p>
      </div>
      <div
        className="candidate-grid"
        role="list"
        aria-label="Các kết quả nhận diện gần nhất"
      >
        {unique.map((candidate, index) => (
          <article
            className="candidate-card"
            key={candidate.item_id}
            role="listitem"
          >
            <CandidateImage candidate={candidate} />
            <div className="candidate-body">
              <span className="candidate-number">Gợi ý {index + 1}</span>
              <h3>{candidate.name}</h3>
              <p className="candidate-meta">
                {formatCategory(candidate.category)}
                <span aria-hidden="true">•</span>
                {formatPeriod(
                  candidate.historical_period || candidate.period,
                  candidate.year,
                )}
              </p>
              <p className="similarity-label">
                Độ tương đồng: <strong>{formatSimilarity(candidate.score)}</strong>
              </p>
              <button
                type="button"
                className="button button-primary button-full"
                onClick={() => onSelect(candidate.item_id)}
                disabled={selecting}
              >
                Chọn hiện vật này
                <ArrowIcon />
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="none-choice">
        <button
          type="button"
          className="button button-ghost"
          onClick={() => onSelect(null)}
          disabled={selecting}
        >
          Không có kết quả phù hợp
        </button>
        <button
          type="button"
          className="text-button"
          onClick={onRetry}
          disabled={selecting}
        >
          Chụp lại ảnh khác
        </button>
      </div>
      <TechnicalSummary result={result} />
    </section>
  );
}

function CandidateSummary({ candidate }: { candidate: RecognitionCandidate }) {
  return (
    <div className="accepted-summary">
      <CandidateImage candidate={candidate} />
      <div>
        <h3>{candidate.name}</h3>
        <p>{formatCategory(candidate.category)}</p>
        <p>
          {formatPeriod(
            candidate.historical_period || candidate.period,
            candidate.year,
          )}
        </p>
        <p className="similarity-label">
          Độ tương đồng: <strong>{formatSimilarity(candidate.score)}</strong>
        </p>
      </div>
    </div>
  );
}

function CandidateImage({ candidate }: { candidate: RecognitionCandidate }) {
  const imageUrl = toAssetUrl(candidate.image_url);
  const [imageFailed, setImageFailed] = useState(false);

  return imageUrl && !imageFailed ? (
    <div className="candidate-image">
      {/* Backend URLs are runtime-configured, so a native image is used here. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={imageUrl}
        alt={candidate.image_caption || `Ảnh của ${candidate.name}`}
        loading="eager"
        decoding="async"
        onError={() => setImageFailed(true)}
      />
    </div>
  ) : (
    <div className="candidate-image candidate-placeholder" aria-hidden="true">
      <span>DiSản Lens</span>
    </div>
  );
}

function TechnicalSummary({ result }: { result: RecognitionResponse }) {
  const duration = formatDuration(result.timings_ms.total);
  return (
    <details className="technical-details">
      <summary>Thông tin kỹ thuật về kết quả</summary>
      <dl>
        {result.top_score != null && (
          <div>
            <dt>Điểm Top-1</dt>
            <dd>{formatSimilarity(result.top_score)}</dd>
          </div>
        )}
        {result.score_margin != null && (
          <div>
            <dt>Khoảng cách Top-1 / Top-2</dt>
            <dd>{formatSimilarity(result.score_margin)}</dd>
          </div>
        )}
        {duration && (
          <div>
            <dt>Thời gian xử lý</dt>
            <dd>{duration}</dd>
          </div>
        )}
      </dl>
      <p>Đây là điểm tương đồng vector, không phải phần trăm chính xác.</p>
    </details>
  );
}
