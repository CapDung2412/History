"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

export type SpeechState =
  | "idle"
  | "preparing"
  | "speaking"
  | "paused"
  | "no_vietnamese_voice"
  | "unsupported"
  | "error";

interface SpeechCallbacks {
  onState: (state: SpeechState) => void;
  onBoundary: (characterIndex: number) => void;
}

export interface TextToSpeechService {
  isSupported(): boolean;
  speak(text: string, callbacks: SpeechCallbacks, limitMs?: number, rate?: number): void;
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
  private voiceWait: ReturnType<typeof setTimeout> | undefined;
  private voiceListener: (() => void) | undefined;

  isSupported(): boolean {
    return (
      typeof window !== "undefined" &&
      "speechSynthesis" in window &&
      "SpeechSynthesisUtterance" in window
    );
  }

  speak(text: string, callbacks: SpeechCallbacks, limitMs?: number, rate = 1): void {
    if (!this.isSupported()) {
      callbacks.onState("unsupported");
      return;
    }

    this.stop();
    const currentRun = this.runId;
    const voices = window.speechSynthesis.getVoices();
    const speakWithVoice = (vietnameseVoice: SpeechSynthesisVoice | null) => {
      if (this.runId !== currentRun) return;
      this.clearVoiceWait();
      const utterance = new SpeechSynthesisUtterance(text.normalize("NFC"));
      utterance.lang = "vi-VN";
      // Some mobile browsers expose no voice list but still select the correct
      // system voice from `lang`. Only leave `voice` unset in that exact case.
      if (vietnameseVoice) utterance.voice = vietnameseVoice;
      utterance.rate = Math.min(1.5, Math.max(0.75, rate));
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
    };

    const selected = selectVietnameseVoice(voices);
    if (selected) {
      speakWithVoice(selected);
      return;
    }
    if (voices.length > 0) {
      callbacks.onState("no_vietnamese_voice");
      return;
    }

    callbacks.onState("preparing");
    this.voiceListener = () => {
      const loaded = selectVietnameseVoice(window.speechSynthesis.getVoices());
      if (loaded) speakWithVoice(loaded);
    };
    window.speechSynthesis.addEventListener("voiceschanged", this.voiceListener);
    this.voiceWait = setTimeout(() => {
      if (this.runId !== currentRun) return;
      const availableVoices = window.speechSynthesis.getVoices();
      const loaded = selectVietnameseVoice(availableVoices);
      this.clearVoiceWait();
      if (loaded) speakWithVoice(loaded);
      else if (availableVoices.length === 0) speakWithVoice(null);
      else callbacks.onState("no_vietnamese_voice");
    }, 1_200);
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
    this.clearVoiceWait();
    this.onLimit = undefined;
    if (this.isSupported()) window.speechSynthesis.cancel();
  }

  private clearTimer(): void {
    if (this.timeout) clearTimeout(this.timeout);
    this.timeout = undefined;
  }

  private clearVoiceWait(): void {
    if (this.voiceWait) clearTimeout(this.voiceWait);
    this.voiceWait = undefined;
    if (this.voiceListener && this.isSupported()) {
      window.speechSynthesis.removeEventListener("voiceschanged", this.voiceListener);
    }
    this.voiceListener = undefined;
  }

  private startTimer(): void {
    if (!this.onLimit) return;
    this.timerStartedAt = Date.now();
    this.timeout = setTimeout(this.onLimit, this.remainingMs);
  }
}

export const textToSpeechService: TextToSpeechService =
  new BrowserTextToSpeechService();

export function selectVietnameseVoice(
  voices: readonly SpeechSynthesisVoice[],
): SpeechSynthesisVoice | undefined {
  const candidates = voices.filter((voice) =>
    voice.lang.replace("_", "-").toLowerCase().startsWith("vi"),
  );
  return (
    candidates.find(
      (voice) =>
        voice.lang.replace("_", "-").toLowerCase() === "vi-vn" &&
        voice.localService,
    ) ||
    candidates.find(
      (voice) => voice.lang.replace("_", "-").toLowerCase() === "vi-vn",
    ) ||
    candidates.find((voice) => voice.localService) ||
    candidates[0]
  );
}

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
  const [rate, setRate] = useState(1);
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
    textToSpeechService.speak(text, callbacks, 30_000, rate);
  }, [callbacks, rate, text]);

  const playFull = useCallback(() => {
    setCharacterIndex(0);
    textToSpeechService.speak(text, callbacks, undefined, rate);
  }, [callbacks, rate, text]);

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
    rate,
    setRate,
  };
}

function subscribeSupport() { return () => undefined; }
