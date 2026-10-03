import type { ReactElement } from 'react';
import type { Task } from '../lib/types';

interface TaskItemProps {
  task: Task;
  /** Drives the entrance stagger. */
  index: number;
  /** Renders the subtask tree indented, without the stagger animation. */
  nested?: boolean;
}

/**
 * Read-only rendering of a task: a checkbox-style circle for the status, the
 * title and points, plus subtasks. Nothing here is clickable yet.
 */
export function TaskItem({ task, index, nested = false }: TaskItemProps): ReactElement {
  const done = task.status === 'done';
  const missed = task.status === 'missed';
  const carried = task.carried_from_id !== null;
  const carriedTimes = task.carry_count > 1 ? task.carry_count : 0;

  const row = (
    <div
      className={`flex items-start gap-3 py-2 ${missed ? 'opacity-45' : ''} ${
        nested ? '' : 'stagger fade-in'
      }`}
      style={{ '--stagger-index': index } as React.CSSProperties}
    >
      <span
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${
          done ? 'border-success bg-success' : 'border-border'
        }`}
        aria-hidden="true"
      >
        {done && (
          <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none" strokeWidth="2.5">
            <path
              d="M2.5 6.5 5 9l4.5-6"
              stroke="var(--color-primary-contrast)"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span
            className={`text-sm ${
              done ? 'text-muted line-through' : 'text-text'
            } ${nested ? 'text-xs' : ''}`}
          >
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
          <TaskItem key={subtask.id} task={subtask} index={0} nested />
        ))}
      </div>
    </div>
  );
}