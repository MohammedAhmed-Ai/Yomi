import type {
  CarryOverResult,
  Day,
  DayScore,
  DayUpdate,
  Tag,
  Task,
  TaskCreate,
  TaskUpdate,
} from './types';

/**
 * Thin typed wrapper over the Yomi API.
 *
 * Requests go to "/api/..." and rely on the Vite dev proxy (vite.config.ts)
 * forwarding to http://localhost:8000.
 */

const BASE = '/api';

/** An error response from the API, carrying the server's own message. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * FastAPI reports failures as {"detail": "..."}, but a validation error sends
 * detail as a list of objects instead. Both are flattened to one message.
 */
function extractDetail(body: unknown, fallback: string): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;

    if (typeof detail === 'string') return detail;

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (typeof item === 'object' && item !== null && 'msg' in item) {
            return String((item as { msg: unknown }).msg);
          }
          return String(item);
        })
        .join('; ');

      if (messages) return messages;
    }
  }

  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      detail = extractDetail(await response.json(), detail);
    } catch {
      // Non-JSON error body (e.g. an empty 204-adjacent failure): keep the fallback.
    }
    throw new ApiError(response.status, detail);
  }

  // 204 No Content (task deletion) has no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

// --- Days ---

/** Fetch a day, creating it server-side on first visit. */
export function getDay(date: string): Promise<Day> {
  return request<Day>(`/days/${date}`);
}

/** All-or-nothing score. Does not create the Day row. */
export function getScore(date: string): Promise<DayScore> {
  return request<DayScore>(`/days/${date}/score`);
}

/** Mark the day as started. Idempotent: the first start time is kept. */
export function startDay(date: string): Promise<Day> {
  return request<Day>(`/days/${date}/start`, { method: 'POST' });
}

/** Save the reflection/mood, or lock/unlock the day. */
export function updateDay(date: string, data: DayUpdate): Promise<Day> {
  return request<Day>(`/days/${date}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

// --- Tasks ---

export function createTask(data: TaskCreate): Promise<Task> {
  return request<Task>('/tasks/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function updateTask(id: number, data: TaskUpdate): Promise<Task> {
  return request<Task>(`/tasks/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/** No-op if already done. 409 if the task was missed, 423 if the day is locked. */
export function completeTask(id: number): Promise<Task> {
  return request<Task>(`/tasks/${id}/complete`, { method: 'POST' });
}

/** No-op if already pending. */
export function uncompleteTask(id: number): Promise<Task> {
  return request<Task>(`/tasks/${id}/uncomplete`, { method: 'POST' });
}

/** Soft delete, cascaded to subtasks. Returns nothing (204). */
export function deleteTask(id: number): Promise<void> {
  return request<void>(`/tasks/${id}`, { method: 'DELETE' });
}

// --- Tags & carry-over ---

export function getTags(): Promise<Tag[]> {
  return request<Tag[]>('/tags/');
}

/**
 * Move unfinished past-day work onto today and mark the originals missed.
 * Ignores the day lock; idempotent. See app/routers/carry_over.py.
 */
export function carryOver(): Promise<CarryOverResult> {
  return request<CarryOverResult>('/carry-over/', { method: 'POST' });
}