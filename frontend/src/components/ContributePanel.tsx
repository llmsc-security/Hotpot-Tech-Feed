import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  contributeUrl,
  ContributeError,
  recategorizeContribution,
  type CategoryCandidate,
  type ContributeResult,
} from "../api";

type Stage =
  | { kind: "idle" }
  | { kind: "submitting"; url: string; phase: "fetching" | "classifying" | "saving" }
  | {
      kind: "done";
      result: ContributeResult & { candidates?: CategoryCandidate[] };
      picked: string;
    }
  | { kind: "error"; message: string; hint?: string };

interface ContributeWithCandidates extends ContributeResult {
  candidates?: CategoryCandidate[];
  primary_category?: string | null;
}

export default function ContributePanel() {
  const [url, setUrl] = useState("");
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const qc = useQueryClient();

  const submit = useMutation({
    mutationFn: contributeUrl,
    onMutate: (u) => {
      setStage({ kind: "submitting", url: u, phase: "fetching" });
      const t1 = setTimeout(
        () =>
          setStage((s) =>
            s.kind === "submitting" ? { ...s, phase: "classifying" } : s,
          ),
        500,
      );
      const t2 = setTimeout(
        () =>
          setStage((s) =>
            s.kind === "submitting" ? { ...s, phase: "saving" } : s,
          ),
        1100,
      );
      return { timers: [t1, t2] };
    },
    onSuccess: (result) => {
      const r = result as ContributeWithCandidates;
      setStage({
        kind: "done",
        result: r,
        picked:
          r.primary_category ??
          r.candidates?.[0]?.category ??
          r.topics?.[0] ??
          "",
      });
      setUrl("");
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["years"] });
      qc.invalidateQueries({ queryKey: ["categories"] });
      qc.invalidateQueries({ queryKey: ["community"] });
    },
    onError: (e: Error) => {
      const msg = e instanceof ContributeError ? e.message : e.message;
      const hint = e instanceof ContributeError ? e.hint : undefined;
      setStage({ kind: "error", message: msg, hint });
    },
    onSettled: (_d, _e, _v, ctx) => {
      ctx?.timers?.forEach(clearTimeout);
    },
  });

  const recategorize = useMutation({
    mutationFn: ({ itemId, category }: { itemId: string; category: string }) =>
      recategorizeContribution(itemId, category),
    onSuccess: (r) => {
      setStage((s) =>
        s.kind === "done"
          ? { ...s, picked: r.primary_category }
          : s,
      );
      qc.invalidateQueries({ queryKey: ["categories"] });
      qc.invalidateQueries({ queryKey: ["community"] });
    },
  });

  function onSubmit() {
    const v = url.trim();
    if (!v) return;
    submit.mutate(v);
  }

  return (
    <section className="rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-rose-50 p-5 shadow-sm">
      <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
        <div>
          <h2 className="font-serif text-xl font-bold text-slate-900">
            ＋ Share a URL
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Paste a paper / blog / news URL — Qwen classifies and it lands in
            the feed instantly. No approval queue.
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSubmit();
          }}
          placeholder="https://example.com/some-article"
          disabled={stage.kind === "submitting"}
          className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm
                     focus:outline-none focus:ring-2 focus:ring-brand-amber
                     disabled:bg-slate-100"
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={!url.trim() || stage.kind === "submitting"}
          className="rounded-lg bg-brand-dark text-white px-4 py-2 text-sm font-medium
                     hover:bg-black disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors"
        >
          {stage.kind === "submitting" ? "Submitting…" : "Submit"}
        </button>
      </div>

      {stage.kind === "submitting" && <ProgressStrip phase={stage.phase} url={stage.url} />}

      {stage.kind === "done" && (
        <DoneBlock
          stage={stage}
          onRecategorize={(cat) =>
            recategorize.mutate({ itemId: stage.result.item_id, category: cat })
          }
          recategorizing={recategorize.isPending}
        />
      )}

      {stage.kind === "error" && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs">
          <p className="font-medium text-red-800">⚠ {stage.message}</p>
          {stage.hint && <p className="text-red-700">{stage.hint}</p>}
          <button
            type="button"
            className="text-red-700 underline underline-offset-2 hover:text-red-900 mt-1"
            onClick={() => setStage({ kind: "idle" })}
          >
            try another URL
          </button>
        </div>
      )}
    </section>
  );
}

function ProgressStrip({
  phase,
  url,
}: {
  phase: "fetching" | "classifying" | "saving";
  url: string;
}) {
  const steps: { key: typeof phase; label: string }[] = [
    { key: "fetching", label: "Fetching the page" },
    { key: "classifying", label: "Asking Qwen for categories" },
    { key: "saving", label: "Saving to feed" },
  ];
  const idx = steps.findIndex((s) => s.key === phase);
  return (
    <div className="mt-3 text-xs">
      <p className="text-slate-500 mb-1.5 truncate" title={url}>
        {url}
      </p>
      <ol className="flex gap-2">
        {steps.map((s, i) => (
          <li
            key={s.key}
            className={`flex items-center gap-1 px-2 py-0.5 rounded-full ${
              i < idx
                ? "bg-emerald-100 text-emerald-800"
                : i === idx
                ? "bg-amber-100 text-amber-900 font-medium"
                : "bg-slate-100 text-slate-400"
            }`}
          >
            <span aria-hidden>{i < idx ? "✓" : i === idx ? "•" : "○"}</span>
            {s.label}
          </li>
        ))}
      </ol>
    </div>
  );
}

function DoneBlock({
  stage,
  onRecategorize,
  recategorizing,
}: {
  stage: Extract<Stage, { kind: "done" }>;
  onRecategorize: (cat: string) => void;
  recategorizing: boolean;
}) {
  const r = stage.result;
  const candidates = r.candidates ?? [];
  const [custom, setCustom] = useState("");

  return (
    <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 space-y-2 text-xs">
      <p className="font-medium text-emerald-800">
        {r.duplicate ? "✓ Already in the feed" : "✓ Added to the feed"}
      </p>
      <p className="text-emerald-900 font-medium">{r.title}</p>
      <p className="text-emerald-700">
        category: <strong>{stage.picked || "(unspecified)"}</strong>
      </p>

      {candidates.length > 0 && !r.duplicate && (
        <div className="pt-1">
          <p className="text-[11px] uppercase tracking-wide text-emerald-700 mb-1">
            not right? pick another
          </p>
          <div className="flex flex-wrap gap-1.5">
            {candidates.map((c, i) => (
              <button
                key={c.category}
                type="button"
                disabled={recategorizing}
                onClick={() => onRecategorize(c.category)}
                className={`px-2 py-0.5 rounded-full text-[11px] border transition-colors ${
                  stage.picked === c.category
                    ? "bg-emerald-700 text-white border-emerald-700"
                    : "bg-white text-slate-700 border-slate-300 hover:border-slate-400"
                }`}
              >
                <span className="opacity-50 mr-1">c{i + 1}</span>
                {c.category}
                {c.open && <span className="ml-1 opacity-60">·open</span>}
                <span className="ml-1 opacity-50 tabular-nums">
                  {Math.round(c.confidence * 100)}%
                </span>
              </button>
            ))}
          </div>
          <div className="flex gap-1.5 mt-1.5">
            <input
              type="text"
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="…or type a new category"
              className="flex-1 border border-slate-300 rounded px-2 py-1 text-[11px]
                         focus:outline-none focus:ring-1 focus:ring-brand-amber"
            />
            <button
              type="button"
              disabled={!custom.trim() || recategorizing}
              onClick={() => {
                onRecategorize(custom.trim());
                setCustom("");
              }}
              className="text-[11px] px-2 py-1 rounded bg-slate-700 text-white
                         hover:bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
