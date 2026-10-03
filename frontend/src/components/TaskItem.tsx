import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent, ReactElement } from 'react';
import type { Task } from '../lib/types';

interface TaskEdit {
  title: string;
  points: number;
}

interface TaskItemProps {
  task: Task;
  /** Drives the entrance stagger. */
  index: number;
  /** Renders the subtask tree indented, without the stagger animation. */
  nested?: boolean;
  /** Slides up on entry instead of fading, for a task just added. */
  entering?: boolean;
  /** Fades and collapses the row before the delete request is sent. */
  exiting?: boolean;
  /** Omitted for missed tasks: they are history and stay read-only. */
  onToggle?: (task: Task) => void;
  /** Saves title and points. Rejects with the API message to stay in edit mode. */
  onSave?: (task: Task, edit: TaskEdit) => Promise<void>;
  /** Starts the exit animation. The page marks the row as exiting. */
  onDeleteRequest?: (task: Task) => void;
  /** Called once the row has faded and collapsed, to run the request. */
  onDelete?: (task: Task) => void;
  /** A toggle request is in flight for this task. */
  busy?: boolean;
}

const EXIT_MS = 240;

/** Only the first eight rows are staggered. */
const STAGGER_LIMIT = 8;

export function TaskItem({
  task,
  index,
  nested = false,
  entering = false,
  exiting = false,
  onToggle,
  onSave,
  onDeleteRequest,
  onDelete,
  busy = false,
}: TaskItemProps): ReactElement {
  const done = task.status === 'done';
  const missed = task.status === 'missed';
  const carried = task.carried_from_id !== null;
  const carriedTimes = task.carry_count > 1 ? task.carry_count : 0;

  // Missed tasks are history: they stay on their own day and are read-only.
  const mutable = !missed;
  const entrance = nested ? '' : entering ? 'slide-up' : 'stagger fade-in';

  const rowRef = useRef<HTMLDivElement | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(task.title);
  const [draftPoints, setDraftPoints] = useState(String(task.points));
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState('');
  // Escape removes the inputs, which can fire blur; this keeps that from saving.
  const cancelled = useRef(false);

  // Measure before paint so the collapse starts at the row's real height.
  useLayoutEffect(() => {
    if (exiting && rowRef.current) {
      rowRef.current.style.setProperty('--exit-height', `${rowRef.current.offsetHeight}px`);
    }
  }, [exiting]);

  // A delete is driven by the page; nothing to clean up here.
  useEffect(() => {
    if (!exiting || !onDelete) return;
    const timer = setTimeout(() => onDelete(task), EXIT_MS);
    return () => clearTimeout(timer);
  }, [exiting, onDelete, task]);

  const startEditing = (): void => {
    cancelled.current = false;
    setDraftTitle(task.title);
    setDraftPoints(String(task.points));
    setEditError('');
    setEditing(true);
  };

  const cancelEditing = (): void => {
    cancelled.current = true;
    setEditing(false);
  };

  const save = async (): Promise<void> => {
    if (cancelled.current || !onSave || saving) return;

    const title = draftTitle.trim();
    const points = Number(draftPoints);

    if (!title) {
      setEditError('A task needs a title.');
      return;
    }
    if (!Number.isFinite(points) || points < 0 || points > 1000) {
      setEditError('Points must be between 0 and 1000.');
      return;
    }
    if (title === task.title && points === task.points) {
      setEditing(false);
      return;
    }

    setSaving(true);
    setEditError('');
    try {
      await onSave(task, { title, points });
      setEditing(false);
    } catch (error: unknown) {
      setEditError(error instanceof Error ? error.message : 'Could not save that task.');
    } finally {
      setSaving(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent): void => {
    if (event.key === 'Escape') {
      event.preventDefault();
      cancelEditing();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      void save();
    }
  };

  const shell =
    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ' +
    (done ? 'border-success bg-success' : 'border-border');

  const focusRing =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface';

  const check = (
    <svg viewBox="0 0 12 12" className="task-check h-3 w-3" fill="none" strokeWidth="2.5">
      <path
        d="M2.5 6.5 5 9l4.5-6"
        stroke="var(--color-primary-contrast)"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );

  const titleText = (
    <span className={`task-title ${nested ? 'text-xs' : 'text-sm'}`} data-done={done}>
      {task.title}
    </span>
  );

  const badges = (
    <>
      {carried && (
        <span className="rounded-full border border-border px-1.5 py-0.5 text-[10px] leading-none text-muted">
          Carried over
          {carriedTimes > 0 ? ` ×${carriedTimes + 1}` : ''}
        </span>
      )}
      {missed && (
        <span className="rounded-full border border-border px-1.5 py-0.5 text-[10px] leading-none text-muted">
          Missed
        </span>
      )}
    </>
  );

  const editor = (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <label className="sr-only" htmlFor={`title-${task.id}`}>
        Task title
      </label>
      <input
        id={`title-${task.id}`}
        value={draftTitle}
        autoFocus
        disabled={saving}
        onChange={(event) => setDraftTitle(event.target.value)}
        onBlur={() => void save()}
        onKeyDown={onKeyDown}
        className={`min-w-0 flex-1 rounded-[12px] border border-border bg-background px-2 py-1 text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60 ${
          nested ? 'text-xs' : 'text-sm'
        }`}
      />

      <label className="sr-only" htmlFor={`points-${task.id}`}>
        Points
      </label>
      <input
        id={`points-${task.id}`}
        type="number"
        min={0}
        max={1000}
        value={draftPoints}
        disabled={saving}
        onChange={(event) => setDraftPoints(event.target.value)}
        onBlur={() => void save()}
        onKeyDown={onKeyDown}
        className="w-16 rounded-[12px] border border-border bg-background px-2 py-1 text-sm text-text tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
      />

      <span className="text-[10px] text-muted">Enter saves · Esc cancels</span>
    </div>
  );

  const row = (
    <div
      ref={rowRef}
      className={`group flex items-start gap-3 py-2 ${missed ? 'opacity-45' : ''} ${entrance} ${
        exiting ? 'task-exit' : ''
      }`}
      style={{ '--stagger-index': index < STAGGER_LIMIT ? index : 0 } as React.CSSProperties}
    >
      {onToggle && !missed ? (
        <button
          type="button"
          onClick={() => onToggle(task)}
          disabled={busy}
          aria-pressed={done}
          aria-label={done ? `Mark "${task.title}" as not done` : `Mark "${task.title}" as done`}
          className={`press ${shell} ${focusRing} disabled:opacity-60`}
        >
          {check}
        </button>
      ) : (
        <span className={shell} aria-hidden="true">
          {check}
        </span>
      )}

      <div className="min-w-0 flex-1">
        {editing ? (
          editor
        ) : (
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            {onSave && mutable ? (
              <button
                type="button"
                onClick={startEditing}
                aria-label={`Edit "${task.title}"`}
                className={`min-w-0 rounded-[12px] text-left ${focusRing}`}
              >
                {titleText}
              </button>
            ) : (
              titleText
            )}
            {badges}
          </div>
        )}

        {task.notes && !editing && (
          <p className="mt-0.5 mb-0 text-xs text-muted">{task.notes}</p>
        )}

        {editError && (
          <p className="mt-1 mb-0 text-xs text-danger" role="alert">
            {editError}
          </p>
        )}
      </div>

      {!editing && (
        <span className="shrink-0 text-xs text-muted tabular-nums">{task.points}</span>
      )}

      {!editing && mutable && (
        <span className="flex shrink-0 items-center gap-1 opacity-100 md:opacity-0 md:transition-opacity md:group-hover:opacity-100 md:group-focus-within:opacity-100">
          {onSave && (
            <button
              type="button"
              onClick={startEditing}
              aria-label={`Edit "${task.title}"`}
              className={`press rounded-[12px] p-1 text-muted hover:text-text ${focusRing}`}
            >
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" strokeWidth="1.5">
                <path
                  d="M11.5 2.5l2 2L6 12l-2.5.5L4 10z"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
          {onDeleteRequest && (
            <button
              type="button"
              onClick={() => onDeleteRequest(task)}
              disabled={exiting}
              aria-label={`Delete "${task.title}"`}
              className={`press rounded-[12px] p-1 text-muted hover:text-danger ${focusRing} disabled:opacity-40`}
            >
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" strokeWidth="1.5">
                <path
                  d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8h5.8l.6-8"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </span>
      )}
    </div>
  );

  if (task.subtasks.length === 0) return row;

  return (
    <div>
      {row}
      <div className="border-l border-border pl-4">
        {task.subtasks.map((subtask) => (
          <TaskItem
            key={subtask.id}
            task={subtask}
            index={0}
            nested
            entering={entering}
            exiting={exiting}
            onToggle={onToggle}
            onSave={onSave}
            onDeleteRequest={onDeleteRequest}
            onDelete={onDelete}
            busy={busy}
          />
        ))}
      </div>
    </div>
  );
}