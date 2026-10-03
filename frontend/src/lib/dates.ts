/**
 * Date helpers for Yomi.
 *
 * The backend defines a "day" in the user's timezone (TIMEZONE, default
 * Africa/Cairo), not in UTC. Anything derived from `Date.toISOString()` would
 * silently shift the day near midnight, so these helpers always work in local
 * time and build the string by hand.
 */

/** Today's local calendar date as "YYYY-MM-DD". */
export function todayISO(): string {
  return toISO(new Date());
}

/** The local calendar date `n` days from `iso`. */
export function addDays(iso: string, n: number): string {
  return toISO(addLocalDays(parseISO(iso), n));
}

function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

/** Formats using local getFullYear/getMonth/getDate, never UTC accessors. */
function toISO(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Parses "YYYY-MM-DD" into a local midnight Date. */
function parseISO(iso: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) {
    throw new Error(`Invalid date, expected YYYY-MM-DD: ${iso}`);
  }

  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day));
}

/**
 * Adds days using the Date constructor so month/year rollover is handled for us.
 */
function addLocalDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}