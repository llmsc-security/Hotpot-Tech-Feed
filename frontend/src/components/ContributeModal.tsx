import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { contributeUrl, ContributeError, type ContributeResult } from "../api";

export default function ContributeModal({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [errHint, setErrHint] = useState<string | null>(null);
  const [result, setResult] = useState<ContributeResult | null>(null);
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: contributeUrl,
    onSuccess: (r) => {
      setErrMsg(null);
      setErrHint(null);
      setResult(r);
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["years"] });
    },
    onError: (e: Error) => {
      setResult(null);
      if (e instanceof ContributeError) {
        setErrMsg(e.message);
        setErrHint(e.hint ?? null);
      } else {
        setErrMsg(e.message);
        setErrHint(null);
      }
    },
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function submit() {
    const v = url.trim();
    if (!v || mut.isPending) return;
    setResult(null);
    setErrMsg(null);
    setErrHint(null);
    mut.mutate(v);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl bg-white shadow-xl border border-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-6 pt-5 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Contribute a source</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Paste a URL — Qwen reads it, classifies it, and adds it to the feed.
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

        <div className="px-6 py-4 space-y-3">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder="https://example.com/some-article"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm
                       focus:outline-none focus:ring-2 focus:ring-brand-amber"
            autoFocus
          />

          <p className="text-xs text-slate-500">
            Good fits: a research paper page, a lab/company blog post, a news article,
            or an OSS release announcement. The URL must be publicly reachable HTML
            (no login wall, no PDF).
          </p>

          {errMsg && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs">
              <p className="font-medium text-red-800">⚠ {errMsg}</p>
              {errHint && <p className="text-red-700 mt-0.5">{errHint}</p>}
            </div>
          )}

          {result && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs space-y-1">
              <p className="font-medium text-emerald-800">
                {result.duplicate ? "✓ Already in the feed" : "✓ Added to the feed"}
              </p>
              <p className="text-emerald-900 font-medium">{result.title}</p>
              <p className="text-emerald-700">
                <span className="opacity-70">type:</span> {result.content_type}
                {result.topics.length > 0 && (
                  <>
                    {" · "}
                    <span className="opacity-70">topics:</span>{" "}
                    {result.topics.join(", ")}
                  </>
                )}
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 pb-5 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-slate-600 hover:text-slate-900 px-3 py-2"
          >
            Close
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!url.trim() || mut.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand-dark text-white
                       px-4 py-2 text-sm font-medium hover:bg-black disabled:opacity-50
                       disabled:cursor-not-allowed transition-colors"
          >
            {mut.isPending ? "Submitting…" : "Submit"}
          </button>
        </div>
      </div>
    </div>
  );
}
