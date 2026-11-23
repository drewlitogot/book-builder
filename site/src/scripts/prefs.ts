// Reading settings and optional local progress. Everything stays in this browser (localStorage);
// nothing is sent anywhere. Written answers in activities are never stored.
const PREFS = "bookbuilder:prefs";
const PROGRESS = "bookbuilder:progress";
const CALLOUTS = "bookbuilder:callouts";
const DEFAULTS: Record<string, string> = { theme: "system", size: "m", font: "sans", spacing: "normal", motion: "auto" };

type Prefs = Record<string, string | boolean>;
export interface Progress { read: string[]; last?: string; activities: string[] }

function load<T>(key: string, fallback: T): T {
  try { return { ...fallback, ...JSON.parse(localStorage.getItem(key) || "{}") }; } catch { return fallback; }
}
function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage may be blocked */ }
}

export const prefs = (): Prefs => load<Prefs>(PREFS, {});
export const remembering = () => prefs().remember === true;
export const progress = (): Progress => load<Progress>(PROGRESS, { read: [], activities: [] });

export function recordProgress(change: (p: Progress) => void) {
  if (!remembering()) return;
  const p = progress();
  change(p);
  save(PROGRESS, p);
  document.dispatchEvent(new CustomEvent("bookbuilder:progress"));
}

function apply(p: Prefs) {
  const r = document.documentElement;
  for (const k of Object.keys(DEFAULTS)) {
    const v = (p[k] as string) ?? DEFAULTS[k];
    if (k === "theme" && v === "system") delete r.dataset.theme;
    else if (v === DEFAULTS[k] && k !== "theme") delete r.dataset[k];
    else r.dataset[k] = v;
  }
  document.querySelectorAll<HTMLElement>(".seg").forEach((seg) => {
    const key = seg.dataset.pref!;
    const cur = (p[key] as string) ?? DEFAULTS[key];
    seg.querySelectorAll<HTMLButtonElement>("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === cur)));
  });
}

function init() {
  const toggle = document.querySelector<HTMLButtonElement>(".settings-toggle");
  const panel = document.getElementById("settings-panel");
  toggle?.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") !== "true";
    toggle.setAttribute("aria-expanded", String(open));
    panel!.hidden = !open;
    if (open) panel!.querySelector<HTMLButtonElement>("button")?.focus();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel && !panel.hidden) {
      panel.hidden = true;
      toggle?.setAttribute("aria-expanded", "false");
      toggle?.focus();
    }
  });
  document.querySelectorAll<HTMLElement>(".seg").forEach((seg) => {
    seg.addEventListener("click", (e) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      const p = prefs();
      p[seg.dataset.pref!] = b.dataset.value!;
      save(PREFS, p);
      apply(p);
    });
  });
  const remember = document.getElementById("remember-progress") as HTMLInputElement | null;
  if (remember) {
    remember.checked = remembering();
    remember.addEventListener("change", () => {
      const p = prefs();
      p.remember = remember.checked;
      save(PREFS, p);
      if (!remember.checked) { try { localStorage.removeItem(PROGRESS); } catch { /* ignore */ } }
      document.dispatchEvent(new CustomEvent("bookbuilder:progress"));
    });
  }
  document.getElementById("clear-data")?.addEventListener("click", () => {
    try { [PREFS, PROGRESS, CALLOUTS].forEach((k) => localStorage.removeItem(k)); } catch { /* ignore */ }
    apply({});
    if (remember) remember.checked = false;
    const s = document.getElementById("clear-status");
    if (s) s.textContent = "Cleared. Nothing from this site is stored on this device now.";
    document.dispatchEvent(new CustomEvent("bookbuilder:progress"));
  });
  // Record finished activities (only when the reader opted in). Answers are never stored.
  document.addEventListener("bookbuilder:game", (e) => {
    const ev = (e as CustomEvent).detail;
    if (ev?.type === "complete") recordProgress((p) => { if (!p.activities.includes(ev.gameId)) p.activities.push(ev.gameId); });
  });
  apply(prefs());
}

init();
