import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import type { DayScore } from '../lib/types';

interface ScoreCardProps {
  score: DayScore;
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Counts the score up to its final value on mount, so the day "arrives" rather
 * than snapping into place. Respects prefers-reduced-motion by showing the
 * final number immediately.
 */
function useCountUp(target: number): number {
  const [value, setValue] = useState(0);
  const frame = useRef<number | undefined>(undefined);

  useEffect(() => {
    // Reduced motion renders the final value directly, so nothing to animate.
    if (prefersReducedMotion()) return;

    const duration = 600;
    const started = performance.now();

    const tick = (now: number): void => {
      const progress = Math.min((now - started) / duration, 1);
      setValue(Math.round(target * easeOutCubic(progress)));
      if (progress < 1) {
        frame.current = requestAnimationFrame(tick);
      }
    };

    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    };
  }, [target]);

  return prefersReducedMotion() ? target : value;
}

export function ScoreCard({ score }: ScoreCardProps): ReactElement {
  const counted = useCountUp(score.score);

  if (score.is_empty) {
    return (
      <section className="surface fade-in px-5 py-6 text-center" aria-label="Daily score">
        <p className="m-0 text-base text-muted">Nothing planned for today yet.</p>
        <p className="m-0 mt-1 text-sm text-muted">A clear day is still a day.</p>
      </section>
    );
  }

  const percent =
    score.tasks_total > 0 ? Math.round((score.tasks_done / score.tasks_total) * 100) : 0;
  const complete = score.is_complete;

  return (
    <section
      className={`surface fade-in ${complete ? 'pulse-once' : ''} px-5 py-5`}
      aria-label="Daily score"
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="m-0">
          <span
            className={`text-3xl font-semibold ${complete ? 'text-success' : 'text-text'}`}
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {counted}
          </span>
          <span className="ml-1 text-sm text-muted">pts</span>
        </p>
        <p className="m-0 text-sm text-muted">
          <span className={complete ? 'text-success' : undefined}>{percent}%</span>
          {' · '}
          {score.tasks_done} of {score.tasks_total} tasks done
        </p>
      </div>

      <div
        className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-border"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Tasks completed"
      >
        <div
          className={`h-full rounded-full ${complete ? 'bg-success' : 'bg-primary'}`}
          style={{
            width: `${percent}%`,
            transitionProperty: 'width',
            transitionDuration: 'var(--dur)',
            transitionTimingFunction: 'ease-out',
          }}
        />
      </div>
    </section>
  );
}