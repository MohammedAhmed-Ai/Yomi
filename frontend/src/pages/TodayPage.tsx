import { useCallback, useEffect, useState } from 'react';
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
import { todayISO } from '../lib/dates';
import type { Day, DayScore, Task } from '../lib/types';
import { ScoreCard } from '../components/ScoreCard';
import { TaskItem } from '../components/TaskItem';

type LoadState = 'loading' | 'ready' | 'error';

const DEFAULT_POINTS = 10;

/**
 * Loads today. Carry-over runs first, but failing it must not hide the day, so
 * its error becomes a warning and the day is still fetched.
 */
async function fetchToday(date: string): Promise<{ day: Day; score: DayScore; warning: string }> {
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

/** "Saturday, 3 October" â€” the long-form header, without the year. */
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
  const [day, setDay] = useState<Day | null>(null);
  const [score, setScore] = useState<DayScore | null>(null);
  const [message, setMessage] = useState('');
  const [attempt, setAttempt] = useState(0);

  const [title, setTitle] = useState('');
  const [points, setPoints] = useState(DEFAULT_POINTS);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState('');
  const [justAdded, setJustAdded] = useState<number | null>(null);
  const [removing, setRemoving] = useState<Record<number, boolean>>({});

  useEffect(() => {
    let cancelled = false;

    const run = async (): Promise<void> => {
      try {
        const result = await fetchToday(todayISO());
        if (cancelled) return;
        setDay(result.day);
        setScore(result.score);
        setMessage(result.warning);
        setState('ready');
      } catch (error: unknown) {
        if (cancelled) return;
        setMessage(errorMessage(error, 'Something went wrong'));
        setState('error');
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  /** Reloads the day and score after a mutation. */
  const refresh = useCallback(async (date: string) => {
    const [freshDay, freshScore] = await Promise.all([getDay(date), getScore(date)]);
    setDay(freshDay);
    setScore(freshScore);
  }, []);

  const retry = (): void => {
    setState('loading');
    setMessage('');
    setAttempt((value) => value + 1);
  };

  const handleAdd = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || adding) return;

    setAdding(true);
    setAddError('');

    try {
      const created = await createTask({
        title: trimmed,
        points,
        planned_date: todayISO(),
      });
      setTitle('');
      await refresh(todayISO());
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
    setDay((current) =>
      current
        ? {
            ...current,
            tasks: patchTask(current.tasks, task.id, (t) => ({
              ...t,
              status: wasDone ? 'pending' : 'done',
            })),
          }
        : current,
    );

    try {
      const updated = wasDone ? await uncompleteTask(task.id) : await completeTask(task.id);
      setDay((current) =>
        current ? { ...current, tasks: patchTask(current.tasks, task.id, () => updated) } : current,
      );
      setScore(await getScore(todayISO()));
    } catch (error: unknown) {
      setDay((current) =>
        current ? { ...current, tasks: patchTask(current.tasks, task.id, () => task) } : current,
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
      setDay((current) =>
        current ? { ...current, tasks: patchTask(current.tasks, task.id, () => updated) } : current,
      );
      setScore(await getScore(todayISO()));
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
      setDay((current) =>
        current ? { ...current, tasks: removeTask(current.tasks, task.id) } : current,
      );
      setScore(await getScore(todayISO()));
    } catch (error: unknown) {
      // Bring the row back and explain why it stayed.
      setActionError(errorMessage(error, 'Could not delete that task.'));
    } finally {
      clearRemoving(task.id);
      setBusyId(null);
    }
  };

  if (state === 'loading') {
    return (
      <div className="mx-auto w-full max-w-[640px] px-4 py-6">
        <div className="h-6 w-48 animate-pulse rounded bg-border" />
        <div className="surface mt-3 h-24 animate-pulse" />
        <div className="surface mt-4 h-40 animate-pulse" />
        <p className="mt-4 text-center text-sm text-muted">Loading todayâ€¦</p>
      </div>
    );
  }

  if (state === 'error' || !day || !score) {
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

  const tasks = rootTasks(day);
  const canAdd = title.trim().length > 0 && !adding;

  return (
    <div className="mx-auto w-full max-w-[640px] px-4 py-6">
      <h2 className="fade-in m-0 text-xl font-semibold">{formatHeading(day.date)}</h2>

      <div className="mt-3">
        <ScoreCard score={score} />
      </div>

      {message && (
        <p className="mt-2 text-xs text-muted" role="status">
          {message}
        </p>
      )}

      <div className="surface mt-4 px-4 py-3">
        <form onSubmit={(event) => void handleAdd(event)} className="flex items-center gap-2">
          <label htmlFor="new-task" className="sr-only">
            New task title
          </label>
          <input
            id="new-task"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Add a taskâ€¦"
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
            className="press rounded-[12px] border border-primary bg-primary px-3 py-1.5 text-sm font-medium text-primary-contrast focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:opacity-40"
          >
            {adding ? 'Addingâ€¦' : 'Add'}
          </button>
        </form>

        {addError && (
          <p className="mt-2 text-xs text-danger" role="alert">
            {addError}
          </p>
        )}

        {actionError && (
          <p className="mt-2 text-xs text-danger" role="alert">
            {actionError}
          </p>
        )}
      </div>

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
                  onToggle={(target) => void handleToggle(target)}
                  onSave={handleSave}
                  onDeleteRequest={handleDeleteRequest}
                  onDelete={(target) => void handleDelete(target)}
                  busy={busyId === task.id}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
