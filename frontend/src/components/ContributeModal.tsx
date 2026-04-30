import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  classifyContribute,
  commitContribute,
  ContributeError,
  listCategories,
  type CategoryCandidate,
  type ClassifyResult,
  type ContributeResult,
} from "../api";

type Step =
  | { kind: "input" }
  | { kind: "classifying"; url: string; stage: "fetching" | "extracting" | "classifying" }
  | { kind: "review"; data: ClassifyResult }
  | { kind: "committing"; data: ClassifyResult; chosen: string }
  | { kind: "done"; result: ContributeResult; chosen: string }
  | { kind: "error"; message: string; hint?: string };

const PENDING_KEY = "hotpot.pending-contributions";

interface PendingEntry {
  data: ClassifyResult;
  ts: number; // unix ms when classified
}

function loadPending(): PendingEntry[] {
  try {
    const raw = window.localStorage.getItem(PENDING_KEY);
    if (!raw) return [];
    const v = JSON.parse(raw);
    if (!Array.isArray(v)) return [];
    return v.filter(
      (e) => e?.data?.url && e?.data?.title && Array.isArray(e?.data?.candidates),
    );
  } catch {
    return [];
  }
}

function savePending(entries: PendingEntry[]) {
  window.localStorage.setItem(PENDING_KEY, JSON.stringify(entries));
}

function upsertPending(data: ClassifyResult) {
  const entries = loadPending().filter((e) => e.data.url !== data.url);
  entries.unshift({ data, ts: Date.now() });
  savePending(entries.slice(0, 10)); // cap queue size
}

function dropPending(url: string) {
  savePending(loadPending().filter((e) => e.data.url !== url));
}

export default function ContributeModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<Step>({ kind: "input" });
  const [urlInput, setUrlInput] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [pending, setPending] = useState<PendingEntry[]>(loadPending);
  const qc = useQueryClient();

  const cats = useQuery({
    queryKey: ["categories"],
    queryFn: listCategories,
    staleTime: 60_000,
  });

  const classify = useMutation({
    mutationFn: classifyContribute,
    onMutate: (url) => {
      setStep({ kind: "classifying", url, stage: "fetching" });
      // Visual progress staging while the single backend call runs.
      const t1 = setTimeout(
        () => setStep((s) => (s.kind === "classifying" ? { ...s, stage: "extracting" } : s)),
        700,
      );
      const t2 = setTimeout(
        () => setStep((s) => (s.kind === "classifying" ? { ...s, stage: "classifying" } : s)),
        1500,
      );
      return { timers: [t1, t2] };
    },
    onSuccess: (data) => {
      if (data.duplicate) {
        setStep({
          kind: "done",
          result: {
            ok: true,
            duplicate: true,
            item_id: data.item_id ?? "",
            title: data.title,
            content_type: data.content_type,
            topics: data.primary_category ? [data.primary_category] : [],
            tags: data.tags,
          },
          chosen: data.primary_category ?? "",
        });
      } else {
        upsertPending(data);
        setPending(loadPending());
        setStep({ kind: "review", data });
        setCustomCategory("");
      }
    },
    onError: (e: Error) => {
      const msg = e instanceof ContributeError ? e.message : e.message;
      const hint = e instanceof ContributeError ? e.hint : undefined;
      setStep({ kind: "error", message: msg, hint });
    },
    onSettled: (_d, _e, _v, ctx) => {
      ctx?.timers?.forEach(clearTimeout);
    },
  });

  const commit = useMutation({
    mutationFn: commitContribute,
    onSuccess: (result, vars) => {
      dropPending(vars.url);
      setPending(loadPending());
      setStep({ kind: "done", result, chosen: vars.category ?? "" });
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["years"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (e: Error) => {
      const msg = e instanceof ContributeError ? e.message : e.message;
      const hint = e instanceof ContributeError ? e.hint : undefined;
      setStep({ kind: "error", message: msg, hint });
    },
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function startReview(entry: PendingEntry) {
    setStep({ kind: "review", data: entry.data });
    setCustomCategory("");
  }

  function discardPending(url: string) {
    dropPending(url);
    setPending(loadPending());
    if (step.kind === "review" && step.data.url === url) {
      setStep({ kind: "input" });
    }
  }

  function submitClassify() {
    const v = urlInput.trim();
    if (!v) return;
    classify.mutate(v);
  }

  function submitCommit(chosenCategory: string) {
    if (step.kind !== "review") return;
    const d = step.data;
    setStep({ kind: "committing", data: d, chosen: chosenCategory });
    commit.mutate({
      url: d.url,
      title: d.title,
      excerpt: d.excerpt,
      category: chosenCategory,
      candidates: d.candidates,
      content_type: d.content_type,
      tags: d.tags,
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/50 px-4 py-6 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-2xl bg-white shadow-xl border border-slate-200 my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <Header step={step} onClose={onClose} />
        <div className="px-6 py-4 space-y-3">
          {step.kind === "input" && (
            <InputStep
              urlInput={urlInput}
              onChange={setUrlInput}
              onSubmit={submitClassify}
              isPending={classify.isPending}
              pending={pending}
              onResume={startReview}
              onDiscard={discardPending}
            />
          )}
          {step.kind === "classifying" && <ClassifyingStep stage={step.stage} url={step.url} />}
          {step.kind === "review" && (
            <ReviewStep
              data={step.data}
              customCategory={customCategory}
              setCustomCategory={setCustomCategory}
              existingCategories={cats.data ?? []}
              onSubmit={submitCommit}
              onDiscard={() => discardPending(step.data.url)}
              isPending={commit.isPending}
            />
          )}
          {step.kind === "committing" && (
            <p className="text-sm text-slate-600">Saving as <strong>{step.chosen}</strong>…</p>
          )}
          {step.kind === "done" && <DoneStep step={step} onAnother={() => {
            setUrlInput("");
            setStep({ kind: "input" });
          }} />}
          {step.kind === "error" && <ErrorStep msg={step.message} hint={step.hint} onBack={() => setStep({ kind: "input" })} />}
        </div>
        <Footer step={step} onClose={onClose} />
      </div>
    </div>
  );
}

function Header({ step, onClose }: { step: Step; onClose: () => void }) {
  const titles: Record<Step["kind"], string> = {
    input: "Contribute a source",
    classifying: "Classifying…",
    review: "Review & confirm category",
    committing: "Saving…",
    done: "Done",
    error: "Something went wrong",
  };
  return (
    <div className="flex items-start justify-between px-6 pt-5 pb-3 border-b border-slate-100">
      <div>
        <h2 className="text-lg font-bold text-slate-900">{titles[step.kind]}</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Qwen reads your URL, ranks candidate categories, and you confirm.
        </p>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="text-slate-400 hover:text-slate-700 text-2xl leading-none"
        aria-label="Close"
      >
        ×
      </button>
    </div>
  );
}

function Footer({ step, onClose }: { step: Step; onClose: () => void }) {
  return (
    <div className="flex items-center justify-end gap-2 px-6 pb-5 pt-2">
      <button
        type="button"
        onClick={onClose}
        className="text-sm text-slate-600 hover:text-slate-900 px-3 py-2"
      >
        {step.kind === "review" || step.kind === "classifying"
          ? "Close (resume later)"
          : "Close"}
      </button>
    </div>
  );
}

function InputStep({
  urlInput,
  onChange,
  onSubmit,
  isPending,
  pending,
  onResume,
  onDiscard,
}: {
  urlInput: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  isPending: boolean;
  pending: PendingEntry[];
  onResume: (e: PendingEntry) => void;
  onDiscard: (url: string) => void;
}) {
  return (
    <>
      <input
        type="url"
        value={urlInput}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSubmit();
        }}
        placeholder="https://example.com/some-article"
        className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm
                   focus:outline-none focus:ring-2 focus:ring-brand-amber"
        autoFocus
      />
      <p className="text-xs text-slate-500">
        We must end up with a record of <strong>title</strong>, <strong>url</strong>,{" "}
        <strong>content</strong>, and <strong>category</strong>. Good fits: a research
        paper page, a lab/company blog post, a news article, an OSS release.
      </p>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onSubmit}
          disabled={!urlInput.trim() || isPending}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark text-white
                     px-4 py-2 text-sm font-medium hover:bg-black disabled:opacity-50
                     disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "Classifying…" : "Classify"}
        </button>
      </div>

      {pending.length > 0 && (
        <div className="pt-3 mt-2 border-t border-slate-100">
          <p className="text-xs font-medium text-slate-700 mb-1.5">
            Drafts ({pending.length})
            <span className="ml-1 font-normal text-slate-400">
              — classified but not yet saved
            </span>
          </p>
          <ul className="space-y-1.5">
            {pending.map((p) => (
              <li key={p.data.url}
                  className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => onResume(p)}
                  className="flex-1 text-left truncate text-blue-600 hover:underline"
                  title={p.data.url}
                >
                  {p.data.title}
                </button>
                <span className="text-slate-400 tabular-nums whitespace-nowrap">
                  {relativeTime(p.ts)}
                </span>
                <button
                  type="button"
                  onClick={() => onDiscard(p.data.url)}
                  className="text-slate-400 hover:text-red-600"
                  title="Discard"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function ClassifyingStep({
  stage,
  url,
}: {
  stage: "fetching" | "extracting" | "classifying";
  url: string;
}) {
  const stages: { key: typeof stage; label: string }[] = [
    { key: "fetching", label: "Fetching the page" },
    { key: "extracting", label: "Extracting title & excerpt" },
    { key: "classifying", label: "Asking Qwen for categories" },
  ];
  const idx = stages.findIndex((s) => s.key === stage);
  return (
    <div>
      <p className="text-xs text-slate-500 mb-3 truncate" title={url}>{url}</p>
      <ol className="space-y-2">
        {stages.map((s, i) => {
          const done = i < idx;
          const active = i === idx;
          return (
            <li key={s.key} className="flex items-center gap-2 text-sm">
              <span
                className={`inline-flex w-5 h-5 items-center justify-center rounded-full text-[11px] font-bold ${
                  done
                    ? "bg-emerald-500 text-white"
                    : active
                    ? "bg-brand-amber text-brand-dark"
                    : "bg-slate-200 text-slate-500"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className={done ? "text-slate-500" : active ? "text-slate-900 font-medium" : "text-slate-400"}>
                {s.label}
                {active && <span className="ml-1 animate-pulse">…</span>}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="text-[11px] text-slate-500 mt-3 italic">
        Closing this dialog is fine — when you reopen it, you'll find your
        in-progress submission under "Drafts".
      </p>
    </div>
  );
}

function ReviewStep({
  data,
  customCategory,
  setCustomCategory,
  existingCategories,
  onSubmit,
  onDiscard,
  isPending,
}: {
  data: ClassifyResult;
  customCategory: string;
  setCustomCategory: (s: string) => void;
  existingCategories: { category: string; count: number }[];
  onSubmit: (chosen: string) => void;
  onDiscard: () => void;
  isPending: boolean;
}) {
  const candidates = data.candidates;
  const [picked, setPicked] = useState<string>(candidates[0]?.category ?? "Other");

  const finalCategory = customCategory.trim() || picked;
  const isNewCategory = useMemo(() => {
    const known = new Set(existingCategories.map((c) => c.category.toLowerCase()));
    return finalCategory && !known.has(finalCategory.toLowerCase());
  }, [finalCategory, existingCategories]);

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
        <p className="text-[11px] uppercase tracking-wide text-slate-500">title</p>
        <p className="text-sm font-medium text-slate-900">{data.title}</p>
        <p className="text-[11px] uppercase tracking-wide text-slate-500 mt-2">url</p>
        <a
          href={data.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:underline break-all"
        >
          {data.url}
        </a>
        {data.excerpt && (
          <>
            <p className="text-[11px] uppercase tracking-wide text-slate-500 mt-2">content</p>
            <p className="text-xs text-slate-700 line-clamp-3">{data.excerpt}</p>
          </>
        )}
      </div>

      <div>
        <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
          Pick a category — Qwen ranked these{" "}
          <span className="text-slate-400">
            (c1, c2 from the curated list · c3 is open / free-form)
          </span>
        </p>
        <div className="space-y-1.5">
          {candidates.map((c, i) => (
            <label
              key={c.category}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer text-sm ${
                picked === c.category && !customCategory
                  ? "border-amber-400 bg-amber-50"
                  : "border-slate-200 hover:bg-slate-50"
              }`}
            >
              <input
                type="radio"
                name="category"
                value={c.category}
                checked={picked === c.category && !customCategory}
                onChange={() => {
                  setPicked(c.category);
                  setCustomCategory("");
                }}
                className="accent-brand-dark"
              />
              <span className="text-[10px] uppercase tracking-wide text-slate-400 w-5">
                c{i + 1}
              </span>
              <span className="font-medium text-slate-900 flex-1">{c.category}</span>
              {c.open && (
                <span className="text-[10px] font-semibold uppercase tracking-wide
                                 text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded">
                  open
                </span>
              )}
              <span className="text-xs text-slate-400 tabular-nums">
                {Math.round(c.confidence * 100)}%
              </span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
          …or propose a new category
        </p>
        <input
          type="text"
          value={customCategory}
          onChange={(e) => setCustomCategory(e.target.value)}
          placeholder="e.g. Distributed-Systems / DevOps / …"
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:ring-2 focus:ring-brand-amber"
        />
        {isNewCategory && (
          <p className="text-[11px] text-amber-700 mt-1">
            This will create a new category “<strong>{finalCategory}</strong>”.
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={onDiscard}
          className="text-xs text-slate-500 hover:text-red-600 underline underline-offset-2"
        >
          discard
        </button>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => onSubmit(finalCategory)}
          disabled={!finalCategory || isPending}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark text-white
                     px-4 py-2 text-sm font-medium hover:bg-black disabled:opacity-50
                     disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? "Saving…" : `Save as ${finalCategory || "?"}`}
        </button>
      </div>
    </div>
  );
}

function DoneStep({
  step,
  onAnother,
}: {
  step: Extract<Step, { kind: "done" }>;
  onAnother: () => void;
}) {
  const r = step.result;
  return (
    <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 space-y-1 text-xs">
      <p className="font-medium text-emerald-800">
        {r.duplicate ? "✓ Already in the feed" : "✓ Added to the feed"}
      </p>
      <p className="text-emerald-900 font-medium">{r.title}</p>
      <p className="text-emerald-700">
        <span className="opacity-70">category:</span>{" "}
        {step.chosen || "(unspecified)"}
      </p>
      <div className="pt-2">
        <button
          type="button"
          onClick={onAnother}
          className="text-xs text-emerald-800 underline underline-offset-2 hover:text-emerald-900"
        >
          Submit another URL
        </button>
      </div>
    </div>
  );
}

function ErrorStep({
  msg,
  hint,
  onBack,
}: {
  msg: string;
  hint?: string;
  onBack: () => void;
}) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-xs space-y-1">
      <p className="font-medium text-red-800">⚠ {msg}</p>
      {hint && <p className="text-red-700">{hint}</p>}
      <div className="pt-2">
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-red-700 underline underline-offset-2 hover:text-red-900"
        >
          Back
        </button>
      </div>
    </div>
  );
}

function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}
