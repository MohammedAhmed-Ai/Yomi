/**
 * Types mirroring the FastAPI schemas in app/schemas.py.
 *
 * Dates are ISO calendar strings ("YYYY-MM-DD"); timestamps are ISO 8601 UTC
 * strings. Server-owned lifecycle fields are included on read shapes but the
 * write shapes below deliberately omit them, because the API rejects them.
 */

/** "pending" | "done" | "missed" | "deleted". See Task.status in app/models.py. */
export type TaskStatus = 'pending' | 'done' | 'missed' | 'deleted';

/** 0 (none) through 3 (highest). */
export type Priority = 0 | 1 | 2 | 3;

export interface Tag {
  id: number;
  name: string;
  /** Hex colour, 3 or 6 digits, e.g. "#4f46e5". */
  color: string;
}

export interface Task {
  id: number;
  title: string;
  notes: string | null;
  points: number;
  priority: Priority;
  planned_date: string | null;
  original_date: string | null;
  parent_task_id: number | null;
  recurrence_rule: string | null;
  sort_order: number;

  status: TaskStatus;
  completed_at: string | null;
  completed_date: string | null;
  carry_count: number;
  /** Set on a carried-over copy: the task it was cloned from. */
  carried_from_id: number | null;
  created_at: string;
  deleted_at: string | null;

  tags: Tag[];
  subtasks: Task[];
}

export interface Day {
  date: string;
  started_at: string | null;
  locked: boolean;
  reflection: string | null;
  mood: number | null;
  /** Flat list: group by parent_task_id, or use each task's nested subtasks. */
  tasks: Task[];
}

/**
 * All-or-nothing scoring: `score` is the day's full point value only when every
 * planned top-level task was completed on that day, otherwise 0.
 */
export interface DayScore {
  date: string;
  is_empty: boolean;
  is_complete: boolean;
  tasks_total: number;
  tasks_done: number;
  subtasks_total: number;
  subtasks_done: number;
  total_points: number;
  earned_points: number;
  score: number;
}

export interface StatsRangeDay {
  date: string;
  tasks_total: number;
  tasks_done: number;
  total_points: number;
  earned_points: number;
  completion_pct: number;
  score: number;
  is_complete: boolean;
  is_empty: boolean;
}

export interface StatsRangeSummary {
  days_complete: number;
  days_with_tasks: number;
  total_score: number;
  avg_completion_pct: number;
}

export interface StatsRange {
  days: StatsRangeDay[];
  summary: StatsRangeSummary;
}

export interface CarryOverResult {
  date: string;
  tasks_carried: number;
  subtasks_carried: number;
  total_carried: number;
}

// --- Request bodies ---

/** POST /api/tasks/ — the server owns status, completion and deletion fields. */
export interface TaskCreate {
  title: string;
  notes?: string | null;
  points?: number;
  priority?: Priority;
  planned_date?: string | null;
  original_date?: string | null;
  parent_task_id?: number | null;
  recurrence_rule?: string | null;
  sort_order?: number;
}

/** PATCH /api/tasks/{id}/ — every field optional; only sent fields are applied. */
export interface TaskUpdate {
  title?: string;
  notes?: string | null;
  points?: number;
  priority?: Priority;
  miss_reason?: string | null;
  sort_order?: number;
}

/** PATCH /api/days/{date}/ — a locked day stays editable; only its tasks freeze. */
export interface DayUpdate {
  reflection?: string | null;
  mood?: number | null;
  locked?: boolean;
}