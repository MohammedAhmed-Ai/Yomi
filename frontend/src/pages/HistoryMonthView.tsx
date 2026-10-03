import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { ApiError, getRange } from '../lib/api';
import { addDays, todayISO } from '../lib/dates';
import { useToday } from '../lib/useToday';
import { plural } from '../lib/text';
import type { StatsRange } from '../lib/types';

type Direction = 'forward' | 'back' | 'none';

interface LoadedMonth extends StatsRange {
  month: string;
}

interface FailedMonth {
  month: string;
  message: string;
}

const WEEKDAYS = ['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

function monthKey(date: string): string {
  return date.slice(0, 7);
}

function monthGridStart(month: string): string {
  const [year, monthNumber] = month.split('-').map(Number);
  const firstDay = `${month}-01`;
  const weekday = new Date(year, monthNumber - 1, 1).getDay();
  return addDays(firstDay, -((weekday + 1) % 7));
}

function monthTitle(month: string): string {
  const [year, monthNumber] = month.split('-').map(Number);
  return new Date(year, monthNumber - 1, 1).toLocaleDateString('en-GB', {
    month: 'long',
    year: 'numeric',
  });
}

function shiftMonth(month: string, amount: number): string {
  const [year, monthNumber] = month.split('-').map(Number);
  const shifted = new Date(year, monthNumber - 1 + amount, 1);
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, '0')}`;
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

export function HistoryMonthView(): ReactElement {
  const today = useToday();
  const currentMonth = monthKey(today);
  const [month, setMonth] = useState(() => monthKey(todayISO()));
  const [loaded, setLoaded] = useState<LoadedMonth | null>(null);
  const [failed, setFailed] = useState<FailedMonth | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [enterDirection, setEnterDirection] = useState<Direction>('none');
  const start = monthGridStart(month);
  const end = addDays(start, 41);

  useEffect(() => {
    let cancelled = false;

    const load = async (): Promise<void> => {
      try {
        const result = await getRange(start, end);
        if (cancelled) return;
        setLoaded({ ...result, month });
        setFailed(null);
      } catch (error: unknown) {
        if (cancelled) return;
        setFailed({ month, message: errorMessage(error) });
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [start, end, month, attempt]);

  const navigateMonth = (direction: 'forward' | 'back'): void => {
    setEnterDirection(direction);
    setMonth((current) => shiftMonth(current, direction === 'forward' ? 1 : -1));
  };

  const stale = loaded !== null && loaded.month !== month;
  const showError = failed?.month === month;
  const daysInMonth = loaded?.days.filter(
    (day) => monthKey(day.date) === month && day.date <= today && !day.is_empty,
  );
  const daysComplete = daysInMonth?.filter((day) => day.is_complete).length ?? 0;
  const totalScore =
    loaded?.days
      .filter((day) => monthKey(day.date) === month && day.date <= today)
      .reduce((sum, day) => sum + day.score, 0) ?? 0;
  const averageCompletion = daysInMonth?.length
    ? Math.round(
        daysInMonth.reduce((sum, day) => sum + day.completion_pct, 0) / daysInMonth.length,
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
    <section className="mx-auto w-full max-w-[720px] px-4 py-4 sm:py-6">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => navigateMonth('back')}
          aria-label="Previous month"
          className={`press flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-border bg-surface text-text hover:border-primary hover:text-primary ${focusRing}`}
        >
          <Arrow direction="back" />
        </button>
        <h2 className="m-0 text-center text-lg font-semibold sm:text-xl">{monthTitle(month)}</h2>
        <button
          type="button"
          onClick={() => navigateMonth('forward')}
          aria-label="Next month"
          className={`press flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-border bg-surface text-text hover:border-primary hover:text-primary ${focusRing}`}
        >
          <Arrow direction="forward" />
        </button>
      </div>

      <div className="mt-2 flex min-h-8 items-center justify-center">
        {month !== currentMonth && (
          <button
            type="button"
            onClick={() => {
              setEnterDirection(currentMonth > month ? 'forward' : 'back');
              setMonth(currentMonth);
            }}
            className={`press rounded-[12px] border border-border bg-surface px-3 py-1 text-sm text-text hover:border-primary hover:text-primary ${focusRing}`}
          >
            This month
          </button>
        )}
      </div>

      {!loaded && !showError && (
        <p className="py-12 text-center text-sm text-muted" role="status">
          Loading your month…
        </p>
      )}

      {showError && (
        <div className="surface mt-3 px-4 py-6 text-center" role="alert">
          <p className="m-0 text-sm text-muted">Could not load this month. {failed?.message}</p>
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
          className={`transition-opacity duration-200 ${stale ? 'pointer-events-none opacity-50' : 'opacity-100'}`}
          aria-busy={stale}
        >
          <div
            key={loaded.month}
            className={`surface mt-3 px-2 py-3 sm:px-4 sm:py-4 ${stale ? '' : slideClass}`}
          >
            <div className="grid grid-cols-7 gap-1 sm:gap-2">
              {WEEKDAYS.map((weekday) => (
                <div
                  key={weekday}
                  className="py-1 text-center text-[10px] font-medium uppercase text-muted sm:text-xs"
                >
                  {weekday}
                </div>
              ))}
              {loaded.days.map((day, index) => {
                const outsideMonth = monthKey(day.date) !== loaded.month;
                const future = day.date > today;
                const hasTasks = !day.is_empty && !future && !outsideMonth;
                const complete = day.is_complete && hasTasks;
                const percent = Math.max(0, Math.min(day.completion_pct, 100));
                const dateNumber = Number(day.date.slice(-2));
                const isToday = day.date === today;
                const [year, monthNumber, date] = day.date.split('-').map(Number);
                const spokenDate = new Date(year, monthNumber - 1, date).toLocaleDateString(
                  'en-GB',
                  { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' },
                );
                const cellColor = complete
                  ? 'bg-success text-white dark:text-background'
                  : hasTasks
                    ? 'bg-muted text-text'
                    : 'bg-background text-muted';
                const cellOpacity = complete ? 1 : hasTasks ? 0.2 + (percent / 100) * 0.5 : 0.45;

                return (
                  <a
                    key={day.date}
                    href={`#/${day.date}`}
                    aria-label={`${spokenDate}${hasTasks ? `, ${percent}% complete` : ', no tasks'}`}
                    className={`month-cell fade-in flex aspect-square min-w-0 items-center justify-center rounded-[10px] text-xs tabular-nums transition-shadow hover:shadow-sm sm:rounded-[12px] sm:text-sm ${focusRing} ${cellColor} ${
                      future || outsideMonth ? 'opacity-40' : ''
                    } ${isToday ? 'ring-2 ring-primary ring-offset-1 ring-offset-surface' : ''}`}
                    style={{
                      animationDelay: `${index * 18}ms`,
                      backgroundColor:
                        hasTasks && !complete
                          ? `color-mix(in srgb, var(--color-muted) ${Math.round(cellOpacity * 100)}%, var(--color-background))`
                          : undefined,
                    }}
                  >
                    {dateNumber}
                  </a>
                );
              })}
            </div>
          </div>

          {daysInMonth && daysInMonth.length > 0 ? (
            <div className="surface mt-3 grid grid-cols-1 gap-3 px-4 py-4 text-center sm:grid-cols-3 sm:gap-2">
              <p className="m-0 text-sm text-muted">
                <span className="font-semibold text-text">
                  {daysComplete} of {daysInMonth.length}
                </span>{' '}
                {plural(daysInMonth.length, 'day', 'days')} complete
              </p>
              <p className="m-0 text-sm text-muted">
                Total score <span className="font-semibold text-text">{totalScore} pts</span>
              </p>
              <p className="m-0 text-sm text-muted">
                Average completion{' '}
                <span className="font-semibold text-text">{averageCompletion}%</span>
              </p>
            </div>
          ) : (
            <p className="surface mt-3 px-4 py-5 text-center text-sm text-muted">
              No tasks this month yet. A little space can be a good thing.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
