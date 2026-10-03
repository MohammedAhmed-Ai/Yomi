import { useEffect, useState } from 'react';
import { ThemeToggle } from './components/ThemeToggle';
import { HistoryPage } from './pages/HistoryPage';
import { TodayPage } from './pages/TodayPage';
import { useToday } from './lib/useToday';
import './index.css';

function App() {
  const today = useToday();
  const [showHistory, setShowHistory] = useState(() =>
    window.location.hash === '#/history' || window.location.hash.startsWith('#/history/'),
  );

  useEffect(() => {
    const onHashChange = (): void =>
      setShowHistory(
        window.location.hash === '#/history' || window.location.hash.startsWith('#/history/'),
      );
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  return (
    <div className="flex min-h-full flex-col bg-background text-text">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
        <h1 className="m-0 text-lg font-semibold">Yomi</h1>
        <div className="flex items-center gap-2">
          <nav aria-label="Main navigation" className="flex items-center gap-1">
            <a
              href={`#/${today}`}
              aria-current={!showHistory ? 'page' : undefined}
              className={`rounded-[12px] px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                showHistory ? 'text-muted hover:text-text' : 'bg-background font-medium text-text'
              }`}
            >
              Today
            </a>
            <a
              href="#/history"
              aria-current={showHistory ? 'page' : undefined}
              className={`rounded-[12px] px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                showHistory ? 'bg-background font-medium text-text' : 'text-muted hover:text-text'
              }`}
            >
              History
            </a>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main className="flex-1">
        {showHistory ? <HistoryPage /> : <TodayPage />}
      </main>
    </div>
  );
}

export default App;