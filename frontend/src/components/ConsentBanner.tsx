import { useConsent } from "../hooks/useConsent";

export default function ConsentBanner() {
  const { consent, set } = useConsent();
  if (consent !== null) return null;

  return (
    <div
      role="dialog"
      aria-live="assertive"
      aria-label="Search-logging consent"
      className="fixed bottom-3 left-3 right-3 max-h-[calc(100dvh-1.5rem)] overflow-y-auto
                 sm:bottom-4 sm:left-auto sm:right-4 sm:max-w-md
                 z-[60] rounded-xl border border-amber-300 bg-white shadow-2xl
                 px-4 py-3 sm:rounded-2xl sm:px-5 sm:py-4"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-0.5 inline-flex w-6 h-6 shrink-0 items-center justify-center
                     rounded-full bg-amber-100 text-amber-700 font-bold text-sm sm:h-7 sm:w-7 sm:text-base"
        >
          !
        </span>
        <div className="flex-1">
          <h3 className="text-sm font-bold leading-snug text-slate-900">
            Heads up — we’d like to record your searches
          </h3>
          <p className="text-xs text-slate-700 mt-1 leading-relaxed">
            <span className="sm:hidden">
              Search queries can be saved to improve Hotpot. No account, no
              cookies — just the text you type and the filters the LLM extracted.
            </span>
            <span className="hidden sm:inline">
              When you click <span className="font-semibold">Ask</span>, your
              query is sent to a self-hosted Qwen3.5 LLM and saved server-side
              (table <code className="font-mono bg-slate-100 px-1 rounded">search_logs</code>)
              so we can study how people search and improve the agent. No
              account, no cookies — just the text you type and the filters
              the LLM extracted.
            </span>
          </p>
          <p className="text-xs text-slate-500 mt-1.5">
            You can change your mind any time from this banner (clear browser
            storage to bring it back).
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => set("rejected")}
          className="text-xs font-medium text-slate-600 hover:text-slate-900
                     px-3 py-1.5 rounded-lg border border-slate-200 hover:border-slate-300"
        >
          Reject
        </button>
        <button
          type="button"
          onClick={() => set("accepted")}
          className="text-xs font-semibold text-white bg-brand-dark hover:bg-black
                     px-3.5 py-1.5 rounded-lg shadow-sm"
        >
          Accept &amp; record
        </button>
      </div>
    </div>
  );
}
