// Renders a Book Builder game package with accessible, keyboard-friendly form controls.
// All game logic lives in engine.ts; this file only draws the current state.
import { Component, useCallback, useEffect, useId, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { GameSession, isAnswered } from "./engine";
import { Markdown } from "./markdown";
import type { Activity, AnswerValue, Field, GameEvent, ImageRef, Manifest, Option, Screen } from "./types";

export interface GameRunnerProps {
  manifest: Manifest;
  activity: Activity;
  /** URL prefix for the package's files, ending in "/". */
  assetBase: string;
  onEvent?: (e: GameEvent) => void;
  /** Label and handler for leaving the activity (for example, back to the chapter). */
  exitLabel?: string;
  onExit?: () => void;
  /** Start immediately instead of showing the introduction card. */
  autoStart?: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  "knowledge-check": "Knowledge check", scenario: "Scenario", reflection: "Reflection",
  practice: "Practice", sorting: "Sorting", explainer: "Explainer",
};

export function GameRunner(props: GameRunnerProps) {
  return (
    <ErrorBoundary manifest={props.manifest} onEvent={props.onEvent}>
      <Runner {...props} />
    </ErrorBoundary>
  );
}

function Runner({ manifest, activity, assetBase, onEvent, exitLabel, onExit, autoStart }: GameRunnerProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [started, setStarted] = useState(false);
  const [left, setLeft] = useState(false);

  const session = useMemo(() => new GameSession(manifest, activity), [manifest, activity]);
  const ready = useMemo(() => {
    const off = session.on((e) => {
      onEvent?.(e);
      rootRef.current?.dispatchEvent(new CustomEvent("bookbuilder:game", { detail: e, bubbles: true }));
    });
    const ok = session.init();
    return { ok, off };
  }, [session, onEvent]);
  useEffect(() => () => ready.off(), [ready]);

  const focusHeading = useCallback(() => requestAnimationFrame(() => headingRef.current?.focus()), []);
  const begin = () => { session.start(); setStarted(true); setErrors({}); rerender(); focusHeading(); };
  useEffect(() => { if (autoStart && ready.ok && !started) begin(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ready.ok) {
    return (
      <div className="pg pg-error" role="alert" ref={rootRef}>
        <p><strong>This activity couldn't load.</strong> The rest of the page still works, and you can skip it.</p>
      </div>
    );
  }

  const leave = (reason: "exit" | "skip") => {
    session.exit(reason);
    setLeft(true);
    setStarted(false);
    onExit?.();
  };

  if (left) {
    return (
      <div className="pg pg-left" ref={rootRef}>
        <p>You left the activity. <button type="button" className="pg-link" onClick={() => { setLeft(false); begin(); }}>Start it again</button></p>
      </div>
    );
  }

  if (!started) {
    return (
      <div className="pg" ref={rootRef}>
        <div className="pg-intro">
          <p className="pg-kicker">{TYPE_LABELS[manifest.activityType] ?? "Activity"}{manifest.estimatedMinutes ? ` · about ${manifest.estimatedMinutes} min` : ""}</p>
          <h3 className="pg-title">{manifest.title}</h3>
          <p>{manifest.description}</p>
          {manifest.contentWarnings.length > 0 && (
            <p className="pg-warning"><strong>Content note:</strong> {manifest.contentWarnings.join("; ")}.</p>
          )}
          <p className="pg-muted">{manifest.accessibility.summary} Nothing you type is saved or sent anywhere.</p>
          <div className="pg-actions">
            <button type="button" className="pg-button pg-primary" onClick={begin}>Start activity</button>
            <button type="button" className="pg-button" onClick={() => leave("skip")}>Skip activity</button>
          </div>
        </div>
      </div>
    );
  }

  const screen = session.screen;
  const fields = session.visibleFields();
  const progress = session.progress();
  const feedback = session.state.feedback;
  const complete = session.state.status === "complete";

  const setAnswer = (id: string, v: AnswerValue) => {
    session.setAnswer(id, v);
    if (errors[id]) setErrors((e) => { const n = { ...e }; delete n[id]; return n; });
    rerender();
  };

  const onContinue = () => {
    const problems = session.problems();
    if (problems.length) {
      const map: Record<string, string> = {};
      for (const p of problems) map[p.fieldId || "_screen"] = p.message;
      setErrors(map);
      setNotice("Some answers need attention.");
      const first = problems.find((p) => p.fieldId)?.fieldId;
      requestAnimationFrame(() => {
        const el = first ? rootRef.current?.querySelector<HTMLElement>(`[data-field="${first}"] input, [data-field="${first}"] select, [data-field="${first}"] textarea`) : null;
        el?.focus();
      });
      return;
    }
    setErrors({});
    setNotice("");
    const result = session.next();
    rerender();
    if (result === "moved" || result === "complete") focusHeading();
  };

  return (
    <div className="pg" ref={rootRef}>
      <div className="pg-top">
        <span className="pg-kicker">{manifest.title}</span>
        <button type="button" className="pg-link" onClick={() => leave("exit")}>{exitLabel ?? "Leave activity"}</button>
      </div>
      <div className="pg-progress" role="progressbar" aria-label="Activity progress" aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={Math.round(progress.fraction * 100)}>
        <span style={{ width: `${Math.round(progress.fraction * 100)}%` }} />
      </div>
      <section className={`pg-screen pg-${screen.type}`} aria-labelledby={`pg-h-${manifest.id}`}>
        <h3 id={`pg-h-${manifest.id}`} className="pg-title" tabIndex={-1} ref={headingRef}>{session.text(screen.title)}</h3>
        <Markdown text={session.text(screen.body)} />
        {screen.image && <Img image={screen.image} manifest={manifest} assetBase={assetBase} />}
        {screen.type === "perspective" && <Perspectives screen={screen} session={session} rerender={rerender}
                                                        manifest={manifest} assetBase={assetBase} error={errors._screen} />}
        {screen.type === "form" && (
          <form className="pg-form" noValidate onSubmit={(e) => { e.preventDefault(); onContinue(); }}>
            {fields.map((f) => (
              <FieldView key={f.id} field={f} options={session.optionOrder(f).map((v) => f.options!.find((o) => o.value === v)!)}
                         value={session.state.answers[f.id]} error={errors[f.id]}
                         disabled={feedback !== null} onChange={(v) => setAnswer(f.id, v)} />
            ))}
            <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
          </form>
        )}
        <div className="pg-feedback" aria-live="polite">
          {feedback?.map((f, i) => (
            <div key={i} className={`pg-fb pg-fb-${f.tone}`}><Markdown text={session.text(f.text)} /></div>
          ))}
        </div>
        {complete && <Completion screen={screen} session={session} />}
        <p className="pg-visually-hidden" aria-live="assertive">{notice}</p>
      </section>
      <div className="pg-actions">
        {complete ? (
          <>
            <button type="button" className="pg-button pg-primary" onClick={() => { session.restart(); setErrors({}); rerender(); focusHeading(); }}>Restart</button>
            {onExit && <button type="button" className="pg-button" onClick={() => leave("exit")}>{exitLabel ?? "Done"}</button>}
          </>
        ) : (
          <>
            {session.canGoBack() && (
              <button type="button" className="pg-button" onClick={() => { session.back(); setErrors({}); rerender(); focusHeading(); }}>Back</button>
            )}
            <button type="button" className="pg-button pg-primary" onClick={onContinue}>
              {screen.type === "form" && feedback === null && hasFeedback(screen) ? "Check" : (screen.continueLabel ?? "Continue")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function hasFeedback(s: Screen): boolean {
  return Boolean(s.feedback?.length || s.fields?.some((f) => f.options?.some((o) => o.feedback)));
}

function assetUrl(base: string, path: string): string {
  return base + path.split("/").map(encodeURIComponent).join("/");
}

function Img({ image, manifest, assetBase }: { image: ImageRef; manifest: Manifest; assetBase: string }) {
  const declared = manifest.assets.find((a) => a.path === image.asset);
  if (!declared || declared.type !== "image") return null;
  return <img className="pg-image" src={assetUrl(assetBase, image.asset)} alt={image.alt ?? declared.alt ?? ""} loading="lazy" />;
}

function Perspectives({ screen, session, rerender, manifest, assetBase, error }: {
  screen: Screen; session: GameSession; rerender: () => void; manifest: Manifest; assetBase: string; error?: string;
}) {
  const ps = screen.perspectives ?? [];
  const [active, setActive] = useState(ps[0]?.id);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const uid = useId();
  useEffect(() => { if (ps[0]) session.viewPerspective(ps[0].id); rerender(); }, [screen.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const select = (i: number) => {
    const p = ps[(i + ps.length) % ps.length];
    setActive(p.id);
    session.viewPerspective(p.id);
    rerender();
    tabRefs.current[(i + ps.length) % ps.length]?.focus();
  };
  const seen = session.state.viewedPerspectives[screen.id] ?? [];
  return (
    <div className="pg-perspectives">
      <div role="tablist" aria-label="Perspectives" className="pg-tabs">
        {ps.map((p, i) => (
          <button key={p.id} role="tab" type="button" id={`${uid}-tab-${p.id}`} aria-controls={`${uid}-panel-${p.id}`}
                  aria-selected={active === p.id} tabIndex={active === p.id ? 0 : -1} ref={(el) => { tabRefs.current[i] = el; }}
                  className="pg-tab" onClick={() => select(i)}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowRight") { e.preventDefault(); select(i + 1); }
                    if (e.key === "ArrowLeft") { e.preventDefault(); select(i - 1); }
                    if (e.key === "Home") { e.preventDefault(); select(0); }
                    if (e.key === "End") { e.preventDefault(); select(ps.length - 1); }
                  }}>
            {p.label}{seen.includes(p.id) ? <span className="pg-visually-hidden"> (read)</span> : null}
          </button>
        ))}
      </div>
      {ps.map((p) => (
        <div key={p.id} role="tabpanel" id={`${uid}-panel-${p.id}`} aria-labelledby={`${uid}-tab-${p.id}`}
             hidden={active !== p.id} className="pg-panel" tabIndex={0}>
          <Markdown text={session.text(p.body)} />
          {p.image && <Img image={p.image} manifest={manifest} assetBase={assetBase} />}
        </div>
      ))}
      {error && <p className="pg-error-text" role="alert">{error}</p>}
    </div>
  );
}

function FieldView({ field: f, options, value, error, disabled, onChange }: {
  field: Field; options: Option[]; value: AnswerValue; error?: string; disabled: boolean; onChange: (v: AnswerValue) => void;
}) {
  const id = useId();
  const [moved, setMoved] = useState("");
  const helpId = f.help ? `${id}-help` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [helpId, errId].filter(Boolean).join(" ") || undefined;
  const common = { "aria-invalid": error ? true : undefined, "aria-describedby": describedBy, disabled };
  const help = <>
    {f.help ? <p id={helpId} className="pg-help">{f.help}</p> : null}
    {f.hint ? <details className="pg-hint"><summary>Need a hint?</summary><p>{f.hint}</p></details> : null}
  </>;
  const err = error ? <p id={errId} className="pg-error-text">{error}</p> : null;
  const req = f.required ? <span className="pg-req"> (required)</span> : <span className="pg-opt"> (optional)</span>;
  const arr = Array.isArray(value) ? value : [];
  const toggle = (v: string, multi: boolean) => {
    if (!multi) return onChange(v);
    onChange(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  };

  if (f.type === "ranking") {
    const order = arr.length ? arr : options.map((o) => o.value);
    const label = (v: string) => f.options!.find((o) => o.value === v)?.label ?? v;
    const move = (i: number, d: number) => {
      const j = i + d;
      if (j < 0 || j >= order.length) return;
      const next = [...order];
      [next[i], next[j]] = [next[j], next[i]];
      onChange(next);
      setMoved(`${label(order[i])} moved to position ${j + 1} of ${order.length}.`);
      requestAnimationFrame(() => document.getElementById(`${id}-${order[i]}-${d < 0 ? "up" : "down"}`)?.focus());
    };
    return (
      <fieldset className="pg-field pg-ranking" data-field={f.id} aria-describedby={describedBy}>
        <legend>{f.label}</legend>
        {help}
        <p className="pg-help">Use the arrow buttons to put these in order, most important first.</p>
        <ol className="pg-rank-list">
          {order.map((v, i) => {
            const o = f.options!.find((x) => x.value === v);
            return (
              <li key={v} className="pg-rank-item">
                <span className="pg-rank-pos" aria-hidden="true">{i + 1}</span>
                <span className="pg-option-text">
                  <span className="pg-option-label">{o?.label ?? v}</span>
                  {o?.description && <span className="pg-option-desc">{o.description}</span>}
                </span>
                <span className="pg-rank-buttons">
                  <button type="button" id={`${id}-${v}-up`} className="pg-button pg-small" disabled={disabled || i === 0}
                          aria-label={`Move ${o?.label ?? v} up`} onClick={() => move(i, -1)}>↑</button>
                  <button type="button" id={`${id}-${v}-down`} className="pg-button pg-small" disabled={disabled || i === order.length - 1}
                          aria-label={`Move ${o?.label ?? v} down`} onClick={() => move(i, 1)}>↓</button>
                </span>
              </li>
            );
          })}
        </ol>
        <p className="pg-visually-hidden" aria-live="polite">{moved}</p>
        {err}
      </fieldset>
    );
  }
  if (f.type === "single-choice" || f.type === "multiple-choice" || f.type === "cards") {
    const multi = f.type === "multiple-choice" || (f.type === "cards" && !!f.multiple);
    return (
      <fieldset className={`pg-field pg-${f.type}`} data-field={f.id} aria-describedby={describedBy} aria-invalid={error ? true : undefined}>
        <legend>{f.label}{req}</legend>
        {help}
        <div className={f.type === "cards" ? "pg-cards" : "pg-options"}>
          {options.map((o) => {
            const checked = multi ? arr.includes(o.value) : value === o.value;
            return (
              <label key={o.value} className={`pg-option${checked ? " pg-checked" : ""}`}>
                <input type={multi ? "checkbox" : "radio"} name={`${id}-${f.id}`} value={o.value} checked={checked}
                       disabled={disabled} onChange={() => toggle(o.value, multi)} />
                <span className="pg-option-text">
                  <span className="pg-option-label">{o.label}</span>
                  {o.description && <span className="pg-option-desc">{o.description}</span>}
                </span>
              </label>
            );
          })}
        </div>
        {err}
      </fieldset>
    );
  }
  if (f.type === "checkbox") {
    return (
      <div className="pg-field pg-checkbox" data-field={f.id}>
        <label className="pg-option">
          <input type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} {...common} />
          <span className="pg-option-label">{f.label}{f.required ? req : null}</span>
        </label>
        {help}{err}
      </div>
    );
  }
  const label = <label htmlFor={id}>{f.label}{req}</label>;
  if (f.type === "dropdown") {
    return (
      <div className="pg-field" data-field={f.id}>
        {label}{help}
        <select id={id} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value || undefined)} {...common}>
          <option value="">Choose…</option>
          {f.options!.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {err}
      </div>
    );
  }
  if (f.type === "slider") {
    const v = typeof value === "number" ? value : (typeof f.initial === "number" ? f.initial : f.min!);
    const text = `${v}${v === f.min && f.minLabel ? ` (${f.minLabel})` : ""}${v === f.max && f.maxLabel ? ` (${f.maxLabel})` : ""}`;
    return (
      <div className="pg-field pg-slider" data-field={f.id}>
        {label}{help}
        <div className="pg-slider-row">
          {f.minLabel && <span aria-hidden="true" className="pg-muted">{f.minLabel}</span>}
          <input id={id} type="range" min={f.min} max={f.max} step={f.step ?? 1} value={v} aria-valuetext={text}
                 onChange={(e) => onChange(Number(e.target.value))} {...common} />
          {f.maxLabel && <span aria-hidden="true" className="pg-muted">{f.maxLabel}</span>}
          <output htmlFor={id} className="pg-slider-value">{isAnswered(value) ? v : "–"}</output>
        </div>
        {err}
      </div>
    );
  }
  if (f.type === "textarea") {
    return (
      <div className="pg-field" data-field={f.id}>
        {label}{help}
        <textarea id={id} rows={4} maxLength={f.maxLength} placeholder={f.placeholder} value={(value as string) ?? ""}
                  autoComplete="off" onChange={(e) => onChange(e.target.value)} {...common} />
        <p className="pg-help">Not saved or sent anywhere.</p>
        {err}
      </div>
    );
  }
  return (
    <div className="pg-field" data-field={f.id}>
      {label}{help}
      <input id={id} type="text" maxLength={f.maxLength} placeholder={f.placeholder} value={(value as string) ?? ""}
             autoComplete="off" onChange={(e) => onChange(e.target.value)} {...common} />
      {err}
    </div>
  );
}

function Completion({ screen, session }: { screen: Screen; session: GameSession }) {
  const score = screen.showScore ? session.score() : null;
  const summary = screen.showSummary ? session.summary() : [];
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const text = summary.map((s) => `${s.label}\n${s.answer}`).join("\n\n");
  // The notes file is made here, in the browser, and handed straight to the reader's device.
  const saveNotes = () => {
    const url = URL.createObjectURL(new Blob([session.notes()], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = `${session.manifest.id}-my-notes.txt`;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setSaved(true);
  };
  return (
    <div className="pg-completion">
      {screen.takeaways && screen.takeaways.length > 0 && (
        <div className="pg-takeaways">
          <h4>To take with you</h4>
          <ul>{screen.takeaways.map((t, i) => <li key={i}>{session.text(t)}</li>)}</ul>
        </div>
      )}
      {score && <p className="pg-score">Knowledge questions: {score.correct} of {score.total} matched the book.</p>}
      {summary.length > 0 && (
        <div className="pg-summary">
          <h4>Your answers</h4>
          <dl>
            {summary.map((s, i) => (<div key={i}><dt>{s.label}</dt><dd>{s.answer}</dd></div>))}
          </dl>
          <p className="pg-help">These stay on this page only and disappear when you leave or restart.</p>
          {typeof navigator !== "undefined" && navigator.clipboard && !screen.allowSaveNotes && (
            <button type="button" className="pg-button" onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}>
              {copied ? "Copied" : "Copy my answers"}
            </button>
          )}
        </div>
      )}
      {screen.allowSaveNotes && (
        <div className="pg-save">
          <button type="button" className="pg-button" onClick={saveNotes}>{saved ? "Saved to your device" : "Save my notes"}</button>
          <p className="pg-help">Downloads a text file of your answers{screen.takeaways?.length ? " and the takeaways" : ""} to this device. Nothing is sent anywhere.</p>
        </div>
      )}
    </div>
  );
}

class ErrorBoundary extends Component<{ children: ReactNode; manifest: Manifest; onEvent?: (e: GameEvent) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) {
    const m = this.props.manifest;
    this.props.onEvent?.({ type: "error", gameId: m?.id, gameVersion: m?.version, apiVersion: m?.apiVersion,
      timestamp: Date.now(), detail: { code: "render-error", messages: [String(error?.message ?? error)], recoverable: false } });
  }
  render() {
    if (this.state.failed) {
      return <div className="pg pg-error" role="alert"><p><strong>This activity stopped working.</strong> You can keep reading; the activity is optional.</p></div>;
    }
    return this.props.children;
  }
}
