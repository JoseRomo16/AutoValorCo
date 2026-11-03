"use client";

/**
 * The service worker's visible side: registration on load, and the update notice.
 *
 * The notice is a small bar at the bottom corner, never a modal: the visitor can keep
 * reading and update when it suits them. Ignoring it does not strand anyone on an old
 * version either, because pages are fetched network first (ADR 0007): a plain reload
 * already brings the new HTML and the new hashed assets.
 */

import { useEffect, useSyncExternalStore } from "react";

import { useLang } from "@/components/LanguageProvider";
import { copy } from "@/lib/i18n";
import {
  applyUpdate,
  getServerSnapshot,
  getSnapshot,
  promptInstall,
  registerServiceWorker,
  subscribe,
  watchInstallPrompt,
} from "@/lib/pwa";

export function usePwa() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function ServiceWorker() {
  const { t } = useLang();
  const { updateReady } = usePwa();

  useEffect(() => {
    watchInstallPrompt();
    // `next dev` serves no sw.js, and a worker caching a dev server is a debugging trap.
    if (process.env.NODE_ENV === "production") void registerServiceWorker();
  }, []);

  if (!updateReady) return null;
  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto flex max-w-md items-center justify-between gap-4 rounded-md border border-line-strong bg-surface px-4 py-3 text-sm text-ink shadow-lg sm:inset-x-auto sm:right-6"
    >
      <span>{t(copy.pwa.updateReady)}</span>
      <button
        type="button"
        onClick={applyUpdate}
        className="inline-flex min-h-10 items-center rounded-md bg-accent px-3 font-semibold text-accent-ink"
      >
        {t(copy.pwa.updateAction)}
      </button>
    </div>
  );
}

/** "Instalar la app", only while the browser offers to install; a footer link, not a modal. */
export function InstallButton({ className = "" }: { className?: string }) {
  const { t } = useLang();
  const { install } = usePwa();
  if (!install) return null;
  return (
    <button
      type="button"
      onClick={() => void promptInstall()}
      className={`text-left text-muted underline-offset-4 hover:text-ink hover:underline ${className}`}
    >
      {t(copy.pwa.install)}
    </button>
  );
}
