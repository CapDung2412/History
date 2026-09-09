"use client";

import { useEffect, useState } from "react";
import { CheckIcon, SparkIcon } from "@/components/icons";

const STEPS = [
  "Kiểm tra độ sáng và độ nét",
  "Mã hóa đặc trưng hình ảnh",
  "Đối chiếu kho hiện vật",
  "Chuẩn bị câu chuyện",
];

export function AnalysisLoader() {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveStep((current) => Math.min(current + 1, STEPS.length - 1));
    }, 1500);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="analysis-card" aria-labelledby="analysis-title">
      <div className="analysis-orbit" aria-hidden="true">
        <span />
        <SparkIcon />
      </div>
      <p className="eyebrow">DiSản Lens đang quan sát</p>
      <h2 id="analysis-title">Đang phân tích ảnh…</h2>
      <p className="analysis-description">
        Quá trình này có thể mất vài giây, nhất là khi mô hình vừa khởi động.
      </p>
      <ol className="analysis-steps">
        {STEPS.map((step, index) => (
          <li
            key={step}
            className={
              index < activeStep
                ? "complete"
                : index === activeStep
                  ? "active"
                  : ""
            }
          >
            <span className="step-marker">
              {index < activeStep ? <CheckIcon /> : index + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
      <p className="visually-hidden" role="status" aria-live="polite">
        {STEPS[activeStep]}
      </p>
    </section>
  );
}
