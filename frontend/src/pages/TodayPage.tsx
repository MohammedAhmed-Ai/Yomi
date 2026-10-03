import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { carryOver, getDay, getScore, ApiError } from '../lib/api';
import { todayISO } from '../lib/dates';
import type { Day, DayScore } from '../lib/types';
import { ScoreCard } from '../components/ScoreCard';
import { TaskItem } from '../components/TaskItem';

type LoadState = 'loading' | 'ready' | 'error';

interface TodayData {
  day: Day;
  score: DayScore;
  /** Non-fatal notice, e.g. carry-over did not run. */
  warning: string;
}

/**
 * Loads today. Carry-over runs first, but failing it must not hide the day, so
 * its error becomes a warning and the day is still fetched.
 */
async function fetchToday(date: string): Promise<TodayData> {
  let warning = '';

  try {
    await carryOver();
  } catch (error: unknown) {
    warning =
      error instanceof ApiError ? `Carry-over skipped: ${error.message}` : 'Carry-over skipped';
  }

  const [day, score] = await Promise.all([getDay(date), getScore(date)]);
  return { day, score, warning };
}

/** Top-level tasks of the day, each carrying its own subtasks. */
function rootTasks(day: Day): Day['tasks'] {
  return day.tasks.filter((task) => task.parent_task_id === null);
}

/** "Saturday, 3 October" — the long-form header, without the year. */
function formatHeading(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

export function TodayPage(): ReactElement {
  const [state, setState] = useState<LoadState>('loading');
  const [data, setData] = useState<TodayData | null>(null);
  const [message, setMessage] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const run = async (): Promise<void> => {
      try {
        const result = await fetchToday(todayISO());
        if (cancelled) return;
        setData(result);
        setMessage(result.warning);
        setState('ready');
      } catch (error: unknown) {
        if (cancelled) return;
        setMessage(error instanceof ApiError ? error.message : 'Something went wrong');
        setState('error');
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = (): void => {
    setState('loading');
    setMessage('');
    setAttempt((value) => value + 1);
  };

  if (state === 'loading') {
    return (
      <div className="mx-auto w-full max-w-[640px] px-4 py-6">
        <div className="h-6 w-48 animate-pulse rounded bg-border" />
        <div className="surface mt-3 h-24 animate-pulse" />
        <div className="surface mt-4 h-40 animate-pulse" />
        <p className="mt-4 text-center text-sm text-muted">Loading today…</p>
      </div>
    );
  }

  if (state === 'error' || !data) {
    return (
      <div className="mx-auto w-full max-w-[640px] px-4 py-10 text-center">
        <h2 className="m-0 text-lg font-semibold">Could not load today</h2>
        <p className="mt-1 text-sm text-muted">{message}</p>
        <button
          type="button"
          onClick={retry}
          className="press mt-4 rounded-[12px] border border-border bg-surface px-3 py-1.5 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          Try again
        </button>
      </div>
    );
  }

  const tasks = rootTasks(data.day);

  return (
    <div className="mx-auto w-full max-w-[640px] px-4 py-6">
      <h2 className="fade-in m-0 text-xl font-semibold">{formatHeading(data.day.date)}</h2>

      <div className="mt-3">
        <ScoreCard score={data.score} />
      </div>

      {data.warning && (
        <p className="mt-2 text-xs text-muted" role="status">
          {data.warning}
        </p>
      )}

      <div className="surface mt-4 px-4 py-1">
        {tasks.length === 0 ? (
          <p className="fade-in my-4 text-center text-sm text-muted">No tasks for today yet.</p>
        ) : (
          <ul className="m-0 list-none p-0">
            {tasks.map((task, index) => (
              <li key={task.id} className="border-b border-border last:border-b-0">
                <TaskItem task={task} index={index} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}