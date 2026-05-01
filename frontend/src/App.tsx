import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getStats } from "./api";
import CommunityModal from "./components/CommunityModal";
import ConsentBanner from "./components/ConsentBanner";
import {
  BellIcon,
  BookmarkIcon,
  DatabaseIcon,
  FlameIcon,
  GithubIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  ShieldIcon,
  SparklesIcon,
} from "./components/HotpotIcons";
import SourcesDrawer from "./components/SourcesDrawer";

const REPO_URL = "https://github.com/llmsc-security/Hotpot-Tech-Feed";
const SIDEBAR_TOPICS: [string, string, boolean][] = [
  ["LLM agents", "12", true],
  ["RAG", "6", true],
  ["Security", "hot", false],
  ["Robotics", "2", false],
  ["Compilers", "0", false],
];

function focusAsk() {
  window.dispatchEvent(new Event("hotpot:focus-ask"));
}

function askHotpot(query: string) {
  window.dispatchEvent(new CustomEvent("hotpot:ask-query", { detail: query }));
}

function HeaderRight({
  onShowCommunity,
  onShowSources,
}: {
  onShowCommunity: () => void;
  onShowSources: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const count = data?.items;
  const formatted = count == null ? "..." : count.toLocaleString();

  return (
    <div className="gx-top-actions">
      <button
        type="button"
        onClick={onShowCommunity}
        className="gx-icon-btn gx-icon-btn-accent"
        title="Share a URL or browse community contributions"
      >
        <PlusIcon size={16} />
        <span className="hidden xl:inline">Contribute</span>
      </button>
      <button
        type="button"
        onClick={onShowSources}
        className="gx-corpus-pill"
        title={
          data
            ? `${data.items.toLocaleString()} items across ${data.sources.toLocaleString()} sources`
            : "Loading corpus stats"
        }
      >
        <DatabaseIcon size={16} />
        <span className="hidden sm:inline">corpus</span>
        <strong>{formatted}</strong>
      </button>
      <button
        type="button"
        className="gx-icon-btn hidden sm:inline-flex"
        title="Notifications are not implemented yet"
        disabled
      >
        <BellIcon size={17} />
      </button>
      <button
        type="button"
        className="gx-icon-btn hidden sm:inline-flex"
        title="Settings are not implemented yet"
        disabled
      >
        <SettingsIcon size={17} />
      </button>
      <GithubLinkWithTip />
      <div className="gx-avatar" title="Hotpot workspace">
        H
      </div>
    </div>
  );
}

function GithubLinkWithTip() {
  const [showTip, setShowTip] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  function revealTip() {
    setShowTip(true);
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      setShowTip(false);
      timerRef.current = null;
    }, 6000);
  }

  return (
    <div
      className="relative shrink-0"
      onMouseEnter={revealTip}
      onFocus={revealTip}
      onTouchStart={revealTip}
    >
      <a
        href={REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="gx-icon-btn"
        aria-label="View ranking and scoring algorithm notes on GitHub"
        title="View on GitHub"
      >
        <GithubIcon className="h-[18px] w-[18px]" />
      </a>
      {showTip && (
        <div className="gx-github-tip" role="tooltip">
          About rank and score algorithm: see it here.
        </div>
      )}
    </div>
  );
}

function Sidebar({
  onShowCommunity,
  onTopicSelect,
}: {
  onShowCommunity: () => void;
  onTopicSelect: (topic: string) => void;
}) {
  const { data } = useQuery({
    queryKey: ["stats"],
    queryFn: getStats,
    staleTime: 30_000,
  });

  return (
    <aside className="gx-sidebar">
      <section>
        <div className="gx-side-label">
          My topics
          <span className="gx-disabled-control" title="Adding custom topics is not implemented yet">
            <PlusIcon size={13} />
          </span>
        </div>
        <div className="space-y-1">
          {SIDEBAR_TOPICS.map(([topic, count, on]) => (
            <button
              key={topic}
              type="button"
              onClick={() => onTopicSelect(topic)}
              className={`gx-topic-row ${on ? "is-on" : ""}`}
              title={`Search ${topic}`}
            >
              <span className="gx-topic-dot" />
              <span className="min-w-0 flex-1 truncate text-left">{topic}</span>
              <span className="gx-topic-count">{count}</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <div className="gx-side-label">Tuning</div>
        <div className="px-1 py-1">
          <div className="mb-1 flex justify-between text-[11px] text-[var(--gx-muted)]">
            <span>Mostly mine</span>
            <span>Wider net</span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value="38"
            disabled
            className="gx-range-disabled"
            title="Personal ranking mix is planned but not implemented yet"
            aria-label="Personal ranking mix is planned but not implemented yet"
          />
          <p className="mt-2 text-[11px] leading-relaxed text-[var(--gx-muted)]">
            Ranking mix control is planned, but not wired to the backend yet.
          </p>
        </div>
      </section>

      <section>
        <div className="gx-side-label">Corpus</div>
        <div className="grid grid-cols-2 gap-2">
          <div className="gx-mini-stat">
            <strong>{data?.items.toLocaleString() ?? "..."}</strong>
            <span>items</span>
          </div>
          <div className="gx-mini-stat">
            <strong>{data?.sources.toLocaleString() ?? "..."}</strong>
            <span>sources</span>
          </div>
        </div>
      </section>

      <section>
        <div className="gx-side-label">My lists</div>
        <div className="space-y-1">
          {[
            ["Reading", "14"],
            ["Cite later", "8"],
            ["Sent to team", "3"],
          ].map(([name, count]) => (
            <button
              key={name}
              type="button"
              className="gx-topic-row"
              disabled
              title={`${name} list is not implemented yet`}
            >
              <BookmarkIcon size={13} />
              <span className="min-w-0 flex-1 truncate text-left">{name}</span>
              <span className="gx-topic-count">{count}</span>
            </button>
          ))}
        </div>
      </section>

      <button type="button" className="gx-contribute-cta" onClick={onShowCommunity}>
        <PlusIcon size={14} />
        <span>Contribute a source</span>
      </button>
    </aside>
  );
}

export default function App() {
  const [showSources, setShowSources] = useState(false);
  const [showCommunity, setShowCommunity] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        focusAsk();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function selectTopic(topic: string) {
    navigate("/");
    window.setTimeout(() => askHotpot(topic), 50);
  }

  return (
    <div className="gx-app">
      <header className="gx-topbar">
        <Link to="/" className="gx-brand" aria-label="Hotpot home">
          <span className="gx-brand-dot">H</span>
          <span>Hotpot</span>
        </Link>

        <nav className="gx-nav hidden md:flex" aria-label="Primary">
          <NavLink to="/" end className={({ isActive }) => `gx-nav-link ${isActive ? "is-active" : ""}`}>
            <FlameIcon size={14} />
            Hot
          </NavLink>
          <NavLink to="/security" className={({ isActive }) => `gx-nav-link ${isActive ? "is-active" : ""}`}>
            <ShieldIcon size={14} />
            Security
          </NavLink>
        </nav>

        <button type="button" className="gx-ask-pill" onClick={focusAsk}>
          <SparklesIcon size={15} />
          <span>Ask Hotpot - describe what you want...</span>
          <kbd>⌘K</kbd>
        </button>

        <HeaderRight
          onShowCommunity={() => setShowCommunity(true)}
          onShowSources={() => setShowSources(true)}
        />
      </header>

      <nav className="gx-mobile-nav md:hidden" aria-label="Mobile primary">
        <NavLink to="/" end className={({ isActive }) => `gx-nav-link ${isActive ? "is-active" : ""}`}>
          <FlameIcon size={14} />
          Hot
        </NavLink>
        <NavLink to="/security" className={({ isActive }) => `gx-nav-link ${isActive ? "is-active" : ""}`}>
          <ShieldIcon size={14} />
          Security
        </NavLink>
        <button type="button" className="gx-nav-link" onClick={focusAsk}>
          <SearchIcon size={14} />
          Ask
        </button>
      </nav>

      <div className="gx-layout">
        <Sidebar
          onShowCommunity={() => setShowCommunity(true)}
          onTopicSelect={selectTopic}
        />
        <main className="gx-main">
          <Outlet />
        </main>
      </div>

      {showCommunity && <CommunityModal onClose={() => setShowCommunity(false)} />}
      {showSources && <SourcesDrawer onClose={() => setShowSources(false)} />}
      <ConsentBanner />
    </div>
  );
}
