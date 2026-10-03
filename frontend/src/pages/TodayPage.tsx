import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactElement } from 'react';
import {
  carryOver,
  getDay,
  getScore,
  createTask,
  updateTask,
  completeTask,
  uncompleteTask,
  deleteTask,
  ApiError,
} from '../lib/api';
import { addDays, todayISO } from '../lib/dates';
import { useToday } from '../lib/useToday';
import type { Day, DayScore, Task } from '../lib/types';
import { ScoreCard } from '../components/ScoreCard';
import { TaskItem } from '../components/TaskItem';

type LoadState = 'loading' | 'ready' | 'error';
type Direction = 'forward' | 'back' | 'none';

interface LoadedDay {
  date: string;
  day: Day;
  score: DayScore;
  warning: string;
}

interface FailedDay {
  date: string;
  message: string;
}

const DEFAULT_POINTS = 10;

/** "Saturday, 3 October" — the long-form header, without the year. */
function formatHeading(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

/** True only for a real calendar date, so 2026-02-31 cannot slip through. */
function isRealDate(iso: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
  const [year, month, day] = iso.split('-').map(Number);
  const parsed = new Date(year, month - 1, day);
  return (
    parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
  );
}

/** "#/YYYY-MM-DD" drives the page; anything unusable falls back to today. */
function readHashDate(): string {
  const raw = window.location.hash.replace(/^#\/?/, '').trim();
  return isRealDate(raw) ? raw : todayISO();
}

/**
 * Loads one day. Carry-over is a today-only action: opening a past day must
 * never rewrite it, and a future day has nothing to carry. `today` is passed in
 * rather than read from the clock so a rollover reload carries into the new day.
 */
async function fetchDay(date: string, today: string): Promise<LoadedDay> {
  let warning = '';

  if (date === today) {
    try {
      await carryOver();
    } catch (error: unknown) {
      warning =
        error instanceof ApiError
          ? `Carry-over skipped: ${error.message}`
          : 'Carry-over skipped';
    }
  }

  const [day, score] = await Promise.all([getDay(date), getScore(date)]);
  return { date, day, score, warning };
}

/** Top-level tasks of the day, each carrying its own subtasks. */
function rootTasks(day: Day): Day['tasks'] {
  return day.tasks.filter((task) => task.parent_task_id === null);
}

/** Replaces a task wherever it appears in the tree, including as a subtask. */
function patchTask(tasks: Day['tasks'], id: number, update: (task: Task) => Task): Day['tasks'] {
  return tasks.map((task) => {
    if (task.id === id) return update(task);
    if (task.subtasks.length === 0) return task;
    return { ...task, subtasks: patchTask(task.subtasks, id, update) };
  });
}

/** Drops a task from the tree wherever it appears. */
function removeTask(tasks: Day['tasks'], id: number): Day['tasks'] {
  return tasks
    .filter((task) => task.id !== id)
    .map((task) =>
      task.subtasks.length === 0 ? task : { ...task, subtasks: removeTask(task.subtasks, id) },
    );
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function TodayPage(): ReactElement {
  // Live local date: it rolls over at midnight even if the tab stays open.
  const today = useToday();
  const [date, setDate] = useState<string>(readHashDate);
  const [direction, setDirection] = useState<Direction>('none');
  const [loaded, setLoaded] = useState<LoadedDay | null>(null);
  const [failed, setFailed] = useState<FailedDay | null>(null);
  const [attempt, setAttempt] = useState(0);

  const [title, setTitle] = useState('');
  const [points, setPoints] = useState(DEFAULT_POINTS);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState('');
  const [justAdded, setJustAdded] = useState<number | null>(null);
  const [removing, setRemoving] = useState<Record<number, boolean>>({});

  // Compared against the hash so browser back/forward slides the right way too.
  const dateRef = useRef(date);
  // The previous "today", so a rollover can tell which day was on screen.
  const previousTodayRef = useRef(today);

  useEffect(() => {
    const onHashChange = (): void => {
      const next = readHashDate();
      const previous = dateRef.current;
      setDirection(next > previous ? 'forward' : next < previous ? 'back' : 'none');
      dateRef.current = next;
      setDate(next);
    };

    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const run = async (): Promise<void> => {
      try {
        const result = await fetchDay(date, today);
        if (cancelled) return;
        setLoaded(result);
        setFailed(null);
        // A day change starts from a clean slate.
        setTitle('');
        setAddError('');
        setActionError('');
        setJustAdded(null);
        setRemoving({});
      } catch (error: unknown) {
        if (cancelled) return;
        setFailed({ date, message: errorMessage(error, 'Something went wrong') });
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [date, today, attempt]);

  const goTo = useCallback((next: string) => {
    const hash = `#/${next}`;
    if (window.location.hash === hash) return;
    window.location.hash = hash;
  }, []);

  const retry = (): void => setAttempt((value) => value + 1);

  // Midnight rollover: yesterday's unfinished work carries into the new day, and
  // whichever day is on screen must re-evaluate its past/future rules.
  useEffect(() => {
    const previous = previousTodayRef.current;
    if (previous === today) return;
    previousTodayRef.current = today;

    if (dateRef.current === previous) {
      // Was looking at the old today: follow it across the boundary.
      goTo(today);
      return;
    }

    if (dateRef.current !== today) {
      // New today is not on screen, but its carry-over still needs to happen.
      void carryOver().catch(() => undefined);
    }

    setAttempt((value) => value + 1);
  }, [today, goTo]);

  const handleAdd = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || adding) return;

    setAdding(true);
    setAddError('');

    try {
      const created = await createTask({ title: trimmed, points, planned_date: date });
      setTitle('');
      const [freshDay, freshScore] = await Promise.all([getDay(date), getScore(date)]);
      setLoaded((current) =>
        current ? { ...current, date, day: freshDay, score: freshScore } : current,
      );
      setJustAdded(created.id);
    } catch (error: unknown) {
      setAddError(errorMessage(error, 'Could not add that task.'));
    } finally {
      setAdding(false);
    }
  };

  const handleToggle = async (task: Task): Promise<void> => {
    if (busyId !== null || task.status === 'missed') return;

    const wasDone = task.status === 'done';
    setBusyId(task.id);
    setActionError('');

    // Optimistic: show the new state immediately, keep the server's task object
    // so a failure can be undone exactly.
    setLoaded((current) =>
      current
        ? {
            ...current,
            day: {
              ...current.day,
              tasks: patchTask(current.day.tasks, task.id, (t) => ({
                ...t,
                status: wasDone ? 'pending' : 'done',
              })),
            },
          }
        : current,
    );

    try {
      const updated = wasDone ? await uncompleteTask(task.id) : await completeTask(task.id);
      const freshScore = await getScore(date);
      setLoaded((current) =>
        current
          ? {
              ...current,
              day: {
                ...current.day,
                tasks: patchTask(current.day.tasks, task.id, () => updated),
              },
              score: freshScore,
            }
          : current,
      );
    } catch (error: unknown) {
      setLoaded((current) =>
        current
          ? {
              ...current,
              day: {
                ...current.day,
                tasks: patchTask(current.day.tasks, task.id, () => task),
              },
            }
          : current,
      );
      setActionError(errorMessage(error, 'Could not update that task.'));
    } finally {
      setBusyId(null);
    }
  };

  const handleSave = async (task: Task, edit: { title: string; points: number }): Promise<void> => {
    setActionError('');
    try {
      const updated = await updateTask(task.id, { title: edit.title, points: edit.points });
      const freshScore = await getScore(date);
      setLoaded((current) =>
        current
          ? {
              ...current,
              day: {
                ...current.day,
                tasks: patchTask(current.day.tasks, task.id, () => updated),
              },
              score: freshScore,
            }
          : current,
      );
    } catch (error: unknown) {
      // Re-thrown so the row stays in edit mode with the message attached.
      throw new Error(errorMessage(error, 'Could not save that task.'));
    }
  };

  /** Marks the row as leaving; TaskItem calls handleDelete once it has collapsed. */
  const handleDeleteRequest = (task: Task): void => {
    if (removing[task.id]) return;
    setActionError('');
    setRemoving((current) => ({ ...current, [task.id]: true }));
  };

  const clearRemoving = (id: number): void => {
    setRemoving((current) => {
      if (!current[id]) return current;
      const next = { ...current };
      delete next[id];
      return next;
    });
  };

  const handleDelete = async (task: Task): Promise<void> => {
    setBusyId(task.id);
    try {
      await deleteTask(task.id);
      const freshScore = await getScore(date);
      setLoaded((current) =>
        current
          ? {
              ...current,
              day: { ...current.day, tasks: removeTask(current.day.tasks, task.id) },
              score: freshScore,
            }
          : current,
      );
    } catch (error: unknown) {
      // Bring the row back and explain why it stayed.
      setActionError(errorMessage(error, 'Could not delete that task.'));
    } finally {
      clearRemoving(task.id);
      setBusyId(null);
    }
  };

  const isToday = date === today;
  const isPast = date < today;
  const isFuture = date > today;

  // A past day is a record: nothing about it can change.
  const readOnly = isPast;
  const canComplete = isToday;

  const focusRing =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background';

  const navButton =
    'press flex h-8 w-8 items-center justify-center rounded-[12px] border border-border bg-surface text-text ' +
    focusRing;

  // Derived from the loaded date, so switching days shows the skeleton without
  // needing a synchronous setState inside the effect.
  const fresh = loaded !== null && loaded.date === date;
  const state: LoadState = fresh ? 'ready' : failed !== null && failed.date === date ? 'error' : 'loading';

  const day = fresh ? loaded.day : null;
  const score = fresh ? loaded.score : null;
  const tasks = day ? rootTasks(day) : [];
  const canAdd = title.trim().length > 0 && !adding;

  const slideClass =
    direction === 'forward' ? 'slide-forward' : direction === 'back' ? 'slide-back' : 'fade-in';

  return (
    <div className="mx-auto w-full max-w-[640px] px-4 py-6">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => goTo(addDays(date, -1))}
          aria-label="Previous day"
          className={navButton}
        >
          <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" strokeWidth="1.5">
            <path d="M10 3L5 8l5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        <h2 key={date} className="fade-in m-0 text-center text-xl font-semibold">
          {formatHeading(date)}
        </h2>

        <button
          type="button"
          onClick={() => goTo(addDays(date, 1))}
          aria-label="Next day"
          className={navButton}
        >
          <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" strokeWidth="1.5">
            <path d="M6 3l5 5-5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div className="mt-2 flex min-h-[26px] items-center justify-between gap-2">
        <span className="text-xs text-muted">
          {isPast ? 'Past day' : isFuture ? 'Planning ahead' : ' '}
        </span>
        {!isToday && (
          <button
            type="button"
            onClick={() => goTo(today)}
            className={`press rounded-[12px] border border-border bg-surface px-2 py-0.5 text-xs text-text ${focusRing}`}
          >
            Today
          </button>
        )}
      </div>

      {state === 'loading' && (
        <div>
          <div className="surface mt-3 h-24 animate-pulse" />
          <div className="surface mt-3 h-40 animate-pulse" />
          <p className="mt-4 text-center text-sm text-muted">Loading…</p>
        </div>
      )}

      {state === 'error' && (
        <div className="py-10 text-center">
          <h3 className="m-0 text-lg font-semibold">Could not load this day</h3>
          <p className="mt-1 text-sm text-muted">{failed?.message}</p>
          <button
            type="button"
            onClick={retry}
            className={`press mt-4 rounded-[12px] border border-border bg-surface px-3 py-1.5 text-sm text-text ${focusRing}`}
          >
            Try again
          </button>
        </div>
      )}

      {state === 'ready' && day !== null && score !== null && (
        <div key={date} className={slideClass}>
          <div className="mt-3">
            <ScoreCard score={score} />
          </div>

          {loaded?.warning && (
            <p className="mt-2 text-xs text-muted" role="status">
              {loaded.warning}
            </p>
          )}

          {readOnly && (
            <p className="surface mt-3 px-4 py-3 text-xs text-muted">
              This day is closed. Its tasks stay as a record of what happened.
            </p>
          )}

          {!readOnly && (
            <div className="surface mt-3 px-4 py-3">
              <form onSubmit={(event) => void handleAdd(event)} className="flex items-center gap-2">
                <label htmlFor="new-task" className="sr-only">
                  New task title
                </label>
                <input
                  id="new-task"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Add a task…"
                  disabled={adding}
                  autoComplete="off"
                  className="min-w-0 flex-1 rounded-[12px] border border-border bg-background px-3 py-1.5 text-sm text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
                />

                <label htmlFor="new-task-points" className="sr-only">
                  Points
                </label>
                <input
                  id="new-task-points"
                  type="number"
                  min={0}
                  max={1000}
                  value={points}
                  onChange={(event) => setPoints(Number(event.target.value))}
                  disabled={adding}
                  className="w-16 rounded-[12px] border border-border bg-background px-2 py-1.5 text-sm text-text tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
                />

                <button
                  type="submit"
                  disabled={!canAdd}
                  className={`press rounded-[12px] border border-primary bg-primary px-3 py-1.5 text-sm font-medium text-primary-contrast ${focusRing} disabled:opacity-40`}
                >
                  {adding ? 'Adding…' : 'Add'}
                </button>
              </form>

              {addError && (
                <p className="mt-2 mb-0 text-xs text-danger" role="alert">
                  {addError}
                </p>
              )}
            </div>
          )}

          {actionError && (
            <p className="mt-2 mb-0 text-xs text-danger" role="alert">
              {actionError}
            </p>
          )}

          {tasks.length > 0 && (
            <div className="surface mt-3 px-4 py-1">
              <ul className="m-0 list-none p-0">
                {tasks.map((task, index) => (
                  <li
                    key={task.id}
                    className={removing[task.id] ? '' : 'border-b border-border last:border-b-0'}
                  >
                    <TaskItem
                      task={task}
                      index={index}
                      entering={task.id === justAdded}
                      exiting={removing[task.id] ?? false}
                      onToggle={canComplete ? (target) => void handleToggle(target) : undefined}
                      onSave={readOnly ? undefined : handleSave}
                      onDeleteRequest={readOnly ? undefined : handleDeleteRequest}
                      onDelete={readOnly ? undefined : (target) => void handleDelete(target)}
                      busy={busyId === task.id}
                    />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}