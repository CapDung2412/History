"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { CloseIcon } from "@/components/icons";

export interface LightboxImage {
  url: string;
  alt: string;
  caption?: string | null;
}

interface ImageLightboxProps {
  image: LightboxImage | null;
  onClose: () => void;
}

const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function ImageLightbox({ image, onClose }: ImageLightboxProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    if (!image) return;
    const dialog = dialogRef.current;
    if (!dialog) return;

    returnFocusRef.current = document.activeElement as HTMLElement | null;
    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    setStatus("loading");

    if (!dialog.open) dialog.showModal();
    const focusFrame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());

    return () => {
      window.cancelAnimationFrame(focusFrame);
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousHtmlOverflow;
      returnFocusRef.current?.focus({ preventScroll: true });
      returnFocusRef.current = null;
    };
  }, [image]);

  if (!image) {
    return <dialog ref={dialogRef} className="image-lightbox" />;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    );
    if (focusable.length === 0) {
      event.preventDefault();
      event.currentTarget.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="image-lightbox"
      aria-modal="true"
      aria-labelledby="image-lightbox-title"
      aria-describedby={image.caption ? "image-lightbox-caption" : undefined}
      aria-busy={status === "loading"}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
    >
      <div className="image-lightbox-content">
        <div className="image-lightbox-header">
          <h2 id="image-lightbox-title">Xem ảnh hiện vật</h2>
          <button
            ref={closeButtonRef}
            type="button"
            className="icon-button image-lightbox-close"
            onClick={onClose}
            aria-label="Đóng ảnh phóng lớn"
          >
            <CloseIcon />
          </button>
        </div>

        <figure className={`image-lightbox-figure is-${status}`}>
          {status === "loading" && (
            <p className="image-lightbox-status" role="status">
              Đang tải ảnh đầy đủ…
            </p>
          )}
          {status === "error" ? (
            <p className="image-lightbox-error" role="alert">
              Chưa thể tải ảnh này. Em hãy đóng cửa sổ và thử lại.
            </p>
          ) : (
            // The original is requested only after the lightbox opens.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={image.url}
              alt={image.alt}
              decoding="async"
              onLoad={() => setStatus("ready")}
              onError={() => setStatus("error")}
            />
          )}
          {image.caption && (
            <figcaption id="image-lightbox-caption">{image.caption}</figcaption>
          )}
        </figure>
      </div>
    </dialog>
  );
}
