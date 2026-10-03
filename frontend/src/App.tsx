import { ThemeToggle } from './components/ThemeToggle';
import { TodayPage } from './pages/TodayPage';
import './index.css';

function App() {
  return (
    <div className="flex min-h-full flex-col bg-background text-text">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
        <h1 className="m-0 text-lg font-semibold">Yomi</h1>
        <ThemeToggle />
      </header>
      <main className="flex-1">
        <TodayPage />
      </main>
    </div>
  );
}

export default App;