// The declarative game engine: state, conditions, branching, scoring and lifecycle events.
// Pure TypeScript with no DOM access, so it can be tested on its own and reused by any renderer.

import {
  RUNTIME_CAPABILITIES, SUPPORTED_API_VERSIONS,
  type Activity, type AnswerValue, type Answers, type Condition, type Effect, type FeedbackItem, type Field,
  type GameEvent, type GameEventType, type Manifest, type Screen, type Vars,
} from "./types";

export class GameError extends Error {}

export function isAnswered(v: AnswerValue): boolean {
  if (v === undefined || v === null) return false;
  if (typeof v === "string") return v.trim() !== "";
  if (Array.isArray(v)) return v.length > 0;
  return true; // numbers and booleans (an unticked checkbox is a valid answer: false)
}

/**
 * Evaluate a condition. `score` is the share of scored questions answered as the book suggests
 * (0–1), or null when there are none yet; it's only needed for API 1.1 score conditions.
 */
export function evaluate(cond: Condition | undefined, answers: Answers, vars: Vars, visited: Set<string>,
                         score: number | null = null): boolean {
  if (!cond) return true;
  if ("all" in cond) return cond.all.every((c) => evaluate(c, answers, vars, visited, score));
  if ("any" in cond) return cond.any.some((c) => evaluate(c, answers, vars, visited, score));
  if ("not" in cond) return !evaluate(cond.not, answers, vars, visited, score);
  if ("score" in cond) {
    if (score === null) return false;
    const o = cond.score;
    return (o.gt === undefined || score > o.gt) && (o.gte === undefined || score >= o.gte)
        && (o.lt === undefined || score < o.lt) && (o.lte === undefined || score <= o.lte);
  }
  if ("visited" in cond && !("field" in cond) && !("var" in cond)) return visited.has(cond.visited);
  const value: AnswerValue = "field" in cond ? answers[(cond as { field: string }).field] : vars[(cond as { var: string }).var];
  const c = cond as Record<string, unknown>;
  if ("answered" in c) return isAnswered(value) === c.answered;
  if (!isAnswered(value) && !("notEquals" in c)) return false;
  if ("equals" in c) return Array.isArray(value) ? value.length === 1 && value[0] === c.equals : value === c.equals;
  if ("notEquals" in c) return Array.isArray(value) ? !(value.length === 1 && value[0] === c.notEquals) : value !== c.notEquals;
  if ("in" in c) return (c.in as unknown[]).includes(value as never);
  if ("includes" in c) return Array.isArray(value) ? value.includes(c.includes as string) : false;
  if ("first" in c) return Array.isArray(value) && value[0] === c.first;
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return false;
  if ("gt" in c) return n > (c.gt as number);
  if ("gte" in c) return n >= (c.gte as number);
  if ("lt" in c) return n < (c.lt as number);
  if ("lte" in c) return n <= (c.lte as number);
  return false;
}

export function applyEffects(vars: Vars, effects: Effect[] | undefined): Vars {
  if (!effects?.length) return vars;
  const out = { ...vars };
  for (const e of effects) {
    if (!(e.var in out)) continue;
    if (e.set !== undefined) out[e.var] = e.set;
    else if (e.add !== undefined && typeof out[e.var] === "number") out[e.var] = (out[e.var] as number) + e.add;
  }
  return out;
}

/** Structural checks the runtime needs before it can safely run a package (the builder validates fully). */
export function checkPackage(manifest: Manifest, activity: Activity): string[] {
  const errors: string[] = [];
  if (!SUPPORTED_API_VERSIONS.includes(manifest?.apiVersion)) errors.push(`Unsupported game.json apiVersion ${manifest?.apiVersion}`);
  if (!SUPPORTED_API_VERSIONS.includes(activity?.apiVersion)) errors.push(`Unsupported activity.json apiVersion ${activity?.apiVersion}`);
  if (errors.length) return errors;
  for (const cap of manifest.requiredCapabilities ?? []) {
    if (!(RUNTIME_CAPABILITIES as readonly string[]).includes(cap)) errors.push(`Unsupported capability ${cap}`);
  }
  const ids = new Set(activity.screens?.map((s) => s.id));
  if (!activity.screens?.length) errors.push("No screens");
  if (!ids.has(activity.start)) errors.push(`Start screen ${activity.start} not found`);
  for (const s of activity.screens ?? []) {
    for (const t of targets(s)) if (!ids.has(t)) errors.push(`Screen ${s.id} goes to unknown screen ${t}`);
    if (s.type !== "completion" && !s.next) errors.push(`Screen ${s.id} has no next screen`);
  }
  return errors;
}

export function targets(s: Screen): string[] {
  if (!s.next) return [];
  if (typeof s.next === "string") return [s.next];
  return [...(s.next.rules ?? []).map((r) => r.goto), s.next.default];
}

/** Placeholders in reader-facing text (API 1.1): {{answer:fieldId}} and {{var:name}}. */
export const PLACEHOLDER = /\{\{\s*(answer|var)\s*:\s*([A-Za-z0-9_-]+)\s*\}\}/g;

function shuffled<T>(items: T[], random: () => number): T[] {
  const a = [...items];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export interface Snapshot { screenId: string; vars: Vars; answers: Answers }

export interface SessionState {
  status: "idle" | "running" | "complete" | "exited" | "error";
  screenId: string;
  answers: Answers;
  vars: Vars;
  visited: string[];
  history: Snapshot[];
  viewedPerspectives: Record<string, string[]>;
  feedback: FeedbackItem[] | null;
  /** Option order per field for this play (shuffled fields and rankings). */
  order: Record<string, string[]>;
}

type Listener = (e: GameEvent) => void;

/**
 * One play-through of a game. Rendering code calls the methods; every change is reported through
 * lifecycle events (see docs/game-developer/lifecycle-and-events.md).
 */
export class GameSession {
  readonly manifest: Manifest;
  readonly activity: Activity;
  state: SessionState;
  private screens: Map<string, Screen>;
  private listeners: Listener[] = [];
  private random: () => number;

  constructor(manifest: Manifest, activity: Activity, listener?: Listener, random: () => number = Math.random) {
    this.manifest = manifest;
    this.activity = activity;
    this.random = random;
    if (listener) this.listeners.push(listener);
    this.screens = new Map((activity?.screens ?? []).map((s) => [s.id, s]));
    this.state = this.fresh();
  }

  on(fn: Listener): () => void {
    this.listeners.push(fn);
    return () => { this.listeners = this.listeners.filter((l) => l !== fn); };
  }

  private emit(type: GameEventType, detail: Record<string, unknown> = {}): void {
    const e: GameEvent = {
      type, gameId: this.manifest?.id, gameVersion: this.manifest?.version, apiVersion: this.manifest?.apiVersion,
      screenId: this.state?.screenId || undefined, timestamp: Date.now(), detail,
    };
    for (const l of this.listeners) {
      try { l(e); } catch { /* a listener must never break the game */ }
    }
  }

  private fresh(): SessionState {
    const vars: Vars = {};
    for (const [k, v] of Object.entries(this.activity?.variables ?? {})) vars[k] = v.initial;
    return { status: "idle", screenId: "", answers: {}, vars, visited: [], history: [], viewedPerspectives: {}, feedback: null, order: {} };
  }

  /** Validate and announce readiness. Returns false (and emits "error") if the package can't run. */
  init(): boolean {
    this.emit("init", { apiVersion: this.manifest?.apiVersion });
    const errors = checkPackage(this.manifest, this.activity);
    if (errors.length) {
      this.state.status = "error";
      this.emit("error", { code: "invalid-package", messages: errors, recoverable: false });
      return false;
    }
    this.emit("ready", { screens: this.activity.screens.length });
    return true;
  }

  start(): void {
    this.state = this.fresh();
    this.state.status = "running";
    this.emit("start", {});
    this.enter(this.activity.start, null);
  }

  get screen(): Screen {
    const s = this.screens.get(this.state.screenId);
    if (!s) throw new GameError(`Unknown screen ${this.state.screenId}`);
    return s;
  }

  private enter(id: string, from: string | null): void {
    const s = this.screens.get(id);
    if (!s) return this.fail("missing-screen", `Screen ${id} does not exist`);
    this.state.screenId = id;
    this.state.feedback = null;
    if (!this.state.visited.includes(id)) this.state.visited.push(id);
    this.state.vars = applyEffects(this.state.vars, s.effects);
    // Rankings start in the shown order, so they always have an answer the reader can rearrange.
    for (const f of s.fields ?? []) {
      if (f.type === "ranking" && !Array.isArray(this.state.answers[f.id])) {
        this.state.answers = { ...this.state.answers, [f.id]: this.optionOrder(f) };
      }
    }
    this.emit("screenchange", { from, to: id, screenType: s.type });
    this.emit("progress", this.progress());
    if (s.type === "completion") {
      const visited = new Set(this.state.visited);
      const fb = (s.feedback ?? []).filter((r) => evaluate(r.when, this.state.answers, this.state.vars, visited, this.scoreFraction()))
        .map((r) => ({ text: r.text, tone: r.tone ?? "neutral" }));
      this.state.feedback = fb.length ? fb : null;
      this.state.status = "complete";
      this.emit("complete", { score: this.score(), path: [...this.state.visited] });
    }
  }

  private fail(code: string, message: string): void {
    this.state.status = "error";
    this.emit("error", { code, messages: [message], recoverable: true });
  }

  visibleFields(screen: Screen = this.screen): Field[] {
    const visited = new Set(this.state.visited);
    return (screen.fields ?? []).filter((f) => evaluate(f.showIf, this.state.answers, this.state.vars, visited, this.scoreFraction()));
  }

  setAnswer(fieldId: string, value: AnswerValue): void {
    const field = this.screen.fields?.find((f) => f.id === fieldId);
    if (!field) return;
    this.state.answers = { ...this.state.answers, [fieldId]: value };
    this.state.feedback = null;
    // Written answers are never included in events, so nothing a reader types can leave the page.
    const written = field.type === "text" || field.type === "textarea";
    this.emit("input", { fieldId, fieldType: field.type, answered: isAnswered(value), ...(written ? {} : { value }) });
  }

  viewPerspective(perspectiveId: string): void {
    const seen = this.state.viewedPerspectives[this.state.screenId] ?? [];
    if (!seen.includes(perspectiveId)) {
      this.state.viewedPerspectives = { ...this.state.viewedPerspectives, [this.state.screenId]: [...seen, perspectiveId] };
    }
    this.emit("input", { perspectiveId });
  }

  /** Field ids that block continuing, with a reason each. */
  problems(): { fieldId: string; message: string }[] {
    const s = this.screen;
    const out: { fieldId: string; message: string }[] = [];
    if (s.type === "perspective" && s.requireAllPerspectives) {
      const seen = this.state.viewedPerspectives[s.id] ?? [];
      const missing = (s.perspectives ?? []).filter((p) => !seen.includes(p.id));
      if (missing.length) out.push({ fieldId: "", message: `Read every view first: ${missing.map((p) => p.label).join(", ")}.` });
    }
    for (const f of this.visibleFields(s)) {
      const v = this.state.answers[f.id];
      const count = Array.isArray(v) ? v.length : 0;
      if (f.required && (!isAnswered(v) || (f.type === "checkbox" && v !== true))) {
        out.push({ fieldId: f.id, message: f.type === "checkbox" ? "Tick this box to continue." : "This one needs an answer." });
      } else if (Array.isArray(v) && f.minSelected && count < f.minSelected && (f.required || count > 0)) {
        out.push({ fieldId: f.id, message: `Choose at least ${f.minSelected}.` });
      } else if (Array.isArray(v) && f.maxSelected && count > f.maxSelected) {
        out.push({ fieldId: f.id, message: `Choose no more than ${f.maxSelected}.` });
      } else if (typeof v === "string" && f.maxLength && v.length > f.maxLength) {
        out.push({ fieldId: f.id, message: `Keep it under ${f.maxLength} characters.` });
      }
    }
    return out;
  }

  /** Feedback for the current screen's answers: option feedback, then screen rules. */
  collectFeedback(): FeedbackItem[] {
    const s = this.screen;
    const items: FeedbackItem[] = [];
    const visited = new Set(this.state.visited);
    for (const f of this.visibleFields(s)) {
      const v = this.state.answers[f.id];
      const chosen = Array.isArray(v) ? v : [v];
      for (const o of f.options ?? []) {
        if (chosen.includes(o.value) && o.feedback) items.push({ text: o.feedback, tone: o.tone ?? "neutral", fieldId: f.id });
      }
    }
    for (const r of s.feedback ?? []) {
      if (evaluate(r.when, this.state.answers, this.state.vars, visited, this.scoreFraction())) items.push({ text: r.text, tone: r.tone ?? "neutral" });
    }
    return items;
  }

  /**
   * Continue from the current screen. On a form with feedback the first call shows the feedback
   * (returns "feedback"); the next call moves on. Returns "blocked" if answers are missing.
   */
  next(): "blocked" | "feedback" | "moved" | "complete" {
    if (this.state.status !== "running") return "complete";
    const s = this.screen;
    if (this.problems().length) return "blocked";
    if (s.type === "form" && this.state.feedback === null) {
      // Hidden fields don't count as answers.
      const visible = new Set(this.visibleFields(s).map((f) => f.id));
      const answers = { ...this.state.answers };
      for (const f of s.fields ?? []) if (!visible.has(f.id)) delete answers[f.id];
      this.state.answers = answers;
      const fb = this.collectFeedback();
      this.emit("submit", { fields: [...visible] });
      if (fb.length) {
        this.state.feedback = fb;
        this.emit("feedback", { count: fb.length, tones: fb.map((f) => f.tone) });
        return "feedback";
      }
    }
    // Apply option effects on leaving a form, then follow the first matching rule.
    let vars = this.state.vars;
    if (s.type === "form") {
      for (const f of this.visibleFields(s)) {
        const v = this.state.answers[f.id];
        const chosen = Array.isArray(v) ? v : [v];
        for (const o of f.options ?? []) if (chosen.includes(o.value)) vars = applyEffects(vars, o.effects);
      }
    }
    this.state.history.push({ screenId: s.id, vars: this.state.vars, answers: this.state.answers });
    this.state.vars = vars;
    const to = this.resolveNext(s);
    this.enter(to, s.id);
    return (this.state.status as SessionState["status"]) === "complete" ? "complete" : "moved";
  }

  resolveNext(s: Screen): string {
    if (!s.next) throw new GameError(`Screen ${s.id} has no next screen`);
    if (typeof s.next === "string") return s.next;
    const visited = new Set(this.state.visited);
    for (const r of s.next.rules ?? []) if (evaluate(r.when, this.state.answers, this.state.vars, visited, this.scoreFraction())) return r.goto;
    return s.next.default;
  }

  canGoBack(): boolean {
    return this.state.history.length > 0 && this.state.status === "running";
  }

  back(): void {
    const prev = this.state.history.pop();
    if (!prev) return;
    const from = this.state.screenId;
    this.state.vars = prev.vars;
    this.state.answers = prev.answers;
    this.state.screenId = prev.screenId;
    this.state.feedback = null;
    this.state.status = "running";
    this.emit("back", { from, to: prev.screenId });
    this.emit("screenchange", { from, to: prev.screenId, screenType: this.screen.type });
    this.emit("progress", this.progress());
  }

  restart(): void {
    this.emit("restart", {});
    this.start();
  }

  exit(reason: "exit" | "skip" = "exit"): void {
    const was = this.state.status;
    this.state.status = "exited";
    this.emit(reason, { from: this.state.screenId || null, completed: was === "complete" });
  }

  /** Fraction of the way through: steps taken / (steps taken + shortest remaining path). */
  progress(): { step: number; remaining: number; fraction: number } {
    const step = this.state.history.length + 1;
    const remaining = this.distanceToEnd(this.state.screenId);
    const fraction = remaining === 0 ? 1 : step / (step + remaining);
    return { step, remaining, fraction: Math.round(fraction * 100) / 100 };
  }

  private distanceToEnd(from: string): number {
    const queue: [string, number][] = [[from, 0]];
    const seen = new Set<string>();
    while (queue.length) {
      const [id, d] = queue.shift()!;
      const s = this.screens.get(id);
      if (!s || seen.has(id)) continue;
      if (s.type === "completion") return d;
      seen.add(id);
      for (const t of targets(s)) queue.push([t, d + 1]);
    }
    return 0;
  }

  /** Knowledge-check score over scored fields the reader saw. Null when the game has no scored fields. */
  score(): { correct: number; total: number } | null {
    let correct = 0, total = 0;
    const seenScreens = new Set([...this.state.history.map((h) => h.screenId), this.state.screenId]);
    for (const s of this.activity.screens) {
      if (!seenScreens.has(s.id)) continue;
      for (const f of s.fields ?? []) {
        if (!f.scored || !(f.id in this.state.answers)) continue;
        total += 1;
        const right = (f.options ?? []).filter((o) => o.correct).map((o) => o.value).sort();
        const v = this.state.answers[f.id];
        const given = (Array.isArray(v) ? [...v] : [v]).sort();
        if (right.length === given.length && right.every((x, i) => x === given[i])) correct += 1;
      }
    }
    return total ? { correct, total } : null;
  }

  /** Share of scored questions answered as the book suggests (0–1), or null if none were answered. */
  scoreFraction(): number | null {
    const s = this.score();
    return s ? s.correct / s.total : null;
  }

  /** Option values in the order to show them this play (shuffled once per play when the field asks). */
  optionOrder(field: Field): string[] {
    const values = (field.options ?? []).map((o) => o.value);
    if (!field.shuffle) return values;
    if (!this.state.order[field.id]) this.state.order = { ...this.state.order, [field.id]: shuffled(values, this.random) };
    return this.state.order[field.id];
  }

  /** How an answer reads in text: option labels, numbers, Yes/No, or what was typed. */
  answerText(fieldId: string): string {
    const field = this.activity.screens.flatMap((s) => s.fields ?? []).find((f) => f.id === fieldId);
    const v = this.state.answers[fieldId];
    if (!field || !isAnswered(v)) return "";
    const label = (val: string) => field.options?.find((o) => o.value === val)?.label ?? val;
    if (Array.isArray(v)) return field.type === "ranking" ? v.map((x, i) => `${i + 1}. ${label(x)}`).join("; ") : v.map(label).join(", ");
    if (typeof v === "boolean") return v ? "Yes" : "No";
    if (typeof v === "number") return String(v);
    return field.options ? label(v as string) : (v as string);
  }

  /** Fill in {{answer:…}} and {{var:…}} placeholders (API 1.1). Unanswered placeholders read "—". */
  text(s: string | undefined): string {
    if (!s) return "";
    return s.replace(PLACEHOLDER, (_m, kind: string, name: string) => {
      const value = kind === "answer" ? this.answerText(name) : String(this.state.vars[name] ?? "");
      return value === "" ? "—" : value;
    });
  }

  /** The "Save my notes" file (API 1.1): answers and takeaways as plain text. Built on the reader's device. */
  notes(): string {
    const s = this.screen;
    const lines = [this.manifest.title, "=".repeat(Math.min(60, this.manifest.title.length)), ""];
    const summary = this.summary();
    if (summary.length) {
      lines.push("Your answers", "");
      for (const a of summary) lines.push(a.label, `  ${a.answer.replace(/\n/g, "\n  ")}`, "");
    }
    for (const f of this.state.feedback ?? []) lines.push(this.text(f.text), "");
    if (s.takeaways?.length) {
      lines.push("To take with you", "");
      for (const t of s.takeaways) lines.push(`- ${this.text(t)}`);
      lines.push("");
    }
    lines.push(`From the activity "${this.manifest.title}" in the book (chapter ${this.manifest.chapter}).`);
    return lines.join("\n");
  }

  /** Answers shown back on completion screens. Kept in memory only. */
  summary(): { label: string; answer: string; written: boolean }[] {
    const out: { label: string; answer: string; written: boolean }[] = [];
    for (const s of this.activity.screens) {
      for (const f of s.fields ?? []) {
        const v = this.state.answers[f.id];
        if (!isAnswered(v)) continue;
        const answer = this.answerText(f.id);
        out.push({ label: f.label, answer, written: f.type === "text" || f.type === "textarea" });
      }
    }
    return out;
  }
}
