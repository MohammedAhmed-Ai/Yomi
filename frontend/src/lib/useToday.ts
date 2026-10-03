import { useEffect, useState } from 'react';
import { todayISO } from './dates';

/** One second past midnight, so the clock has definitely flipped over. */
const MIDNIGHT_GRACE_MS = 1000;

/** Milliseconds from `now` to one second past the next local midnight. */
function msUntilNextMidnight(now: Date): number {
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0, 0);
  return next.getTime() - now.getTime() + MIDNIGHT_GRACE_MS;
}

/**
 * Today's local date as "YYYY-MM-DD", kept live across midnight.
 *
 * A timer alone is not enough: browsers throttle timers in background tabs and
 * may pause them entirely while a device sleeps, so the date is also re-checked
 * whenever the tab becomes visible again or the window regains focus.
 */
export function useToday(): string {
  const [today, setToday] = useState<string>(todayISO);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    const check = (): void => {
      const next = todayISO();
      setToday((current) => (next === current ? current : next));
      schedule();
    };

    const schedule = (): void => {
      clearTimeout(timer);
      timer = setTimeout(check, msUntilNextMidnight(new Date()));
    };

    const onVisibility = (): void => {
      if (document.visibilityState === 'visible') check();
    };

    schedule();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', check);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', check);
    };
  }, []);

  return today;
}
