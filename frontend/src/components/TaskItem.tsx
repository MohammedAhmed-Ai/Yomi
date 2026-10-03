import type { ReactElement } from 'react';
import type { Task } from '../lib/types';

interface TaskItemProps {
  task: Task;
  /** Drives the entrance stagger. */
  index: number;
  /** Renders the subtask tree indented, without the stagger animation. */
  nested?: boolean;
  /** Slides up on entry instead of fading, for a task just added. */
  entering?: boolean;
  /** Omitted for missed tasks: they are history and stay read-only. */
  onToggle?: (task: Task) => void;
  /** A toggle request is in flight for this task. */
  busy?: boolean;
}

export function TaskItem({
  task,
  index,
  nested = false,
  entering = false,
  onToggle,
  busy = false,
}: TaskItemProps): ReactElement {
  const done = task.status === 'done';
  const missed = task.status === 'missed';
  const carried = task.carried_from_id !== null;
  const carriedTimes = task.carry_count > 1 ? task.carry_count : 0;

  // Missed tasks are history: they stay on their own day and are read-only.
  const interactive = onToggle !== undefined && !missed;
  const entrance = nested ? '' : entering ? 'slide-up' : 'stagger fade-in';

  const shell =
    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ' +
    (done ? 'border-success bg-success' : 'border-border');

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

  const row = (
    <div
      className={`flex items-start gap-3 py-2 ${missed ? 'opacity-45' : ''} ${entrance}`}
      style={{ '--stagger-index': index } as React.CSSProperties}
    >
      {interactive ? (
        <button
          type="button"
          onClick={() => onToggle(task)}
          disabled={busy}
          aria-pressed={done}
          aria-label={done ? `Mark "${task.title}" as not done` : `Mark "${task.title}" as done`}
          className={`press ${shell} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:opacity-60`}
        >
          {check}
        </button>
      ) : (
        <span className={shell} aria-hidden="true">
          {check}
        </span>
      )}

      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className={`task-title ${nested ? 'text-xs' : 'text-sm'}`} data-done={done}>
            {task.title}
          </span>

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
        </span>

        {task.notes && <span className="mt-0.5 block text-xs text-muted">{task.notes}</span>}
      </span>

      <span className="shrink-0 text-xs text-muted tabular-nums">{task.points}</span>
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
            onToggle={onToggle}
            busy={busy}
          />
        ))}
      </div>
    </div>
  );
}