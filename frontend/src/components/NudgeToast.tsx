import { useEffect, useRef, useState } from 'react';
import type { AnimationEvent, ReactElement } from 'react';

export interface NudgeMessage {
  title: string;
  detail: string;
  motivation?: string;
}

interface NudgeToastProps {
  message: NudgeMessage | null;
  onDismiss: () => void;
  persistent?: boolean;
  id?: string;
}

type NudgePhase = 'entering' | 'open' | 'exiting' | 'collapsing';

export function NudgeToast({
  message,
  onDismiss,
  persistent = false,
  id,
}: NudgeToastProps): ReactElement | null {
  const [phase, setPhase] = useState<NudgePhase>('entering');
  const [textChanging, setTextChanging] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const previousMessage = useRef(message);
  const phaseRef = useRef(phase);
  const remaining = useRef(4000);
  const paused = hovered || focused;

  const updatePhase = (nextPhase: NudgePhase): void => {
    phaseRef.current = nextPhase;
    setPhase(nextPhase);
  };

  useEffect(() => {
    if (message === previousMessage.current) return;

    const wasReplacingOpenMessage = previousMessage.current !== null && phaseRef.current === 'open';
    previousMessage.current = message;
    remaining.current = 4000;
    setTextChanging(false);

    if (!message || !wasReplacingOpenMessage) {
      updatePhase('entering');
      setHovered(false);
      setFocused(false);
      return;
    }

    setTextChanging(true);
    const timeout = window.setTimeout(() => setTextChanging(false), 180);
    return () => window.clearTimeout(timeout);
  }, [message]);

  useEffect(() => {
    if (!message || phase !== 'open' || persistent) return;
    if (paused) {
      remaining.current = 2000;
      return;
    }

    const startedAt = Date.now();
    const timeout = window.setTimeout(() => {
      updatePhase('exiting');
    }, remaining.current);

    return () => {
      window.clearTimeout(timeout);
      if (phaseRef.current === 'open') {
        remaining.current = Math.max(0, remaining.current - (Date.now() - startedAt));
      }
    };
  }, [message, paused, phase, persistent]);

  useEffect(() => {
    if (!message || phase === 'exiting' || phase === 'collapsing') return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        updatePhase('exiting');
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [message, phase]);

  const handleSlotAnimationEnd = (event: AnimationEvent<HTMLDivElement>): void => {
    if (event.target !== event.currentTarget || !message) return;

    if (event.animationName === 'nudge-toast-reduced-enter' && phase === 'entering') {
      updatePhase('open');
    } else if (
      event.animationName === 'nudge-toast-space-close' ||
      event.animationName === 'nudge-toast-reduced-exit'
    ) {
      onDismiss();
    }
  };

  const handleCardAnimationEnd = (event: AnimationEvent<HTMLDivElement>): void => {
    if (
      event.target === event.currentTarget &&
      event.animationName === 'nudge-toast-card-enter' &&
      phase === 'entering'
    ) {
      updatePhase('open');
    } else if (
      event.target === event.currentTarget &&
      event.animationName === 'nudge-toast-card-exit' &&
      phase === 'exiting'
    ) {
      updatePhase('collapsing');
    }
  };

  if (!message) return null;

  const dismissing = phase === 'exiting' || phase === 'collapsing';

  return (
    <div
      id={id}
      onAnimationEnd={handleSlotAnimationEnd}
      aria-hidden={dismissing}
      inert={dismissing}
      className={`nudge-toast-slot mt-3 grid nudge-toast-${phase}`}
    >
      <div
        role="status"
        aria-live="polite"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocusCapture={() => setFocused(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
        }}
        className="nudge-toast-content min-h-0 overflow-hidden"
      >
        <div
          onAnimationEnd={handleCardAnimationEnd}
          className="nudge-toast-card surface px-4 py-3 text-text"
        >
          <div className="flex items-start justify-between gap-3">
            <div className={`min-w-0 ${textChanging ? 'nudge-toast-copy-change' : ''}`}>
              <p className="m-0 text-sm font-semibold">{message.title}</p>
            </div>
            <button
              type="button"
              aria-label="Dismiss nudge"
              onClick={() => {
                updatePhase('exiting');
              }}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-background hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor">
                <path d="m4 4 8 8m0-8-8 8" strokeLinecap="round" strokeWidth="1.5" />
              </svg>
            </button>
          </div>
          <div className={textChanging ? 'nudge-toast-copy-change' : ''}>
            <p className="mt-1 mb-0 text-sm">{message.detail}</p>
            {message.motivation && (
              <p className="mt-1 mb-0 text-xs text-muted">{message.motivation}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
