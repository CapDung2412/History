"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

type TextScale = "small" | "normal" | "large";

const SCALE_ORDER: TextScale[] = ["small", "normal", "large"];
const STORAGE_SCALE = "di-san-lens:text-scale";
const STORAGE_CONTRAST = "di-san-lens:high-contrast";

export function AccessibilityToolbar() {
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false);
  return <ToolbarContent key={String(hydrated)} readSaved={hydrated} />;
}

function subscribeHydration() { return () => undefined; }

function ToolbarContent({ readSaved }: { readSaved: boolean }) {
  const [scale, setScale] = useState<TextScale>(() => {
    const savedScale = readSaved ? readPreference(STORAGE_SCALE) : null;
    return SCALE_ORDER.includes(savedScale as TextScale)
      ? (savedScale as TextScale)
      : "normal";
  });
  const [highContrast, setHighContrast] = useState(() => readSaved && readPreference(STORAGE_CONTRAST) === "true");

  useEffect(() => { applyPreferences(scale, highContrast); }, [scale, highContrast]);

  function updateScale(nextScale: TextScale) {
    setScale(nextScale);
    savePreference(STORAGE_SCALE, nextScale);
    applyPreferences(nextScale, highContrast);
  }

  function changeScale(offset: -1 | 1) {
    const index = Math.max(
      0,
      Math.min(SCALE_ORDER.length - 1, SCALE_ORDER.indexOf(scale) + offset),
    );
    updateScale(SCALE_ORDER[index]);
  }

  function toggleContrast() {
    const next = !highContrast;
    setHighContrast(next);
    savePreference(STORAGE_CONTRAST, String(next));
    applyPreferences(scale, next);
  }

  return (
    <div className="accessibility-toolbar" aria-label="Tùy chọn hiển thị">
      <span className="toolbar-label">Cỡ chữ</span>
      <button
        type="button"
        className="toolbar-button"
        onClick={() => changeScale(-1)}
        disabled={scale === "small"}
        aria-label="Giảm cỡ chữ"
      >
        A−
      </button>
      <button
        type="button"
        className="toolbar-button toolbar-button-large"
        onClick={() => changeScale(1)}
        disabled={scale === "large"}
        aria-label="Tăng cỡ chữ"
      >
        A+
      </button>
      <span className="toolbar-divider" aria-hidden="true" />
      <button
        type="button"
        className="contrast-button"
        onClick={toggleContrast}
        aria-pressed={highContrast}
      >
        <span className="contrast-swatch" aria-hidden="true" />
        Tương phản
      </button>
    </div>
  );
}

function applyPreferences(scale: TextScale, highContrast: boolean) {
  document.documentElement.dataset.textScale = scale;
  document.documentElement.dataset.contrast = highContrast ? "high" : "normal";
}

function readPreference(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function savePreference(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch {
    // Preferences still apply for this visit when browser storage is blocked.
  }
}
