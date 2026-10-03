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
}

export function NudgeToast({ message, onDismiss }: NudgeToastProps): ReactElement | null {
  const [dismissedMessage, setDismissedMessage] = useState<NudgeMessage | null>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const remaining = useRef(6000);
  const visible = message !== null && message !== dismissedMessage;
  const paused = hovered || focused;

  useEffect(() => {
    remaining.current = 6000;
  }, [message]);

  useEffect(() => {
    if (!message || !visible || paused) return;

    const startedAt = Date.now();
    const timeout = window.setTimeout(() => {
      setDismissedMessage(message);
    }, remaining.current);

    return () => {
      window.clearTimeout(timeout);
      remaining.current = Math.max(0, remaining.current - (Date.now() - startedAt));
    };
  }, [message, paused, visible]);

  useEffect(() => {
    if (!visible) return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        setDismissedMessage(message);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [message, visible]);

  const handleAnimationEnd = (event: AnimationEvent<HTMLDivElement>): void => {
    if (event.target === event.currentTarget && !visible && message) {
      onDismiss();
    }
  };

  if (!message) return null;

  return (
    <div
      onAnimationEnd={handleAnimationEnd}
      className={`nudge-toast-slot mt-3 grid ${visible ? 'nudge-toast-enter' : 'nudge-toast-exit'}`}
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
        <div className="surface px-4 py-3 text-text">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="m-0 text-sm font-semibold">{message.title}</p>
            </div>
            <button
              type="button"
              aria-label="Dismiss nudge"
              onClick={() => {
                setDismissedMessage(message);
              }}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-background hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor">
                <path d="m4 4 8 8m0-8-8 8" strokeLinecap="round" strokeWidth="1.5" />
              </svg>
            </button>
          </div>
          <p className="mt-1 mb-0 text-sm">{message.detail}</p>
          {message.motivation && (
            <p className="mt-1 mb-0 text-xs text-muted">{message.motivation}</p>
          )}
        </div>
      </div>
    </div>
  );
}
