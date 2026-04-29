import { Outlet } from "react-router-dom";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-brand-dark text-white">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🌶️</span>
            <span className="font-serif text-2xl font-bold">Hotpot Tech Feed</span>
          </div>
          <nav className="text-sm text-slate-300">
            <a href="/" className="hover:text-brand-amber">Browse</a>
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        <Outlet />
      </main>

      <footer className="text-xs text-slate-500 text-center py-6 border-t border-slate-200">
        feed.ai2wj.com — daily CS digest
      </footer>
    </div>
  );
}
