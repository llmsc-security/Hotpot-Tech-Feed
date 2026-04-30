import { useCallback, useEffect, useState } from "react";

const KEY = "hotpot.search-log-consent";
export type Consent = "accepted" | "rejected" | null;

const EVT = "hotpot:consent-change";

export function useConsent(): {
  consent: Consent;
  set: (v: Exclude<Consent, null>) => void;
  clear: () => void;
} {
  const [consent, setConsent] = useState<Consent>(() => {
    if (typeof window === "undefined") return null;
    const v = window.localStorage.getItem(KEY);
    return v === "accepted" || v === "rejected" ? v : null;
  });

  useEffect(() => {
    function onChange() {
      const v = window.localStorage.getItem(KEY);
      setConsent(v === "accepted" || v === "rejected" ? v : null);
    }
    window.addEventListener(EVT, onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener(EVT, onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);

  const set = useCallback((v: Exclude<Consent, null>) => {
    window.localStorage.setItem(KEY, v);
    window.dispatchEvent(new Event(EVT));
  }, []);

  const clear = useCallback(() => {
    window.localStorage.removeItem(KEY);
    window.dispatchEvent(new Event(EVT));
  }, []);

  return { consent, set, clear };
}
