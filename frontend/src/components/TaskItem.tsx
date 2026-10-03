import { useEffect, useRef, useState } from 'react';
import type { AnimationEvent, KeyboardEvent, ReactElement } from 'react';
import type { MissReason, Task } from '../lib/types';

interface TaskEdit {
  title: string;
  points: number;
}

interface TaskItemProps {
  task: Task;
  /** Drives the entrance stagger. */
  index: number;
  lastTaskHint?: string;
  /** Renders the subtask tree indented, without the stagger animation. */
  nested?: boolean;
  /** Slides up on entry instead of fading, for a task just added. */
  entering?: boolean;
  /** Controls the row's delete or restore animation. */
  exitPhase?: 'exiting' | 'collapsing' | 'restoring';
  exitPhaseForTask?: (taskId: number) => 'exiting' | 'collapsing' | 'restoring' | undefined;
  /** Omitted for missed tasks: they are history and stay read-only. */
  onToggle?: (task: Task) => void;
  /** Saves title and points. Rejects with the API message to stay in edit mode. */
  onSave?: (task: Task, edit: TaskEdit) => Promise<void>;
  onReasonChange?: (task: Task, reason: MissReason | null) => Promise<void>;
  allowReasonEdit?: boolean;
  /** Starts the exit animation. The page marks the row as exiting. */
  onDeleteRequest?: (task: Task) => void;
  /** Called between the delete fade and space-collapse stages. */
  onDeleteCollapse?: (task: Task) => void;
  /** Called after the delete collapse or restore animation finishes. */
  onDeleteAnimationEnd?: (task: Task, phase: 'exiting' | 'restoring') => void;
  /** A toggle request is in flight for this task. */
  busy?: boolean;
}

/** Only the first eight rows are staggered. */
const STAGGER_LIMIT = 8;

interface LastTaskHintProps {
  message?: string;
}

interface LastTaskHintState {
  prop?: string;
  displayed: string;
  visible: boolean;
}

function LastTaskHint({ message }: LastTaskHintProps): ReactElement {
  const [hint, setHint] = useState<LastTaskHintState>({
    displayed: '',
    visible: false,
  });
  if (message !== hint.prop) {
    setHint({
      prop: message,
      displayed: message ?? hint.displayed,
      visible: Boolean(message),
    });
  }

  return (
    <span
      aria-hidden="true"
      className={`pointer-events-none absolute left-full top-1/2 z-10 ml-2 -translate-y-1/2 whitespace-nowrap text-[10px] font-normal text-muted no-underline transition-opacity duration-500 ${
        hint.visible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      {hint.displayed}
    </span>
  );
}

export function TaskItem({
  task,
  index,
  lastTaskHint,
  nested = false,
  entering = false,
  exitPhase,
  exitPhaseForTask,
  onToggle,
  onSave,
  onReasonChange,
  allowReasonEdit = false,
  onDeleteRequest,
  onDeleteCollapse,
  onDeleteAnimationEnd,
  busy = false,
}: TaskItemProps): ReactElement {
  const currentExitPhase = exitPhase ?? exitPhaseForTask?.(task.id);
  const done = task.status === 'done';
  const missed = task.status === 'missed';
  const carried = task.carried_from_id !== null;
  const carriedTimes = task.carry_count > 1 ? task.carry_count : 0;

  // Missed tasks are history: they stay on their own day and are read-only.
  const mutable = !missed;
  const entrance = nested || entering ? '' : 'stagger fade-in';

  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(task.title);
  const [draftPoints, setDraftPoints] = useState(String(task.points));
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState('');
  const [reasonExpanded, setReasonExpanded] = useState(false);
  const [reasonBusy, setReasonBusy] = useState(false);
  const [reasonError, setReasonError] = useState('');
  // Escape removes the inputs, which can fire blur; this keeps that from saving.
  const cancelled = useRef(false);
  const deleteAnimationHandlers = useRef({
    task,
    onDeleteCollapse,
    onDeleteAnimationEnd,
  });

  useEffect(() => {
    deleteAnimationHandlers.current = { task, onDeleteCollapse, onDeleteAnimationEnd };
  }, [task, onDeleteCollapse, onDeleteAnimationEnd]);

  useEffect(() => {
    if (!editing) return;
    document.getElementById(`title-${task.id}`)?.focus();
  }, [editing, task.id]);

  const handleSlotAnimationEnd = (event: AnimationEvent<HTMLDivElement>): void => {
    const isSlotContent = event.target === event.currentTarget.firstElementChild;
    if (event.animationName === 'task-delete-content' && isSlotContent) {
      onDeleteCollapse?.(task);
    } else if (event.animationName === 'task-space-collapse' && event.target === event.currentTarget) {
      onDeleteAnimationEnd?.(task, 'exiting');
    } else if (event.animationName === 'task-space-restore' && event.target === event.currentTarget) {
      onDeleteAnimationEnd?.(task, 'restoring');
    } else if (
      event.animationName === 'task-reduced-fade' &&
      event.target === event.currentTarget &&
      currentExitPhase === 'restoring'
    ) {
      onDeleteAnimationEnd?.(task, 'restoring');
    } else if (event.animationName === 'task-reduced-exit' && isSlotContent) {
      onDeleteAnimationEnd?.(task, 'exiting');
    }
  };

  useEffect(() => {
    if (!currentExitPhase) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const duration =
      currentExitPhase === 'exiting'
        ? reducedMotion
          ? 150
          : 300
        : currentExitPhase === 'collapsing'
          ? reducedMotion
            ? 0
            : 250
          : reducedMotion
            ? 150
            : 250;
    const timer = window.setTimeout(() => {
      const handlers = deleteAnimationHandlers.current;
      if (currentExitPhase === 'exiting' && !reducedMotion) {
        handlers.onDeleteCollapse?.(handlers.task);
      } else {
        handlers.onDeleteAnimationEnd?.(
          handlers.task,
          currentExitPhase === 'restoring' ? 'restoring' : 'exiting',
        );
      }
    }, duration + 100);

    return () => window.clearTimeout(timer);
  }, [currentExitPhase, task.id]);

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
    'task-circle relative flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-border';

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
    <span
      dir="auto"
      className={`task-title user-text ${nested ? 'text-xs' : 'text-sm'}`}
      data-done={done}
      data-title={task.title}
    >
      <span className="task-title-base">{task.title}</span>
      <span aria-hidden="true" className="task-title-muted">
        {task.title}
      </span>
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

  const reasonOptions: { value: MissReason; label: string }[] = [
    { value: 'tired', label: 'Tired' },
    { value: 'no_time', label: 'No time' },
    { value: 'forgot', label: 'Forgot' },
    { value: 'too_big', label: 'Too big' },
    { value: 'emergency', label: 'Emergency' },
    { value: 'other', label: 'Other' },
  ];
  const selectedReason = missed ? task.miss_reason : task.source_miss_reason;
  const showReason = allowReasonEdit && onReasonChange && (missed || (carried && !done));

  const saveReason = async (reason: MissReason | null): Promise<void> => {
    if (!onReasonChange || reasonBusy) return;
    setReasonBusy(true);
    setReasonError('');
    try {
      await onReasonChange(task, reason);
      setReasonExpanded(false);
    } catch (error: unknown) {
      setReasonError(error instanceof Error ? error.message : 'Could not save that reason.');
    } finally {
      setReasonBusy(false);
    }
  };

  const reasonControl = showReason ? (
    <div className="mt-1">
      {selectedReason && !reasonExpanded ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-[10px] text-muted">
          {reasonOptions.find((option) => option.value === selectedReason)?.label ?? 'Reason'}
          <button
            type="button"
            onClick={() => setReasonExpanded(true)}
            className="rounded-sm underline underline-offset-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Change
          </button>
        </span>
      ) : !reasonExpanded ? (
        <button
          type="button"
          onClick={() => setReasonExpanded(true)}
          className="rounded-sm text-[11px] text-muted underline decoration-border underline-offset-2 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          Why did it slip?
        </button>
      ) : null}

      <div
        aria-hidden={!reasonExpanded}
        inert={!reasonExpanded}
        className={`grid transition-[grid-template-rows,opacity] duration-250 ease-[var(--ease)] motion-reduce:transition-none ${
          reasonExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="flex flex-wrap gap-1.5 py-1">
            {reasonOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={reasonBusy}
                aria-pressed={selectedReason === option.value}
                onClick={() =>
                  void saveReason(selectedReason === option.value ? null : option.value)
                }
                className="press rounded-full border border-border px-2 py-1 text-[10px] text-muted hover:border-primary hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
              >
                {option.label}
              </button>
            ))}
          </div>
          {reasonError && (
            <p role="status" className="mb-1 text-[11px] text-danger">
              {reasonError}
            </p>
          )}
        </div>
      </div>
    </div>
  ) : null;

  const editor = (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <label className="sr-only" htmlFor={`title-${task.id}`}>
        Task title
      </label>
      <input
        id={`title-${task.id}`}
        dir="auto"
        value={draftTitle}
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
      className={`group flex items-start gap-3 py-2 ${missed ? 'opacity-45' : ''} ${entrance} ${
        entering && !nested ? 'task-add-content' : ''
      }`}
      style={{ '--stagger-index': index < STAGGER_LIMIT ? index : 0 } as React.CSSProperties}
    >
      {onToggle && !missed ? (
        <button
          type="button"
          onClick={() => onToggle(task)}
          disabled={busy}
          aria-pressed={done}
          data-done={done}
          aria-label={done ? `Mark "${task.title}" as not done` : `Mark "${task.title}" as done`}
          className={`press ${shell} ${focusRing} disabled:opacity-60`}
        >
          {check}
        </button>
      ) : (
        <span className={shell} data-done={done} aria-hidden="true">
          {check}
        </span>
      )}

      <div className="task-edit-stack min-w-0 flex-1">
        <div
          aria-hidden={editing}
          inert={editing}
          className={`task-edit-layer ${editing ? 'task-edit-layer-hidden' : ''}`}
        >
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="relative inline-block align-baseline">
              {onSave && mutable ? (
                <button
                  type="button"
                  onClick={startEditing}
                  aria-label={`Edit "${task.title}"`}
                  className={`min-w-0 rounded-[12px] text-start ${focusRing}`}
                >
                  {titleText}
                </button>
              ) : (
                titleText
              )}
              <LastTaskHint message={lastTaskHint} />
            </span>
            {badges}
          </div>
          {task.notes && (
            <p dir="auto" className="user-text mt-0.5 mb-0 text-xs text-muted">
              {task.notes}
            </p>
          )}
          {reasonControl}
          {editError && (
            <p className="mt-1 mb-0 text-xs text-danger" role="alert">
              {editError}
            </p>
          )}
        </div>
        <div
          aria-hidden={!editing}
          inert={!editing}
          className={`task-edit-layer ${!editing ? 'task-edit-layer-hidden' : ''}`}
        >
          {editor}
          {editError && (
            <p className="mt-1 mb-0 text-xs text-danger" role="alert">
              {editError}
            </p>
          )}
        </div>
      </div>

      <span
        aria-hidden={editing}
        className={`task-points shrink-0 text-xs ${
          nested ? 'leading-4' : 'leading-5'
        } text-muted tabular-nums ${
          editing ? 'task-edit-side-hidden' : ''
        }`}
        data-done={done}
      >
          {task.points}
      </span>

      {mutable && (
        <span
          aria-hidden={editing}
          inert={editing}
          className={`flex shrink-0 items-center gap-1 opacity-100 md:opacity-0 md:transition-opacity md:group-hover:opacity-100 md:group-focus-within:opacity-100 ${
            editing ? 'task-edit-side-hidden' : ''
          }`}
        >
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
              disabled={currentExitPhase !== undefined}
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

  return (
    <div
      onAnimationEnd={handleSlotAnimationEnd}
      inert={currentExitPhase === 'exiting' || currentExitPhase === 'collapsing'}
      className={`task-slot grid ${currentExitPhase === 'exiting' ? 'task-slot-exiting' : ''} ${
        currentExitPhase === 'collapsing' ? 'task-slot-collapsing' : ''
      } ${currentExitPhase === 'restoring' ? 'task-slot-restoring' : ''} ${
        entering && !nested ? 'task-slot-entering' : ''
      }`}
    >
      <div className="task-slot-content min-h-0 overflow-hidden">
        {row}
        {task.subtasks.length > 0 && (
          <div className="border-l border-border pl-4">
            {task.subtasks.map((subtask) => (
              <TaskItem
                key={subtask.id}
                task={subtask}
                index={0}
                nested
                onToggle={onToggle}
                onSave={onSave}
                onReasonChange={onReasonChange}
                allowReasonEdit={allowReasonEdit}
                onDeleteRequest={onDeleteRequest}
                onDeleteCollapse={onDeleteCollapse}
                onDeleteAnimationEnd={onDeleteAnimationEnd}
                exitPhaseForTask={exitPhaseForTask}
                busy={busy}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}