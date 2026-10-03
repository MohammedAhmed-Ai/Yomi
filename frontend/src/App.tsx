import { ThemeToggle } from './components/ThemeToggle';
import './index.css';

function App() {
  return (
    <div className="min-h-full bg-background text-text">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
        <h1 className="m-0 text-lg font-semibold">Yomi</h1>
        <ThemeToggle />
      </header>
      <main className="flex min-h-[calc(100%-56px)] items-center justify-center px-4">
        <section className="surface fade-in max-w-md p-6 text-center">
          <p className="m-0 text-base">Today page coming next</p>
        </section>
      </main>
    </div>
  );
}

export default App;
