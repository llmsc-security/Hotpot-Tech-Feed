import { useState } from "react";
import { Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getStats } from "./api";
import ContributeModal from "./components/ContributeModal";
import SourcesDrawer from "./components/SourcesDrawer";

const REPO_URL = "https://github.com/llmsc-security/Hotpot-Tech-Feed";

function GithubIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={className}
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.218.682-.483
          0-.237-.009-.868-.014-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608
          1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.339-2.221-.253-4.555-1.113-4.555-4.951
          0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337
          1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688
          0 3.847-2.337 4.695-4.566 4.943.359.31.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747
          0 .268.18.58.688.482A10.02 10.02 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

function CorpusIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  );
}

function HeaderRight({
  onContribute,
  onShowSources,
}: {
  onContribute: () => void;
  onShowSources: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const count = data?.items;
  const formatted = count == null ? "…" : count.toLocaleString();

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onContribute}
        className="inline-flex items-center gap-1.5 rounded-full
                   bg-brand-amber/95 hover:bg-brand-amber text-brand-dark
                   px-3 py-1.5 text-xs font-semibold transition-colors shadow-sm"
        title="Submit a paper, blog post, or news URL"
      >
        <span aria-hidden="true">＋</span>
        <span>I want to contribute</span>
      </button>
      <button
        type="button"
        onClick={onShowSources}
        className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10
                   border border-white/15 text-sm tabular-nums hover:bg-white/15
                   hover:border-white/25 transition-colors"
        title={
          data
            ? `${data.items.toLocaleString()} items across ${data.sources.toLocaleString()} sources — click to browse`
            : "Loading corpus stats…"
        }
      >
        <CorpusIcon className="w-4 h-4 text-brand-amber" />
        <span className="text-slate-200">corpus</span>
        <span className="font-semibold text-white">{formatted}</span>
      </button>
      <a
        href={REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="text-slate-200 hover:text-white transition-colors"
        aria-label="View on GitHub"
        title="View on GitHub"
      >
        <GithubIcon className="w-6 h-6" />
      </a>
    </div>
  );
}

export default function App() {
  const [showContribute, setShowContribute] = useState(false);
  const [showSources, setShowSources] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-brand-dark text-white">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🌶️</span>
            <span className="font-serif text-2xl font-bold">Hotpot Tech Feed</span>
          </div>
          <HeaderRight
            onContribute={() => setShowContribute(true)}
            onShowSources={() => setShowSources(true)}
          />
        </div>
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
        <Outlet />
      </main>

      <footer className="text-xs text-slate-500 text-center py-6 border-t border-slate-200">
        feed.ai2wj.com — daily CS digest · powered by{" "}
        <span className="font-semibold text-slate-700">Qwen3.5</span>, a free
        self-hosted LLM
      </footer>

      {showContribute && <ContributeModal onClose={() => setShowContribute(false)} />}
      {showSources && <SourcesDrawer onClose={() => setShowSources(false)} />}
    </div>
  );
}
