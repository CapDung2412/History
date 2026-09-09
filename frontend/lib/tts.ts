"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

export type SpeechState =
  | "idle"
  | "speaking"
  | "paused"
  | "unsupported"
  | "error";

interface SpeechCallbacks {
  onState: (state: SpeechState) => void;
  onBoundary: (characterIndex: number) => void;
}

export interface TextToSpeechService {
  isSupported(): boolean;
  speak(text: string, callbacks: SpeechCallbacks, limitMs?: number): void;
  pause(): void;
  resume(): void;
  stop(): void;
}

class BrowserTextToSpeechService implements TextToSpeechService {
  private timeout: ReturnType<typeof setTimeout> | undefined;
  private runId = 0;
  private remainingMs = 0;
  private timerStartedAt = 0;
  private onLimit: (() => void) | undefined;

  isSupported(): boolean {
    return (
      typeof window !== "undefined" &&
      "speechSynthesis" in window &&
      "SpeechSynthesisUtterance" in window
    );
  }

  speak(text: string, callbacks: SpeechCallbacks, limitMs?: number): void {
    if (!this.isSupported()) {
      callbacks.onState("unsupported");
      return;
    }

    this.stop();
    const currentRun = this.runId;
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    const vietnameseVoice = voices.find((voice) =>
      voice.lang.toLowerCase().startsWith("vi"),
    );

    utterance.lang = vietnameseVoice?.lang || "vi-VN";
    if (vietnameseVoice) utterance.voice = vietnameseVoice;
    utterance.rate = 0.92;
    utterance.pitch = 1;

    utterance.onstart = () => {
      if (this.runId === currentRun) callbacks.onState("speaking");
    };
    utterance.onboundary = (event) => {
      if (this.runId === currentRun) callbacks.onBoundary(event.charIndex);
    };
    utterance.onend = () => {
      if (this.runId === currentRun) {
        this.clearTimer();
        this.onLimit = undefined;
        callbacks.onState("idle");
      }
    };
    utterance.onerror = (event) => {
      if (event.error === "canceled" || event.error === "interrupted") return;
      if (this.runId === currentRun) {
        this.clearTimer();
        this.onLimit = undefined;
        callbacks.onState("error");
      }
    };

    window.speechSynthesis.speak(utterance);
    callbacks.onState("speaking");
    if (limitMs) {
      this.remainingMs = limitMs;
      this.onLimit = () => {
        if (this.runId === currentRun) {
          this.stop();
          callbacks.onState("idle");
        }
      };
      this.startTimer();
    }
  }

  pause(): void {
    if (this.isSupported() && window.speechSynthesis.speaking) {
      window.speechSynthesis.pause();
      if (this.timeout) {
        this.remainingMs = Math.max(0, this.remainingMs - (Date.now() - this.timerStartedAt));
        this.clearTimer();
      }
    }
  }

  resume(): void {
    if (this.isSupported() && window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      if (this.onLimit && !this.timeout) this.startTimer();
    }
  }

  stop(): void {
    this.runId += 1;
    this.clearTimer();
    this.onLimit = undefined;
    if (this.isSupported()) window.speechSynthesis.cancel();
  }

  private clearTimer(): void {
    if (this.timeout) clearTimeout(this.timeout);
    this.timeout = undefined;
  }

  private startTimer(): void {
    if (!this.onLimit) return;
    this.timerStartedAt = Date.now();
    this.timeout = setTimeout(this.onLimit, this.remainingMs);
  }
}

export const textToSpeechService: TextToSpeechService =
  new BrowserTextToSpeechService();

function currentSentence(text: string, index: number): string {
  const before = text.lastIndexOf(".", Math.max(0, index - 1));
  const after = text.indexOf(".", index);
  const start = before < 0 ? 0 : before + 1;
  const end = after < 0 ? text.length : after + 1;
  return text.slice(start, end).trim() || text.slice(0, 180);
}

export function useTextToSpeech(text: string, contentId: string) {
  const supported = useSyncExternalStore(subscribeSupport, () => textToSpeechService.isSupported(), () => false);
  const [state, setState] = useState<SpeechState>("idle");
  const [characterIndex, setCharacterIndex] = useState(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    textToSpeechService.stop();
    return () => {
      mounted.current = false;
      textToSpeechService.stop();
    };
  }, [contentId, text]);

  const callbacks = useMemo<SpeechCallbacks>(
    () => ({
      onState: (nextState) => mounted.current && setState(nextState),
      onBoundary: (index) => mounted.current && setCharacterIndex(index),
    }),
    [],
  );

  const playShort = useCallback(() => {
    setCharacterIndex(0);
    textToSpeechService.speak(text, callbacks, 30_000);
  }, [callbacks, text]);

  const playFull = useCallback(() => {
    setCharacterIndex(0);
    textToSpeechService.speak(text, callbacks);
  }, [callbacks, text]);

  const pause = useCallback(() => {
    textToSpeechService.pause();
    setState("paused");
  }, []);

  const resume = useCallback(() => {
    textToSpeechService.resume();
    setState("speaking");
  }, []);

  const stop = useCallback(() => {
    textToSpeechService.stop();
    setCharacterIndex(0);
    setState(textToSpeechService.isSupported() ? "idle" : "unsupported");
  }, []);

  return {
    state: supported ? state : "unsupported" as SpeechState,
    subtitle: currentSentence(text, characterIndex),
    playShort,
    playFull,
    pause,
    resume,
    stop,
  };
}

function subscribeSupport() { return () => undefined; }
