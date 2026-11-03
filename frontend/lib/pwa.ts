/**
 * The installable app's client side: registering the service worker, noticing a new
 * version, and holding Chrome's install prompt for the footer button.
 *
 * External stores read with `useSyncExternalStore`, like the language and the theme, so a
 * component that shows the update notice or the install button renders from one source.
 */

/** The `beforeinstallprompt` event, which TypeScript's DOM types do not describe yet. */
export type InstallPromptEvent = Event & { prompt: () => Promise<void> };

type State = { updateReady: boolean; install: InstallPromptEvent | null };

let state: State = { updateReady: false, install: null };
const listeners = new Set<() => void>();
let waiting: ServiceWorker | null = null;

function set(next: Partial<State>): void {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const getSnapshot = (): State => state;
const SERVER_STATE: State = { updateReady: false, install: null };
export const getServerSnapshot = (): State => SERVER_STATE;

/** A new worker is installed and waiting while an older one controls the page. */
function offerUpdate(worker: ServiceWorker | null): void {
  if (!worker || !navigator.serviceWorker.controller) return;
  waiting = worker;
  set({ updateReady: true });
}

/**
 * Register `/sw.js` and watch for new versions.
 *
 * `updateViaCache: "none"` makes the browser skip the HTTP cache when it checks the script,
 * on top of the no-cache header Render sends. The check also runs whenever the tab comes
 * back to the foreground, so a tab left open across a deploy still learns about it.
 */
export async function registerServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  // The emergency build (ADR 0007) says "off": register nothing and remove whatever is
  // there. Without this the page would re-register /sw.js -- by then the emergency worker
  // itself -- every time that worker reloaded it, in a loop.
  if (document.querySelector('meta[name="autovalor-sw"]')?.getAttribute("content") === "off") {
    for (const registration of await navigator.serviceWorker.getRegistrations()) {
      await registration.unregister();
    }
    return;
  }
  const registration = await navigator.serviceWorker.register("/sw.js", {
    scope: "/",
    updateViaCache: "none",
  });
  offerUpdate(registration.waiting);
  registration.addEventListener("updatefound", () => {
    const installing = registration.installing;
    installing?.addEventListener("statechange", () => {
      if (installing.state === "installed") offerUpdate(installing);
    });
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void registration.update();
  });

  // Reload only when the visitor asked for the update. The first install also changes the
  // controller (the worker claims the page), and reloading then would throw away a page
  // the visitor had just started to use.
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!updating) return;
    updating = false;
    window.location.reload();
  });
}

let updating = false;

/** Ask the waiting worker to take over; `controllerchange` above then reloads the page. */
export function applyUpdate(): void {
  if (!waiting) {
    window.location.reload();
    return;
  }
  updating = true;
  waiting.postMessage({ type: "SKIP_WAITING" });
}

/** Keep Chrome's install prompt instead of letting it show its own mini-infobar. */
export function watchInstallPrompt(): void {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    set({ install: event as InstallPromptEvent });
  });
  window.addEventListener("appinstalled", () => set({ install: null }));
}

export async function promptInstall(): Promise<void> {
  const event = state.install;
  if (!event) return;
  set({ install: null });
  await event.prompt();
}
