import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { getRange, ApiError } from '../lib/api';
import { addDays, todayISO } from '../lib/dates';
import { useToday } from '../lib/useToday';
import type { StatsRange } from '../lib/types';

type Direction = 'forward' | 'back' | 'none';

interface LoadedWeek extends StatsRange {
  start: string;
}

interface FailedWeek {
  start: string;
  message: string;
}

function startOfWeek(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  const weekday = new Date(year, month - 1, day).getDay();
  return addDays(date, -((weekday + 1) % 7));
}

function formatWeek(start: string, end: string): string {
  const [startYear, startMonth, startDay] = start.split('-').map(Number);
  const [endYear, endMonth, endDay] = end.split('-').map(Number);
  const first = new Date(startYear, startMonth - 1, startDay);
  const last = new Date(endYear, endMonth - 1, endDay);
  const options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' };
  const firstLabel = first.toLocaleDateString('en-GB', options);
  const lastLabel = last.toLocaleDateString(
    'en-GB',
    startYear === endYear && startMonth === endMonth ? { day: 'numeric' } : options,
  );
  return `${firstLabel} – ${lastLabel}`;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong. Please try again.';
}

function Arrow({ direction }: { direction: Direction }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" strokeWidth="1.5" aria-hidden="true">
      {direction === 'back' ? (
        <path d="M10 3L5 8l5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M6 3l5 5-5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

export function HistoryPage(): ReactElement {
  const today = useToday();
  const currentWeekStart = startOfWeek(today);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(todayISO()));
  const [loaded, setLoaded] = useState<LoadedWeek | null>(null);
  const [failed, setFailed] = useState<FailedWeek | null>(null);
  const [loadingStart, setLoadingStart] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const directionRef = useRef<Direction>('none');
  const [enterDirection, setEnterDirection] = useState<Direction>('none');

  useEffect(() => {
    let cancelled = false;
    const end = addDays(weekStart, 6);
    setLoadingStart(weekStart);

    const load = async (): Promise<void> => {
      try {
        const result = await getRange(weekStart, end);
        if (cancelled) return;
        setLoaded({ ...result, start: weekStart });
        setFailed(null);
        setEnterDirection(directionRef.current);
        directionRef.current = 'none';
      } catch (error: unknown) {
        if (cancelled) return;
        setFailed({ start: weekStart, message: errorMessage(error) });
      } finally {
        if (!cancelled) setLoadingStart(null);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [weekStart, attempt]);

  const navigateWeek = (direction: 'forward' | 'back'): void => {
    directionRef.current = direction;
    setWeekStart((current) => addDays(current, direction === 'forward' ? 7 : -7));
  };

  const goToDay = (date: string): void => {
    window.location.hash = `#/${date}`;
  };

  const isStale = loaded !== null && loaded.start !== weekStart;
  const isLoading = loadingStart === weekStart;
  const showError = failed?.start === weekStart;
  const visibleDays = loaded?.days ?? [];
  const completedDays = visibleDays.filter((day) => day.date <= today && day.is_complete).length;
  const daysWithTasks = visibleDays.filter((day) => day.date <= today && !day.is_empty);
  const totalScore = visibleDays
    .filter((day) => day.date <= today)
    .reduce((sum, day) => sum + day.score, 0);
  const averageCompletion = daysWithTasks.length
    ? Math.round(
        daysWithTasks.reduce((sum, day) => sum + day.completion_pct, 0) / daysWithTasks.length,
      )
    : 0;
  const focusRing =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background';
  const slideClass =
    enterDirection === 'forward'
      ? 'slide-forward'
      : enterDirection === 'back'
        ? 'slide-back'
        : 'fade-in';

  return (
    <section className="mx-auto w-full max-w-[720px] px-4 py-6">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigateWeek('back')}
          aria-label="Previous week"
          className={`press flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-border bg-surface text-text hover:border-primary hover:text-primary ${focusRing}`}
        >
          <Arrow direction="back" />
        </button>
        <h2 className="m-0 text-center text-lg font-semibold sm:text-xl">
          {formatWeek(weekStart, addDays(weekStart, 6))}
        </h2>
        <button
          type="button"
          onClick={() => navigateWeek('forward')}
          aria-label="Next week"
          className={`press flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-border bg-surface text-text hover:border-primary hover:text-primary ${focusRing}`}
        >
          <Arrow direction="forward" />
        </button>
      </div>

      <div className="mt-2 flex min-h-8 items-center justify-center">
        {weekStart !== currentWeekStart && (
          <button
            type="button"
            onClick={() => {
              directionRef.current = currentWeekStart > weekStart ? 'forward' : 'back';
              setWeekStart(currentWeekStart);
            }}
            className={`press rounded-[12px] border border-border bg-surface px-3 py-1 text-sm text-text hover:border-primary hover:text-primary ${focusRing}`}
          >
            This week
          </button>
        )}
      </div>

      {!loaded && !showError && (
        <p className="py-12 text-center text-sm text-muted" role="status">
          Loading your week…
        </p>
      )}

      {showError && (
        <div className="surface mt-3 px-4 py-6 text-center" role="alert">
          <p className="m-0 text-sm text-muted">
            Could not load this week. {failed?.message}
          </p>
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className={`press mt-3 rounded-[12px] border border-border bg-surface px-3 py-1.5 text-sm text-text ${focusRing}`}
          >
            Try again
          </button>
        </div>
      )}

      {loaded && (
        <div
          className={`transition-opacity duration-200 ${
            isStale || isLoading ? 'pointer-events-none opacity-50' : 'opacity-100'
          }`}
          aria-busy={isStale || isLoading}
        >
          <div
            key={loaded.start}
            className={`surface mt-3 px-2 py-5 sm:px-5 ${isStale || isLoading ? '' : slideClass}`}
          >
            <div className="grid grid-cols-7 gap-1 sm:gap-3" aria-label="Week completion">
              {loaded.days.map((day, index) => {
                const future = day.date > today;
                const hasTasks = !day.is_empty && !future;
                const complete = day.is_complete && hasTasks;
                const percent = hasTasks ? Math.max(0, Math.min(day.completion_pct, 100)) : 0;
                const [year, month, dateNumber] = day.date.split('-').map(Number);
                const date = new Date(year, month - 1, dateNumber);
                const weekday = date.toLocaleDateString('en-GB', { weekday: 'short' }).slice(0, 1);
                const isToday = day.date === today;

                return (
                  <button
                    key={day.date}
                    type="button"
                    onClick={() => goToDay(day.date)}
                    aria-label={`${date.toLocaleDateString('en-GB', {
                      weekday: 'long',
                      day: 'numeric',
                      month: 'long',
                    })}${hasTasks ? `, ${percent}% complete, ${day.score} points` : ', no tasks'}`}
                    className={`day-column flex min-w-0 flex-col items-center rounded-[12px] px-1 py-2 transition-colors hover:bg-background ${focusRing} ${
                      future ? 'opacity-40' : ''
                    } ${isToday ? 'bg-background ring-1 ring-primary' : ''}`}
                  >
                    <span className="text-xs font-medium uppercase text-muted">{weekday}</span>
                    <span className={`mt-1 text-sm tabular-nums ${isToday ? 'font-semibold text-primary' : 'text-text'}`}>
                      {dateNumber}
                    </span>
                    <span
                      className="mt-3 flex h-28 w-5 items-end overflow-hidden rounded-full bg-background sm:w-7"
                      aria-hidden="true"
                    >
                      <span
                        className={`week-bar stagger block w-full rounded-full ${
                          complete ? 'bg-success' : hasTasks ? 'bg-muted' : 'bg-border'
                        }`}
                        style={{
                          height: hasTasks ? `${Math.max(percent, 3)}%` : '2px',
                          animationDelay: `${index * 45}ms`,
                          opacity: hasTasks ? 1 : 0.8,
                        }}
                      />
                    </span>
                    <span className={`mt-2 text-xs tabular-nums ${complete ? 'font-semibold text-success' : 'text-muted'}`}>
                      {hasTasks ? day.score : '—'}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {daysWithTasks.length > 0 ? (
            <div className="surface mt-3 grid grid-cols-1 gap-3 px-4 py-4 text-center sm:grid-cols-3 sm:gap-2">
              <p className="m-0 text-sm text-muted">
                <span className="font-semibold text-text">
                  {completedDays} of {daysWithTasks.length}
                </span>{' '}
                days complete
              </p>
              <p className="m-0 text-sm text-muted">
                Total score{' '}
                <span className="font-semibold text-text">{totalScore} pts</span>
              </p>
              <p className="m-0 text-sm text-muted">
                Average completion{' '}
                <span className="font-semibold text-text">{averageCompletion}%</span>
              </p>
            </div>
          ) : (
            <p className="surface mt-3 px-4 py-5 text-center text-sm text-muted">
              No tasks this week yet. A little space can be a good thing.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
