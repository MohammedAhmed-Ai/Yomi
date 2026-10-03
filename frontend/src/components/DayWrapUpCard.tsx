import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import type { KeyboardEvent, ReactElement } from 'react';
import { ApiError, updateDay } from '../lib/api';
import type { Day } from '../lib/types';

export interface DayWrapUpHandle {
  flush: () => Promise<boolean>;
}

interface DayWrapUpCardProps {
  day: Day;
  isToday: boolean;
}

const MOODS = [
  { value: 1, face: '😞', label: 'Rough' },
  { value: 2, face: '🙁', label: 'Low' },
  { value: 3, face: '😐', label: 'Okay' },
  { value: 4, face: '🙂', label: 'Good' },
  { value: 5, face: '😄', label: 'Great' },
] as const;

function messageFor(error: unknown): string {
  if (error instanceof ApiError && (error.status === 409 || error.status === 422)) {
    return error.message;
  }
  return 'Could not save this note. It is still here; try changing it to retry.';
}

export const DayWrapUpCard = forwardRef<DayWrapUpHandle, DayWrapUpCardProps>(
  function DayWrapUpCard({ day, isToday }, ref): ReactElement {
    const [reflection, setReflection] = useState(day.reflection ?? '');
    const [mood, setMood] = useState<number | null>(day.mood);
    const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
    const [saveError, setSaveError] = useState('');
    const [moodError, setMoodError] = useState('');
    const draftRef = useRef(reflection);
    const dateRef = useRef(day.date);
    const revisionRef = useRef(0);
    const savedRevisionRef = useRef(0);
    const failedRevisionRef = useRef(0);
    const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const saveInFlightRef = useRef<Promise<boolean> | null>(null);
    const moodRequestRef = useRef(0);
    const moodRef = useRef(mood);
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    const flush = useCallback(async (): Promise<boolean> => {
      if (saveTimerRef.current !== null) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }

      while (savedRevisionRef.current < revisionRef.current) {
        const inFlight = saveInFlightRef.current;
        if (inFlight) {
          const succeeded = await inFlight;
          if (
            !succeeded &&
            failedRevisionRef.current === revisionRef.current
          ) {
            return false;
          }
          continue;
        }

        const revision = revisionRef.current;
        const text = draftRef.current;
        const targetDate = dateRef.current;
        setSaveState('saving');
        setSaveError('');
        const request = updateDay(targetDate, { reflection: text })
          .then(() => {
            savedRevisionRef.current = Math.max(savedRevisionRef.current, revision);
            if (revisionRef.current === revision) setSaveState('saved');
            return true;
          })
          .catch((error: unknown) => {
            failedRevisionRef.current = revision;
            if (revisionRef.current === revision) {
              setSaveState('error');
              setSaveError(messageFor(error));
            }
            return false;
          })
          .finally(() => {
            if (saveInFlightRef.current === request) saveInFlightRef.current = null;
          });
        saveInFlightRef.current = request;
        const succeeded = await request;
        if (!succeeded && revisionRef.current === revision) return false;
      }
      return true;
    }, []);

    useImperativeHandle(ref, () => ({ flush }), [flush]);

    useEffect(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }, [reflection]);

    useEffect(() => {
      if (saveState !== 'saved') return;
      const timer = window.setTimeout(() => setSaveState('idle'), 1800);
      return () => window.clearTimeout(timer);
    }, [saveState]);

    useEffect(
      () => () => {
        if (saveTimerRef.current !== null) clearTimeout(saveTimerRef.current);
      },
      [],
    );

    const handleReflectionChange = (value: string): void => {
      draftRef.current = value;
      revisionRef.current += 1;
      setReflection(value);
      setSaveError('');
      setSaveState('idle');
      if (saveTimerRef.current !== null) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => void flush(), 800);
    };

    const saveMood = async (nextMood: number | null): Promise<void> => {
      const requestId = ++moodRequestRef.current;
      const previousMood = moodRef.current;
      moodRef.current = nextMood;
      setMood(nextMood);
      setMoodError('');
      try {
        await updateDay(day.date, { mood: nextMood });
      } catch (error: unknown) {
        if (requestId !== moodRequestRef.current) return;
        moodRef.current = previousMood;
        setMood(previousMood);
        setMoodError(messageFor(error));
      }
    };

    const handleMoodKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
      const currentIndex = MOODS.findIndex((item) => item.value === moodRef.current);
      let nextIndex: number | null = null;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
        nextIndex = (currentIndex + 1 + MOODS.length) % MOODS.length;
      } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
        nextIndex = (currentIndex <= 0 ? MOODS.length : currentIndex) - 1;
      } else if (event.key === 'Home') {
        nextIndex = 0;
      } else if (event.key === 'End') {
        nextIndex = MOODS.length - 1;
      }
      if (nextIndex === null) return;
      event.preventDefault();
      const item = MOODS[nextIndex];
      void saveMood(item.value);
      document.getElementById(`mood-${day.date}-${item.value}`)?.focus();
    };

    return (
      <section className="surface mt-4 px-4 py-4" aria-labelledby={`wrap-up-${day.date}`}>
        <h3 id={`wrap-up-${day.date}`} className="m-0 text-base font-semibold">
          {isToday ? 'Wrap up your day' : 'Notes for this day'}
        </h3>

        <div className="mt-4">
          <span className="mb-2 block text-xs font-medium text-muted">Mood</span>
          <div
            role="radiogroup"
            aria-label="Mood"
            onKeyDown={handleMoodKeyDown}
            className="flex items-start justify-between gap-1"
          >
            {MOODS.map((item) => (
              <button
                key={item.value}
                id={`mood-${day.date}-${item.value}`}
                type="button"
                role="radio"
                aria-label={item.label}
                aria-checked={mood === item.value}
                tabIndex={mood === item.value || (mood === null && item.value === 1) ? 0 : -1}
                onClick={() => void saveMood(mood === item.value ? null : item.value)}
                className={`press flex min-w-0 flex-1 flex-col items-center gap-1 rounded-[12px] px-1 py-2 text-muted hover:bg-background hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  mood === item.value ? 'bg-background text-text' : ''
                }`}
              >
                <span aria-hidden="true" className="text-2xl leading-none">
                  {item.face}
                </span>
                <span className="text-[10px]">{item.label}</span>
              </button>
            ))}
          </div>
          {moodError && (
            <p className="mt-2 mb-0 text-xs text-danger" role="status">
              {moodError}
            </p>
          )}
        </div>

        <div className="mt-4">
          <label htmlFor={`reflection-${day.date}`} className="mb-2 block text-xs font-medium text-muted">
            Reflection
          </label>
          <textarea
            ref={textareaRef}
            id={`reflection-${day.date}`}
            dir="auto"
            maxLength={2000}
            rows={2}
            value={reflection}
            onChange={(event) => handleReflectionChange(event.target.value)}
            onBlur={() => void flush()}
            placeholder="A line or two about your day..."
            className="min-h-16 w-full resize-none overflow-hidden rounded-[12px] border border-border bg-background px-3 py-2 text-start text-sm text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
          <div className="mt-1 flex min-h-4 items-center justify-between gap-2">
            <span
              aria-live="polite"
              className={`text-[11px] text-muted transition-opacity duration-500 ${
                saveState === 'saving' || saveState === 'saved' ? 'opacity-100' : 'opacity-0'
              }`}
            >
              {saveState === 'saving' ? 'Saving...' : saveState === 'saved' ? 'Saved' : ''}
            </span>
            {saveState === 'error' ? (
              <span role="status" className="text-[11px] text-danger">
                {saveError}
              </span>
            ) : (
              <span className="text-[10px] text-muted">{reflection.length}/2000</span>
            )}
          </div>
        </div>
      </section>
    );
  },
);
