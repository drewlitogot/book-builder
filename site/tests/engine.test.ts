import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { GameSession, evaluate, checkPackage } from "../src/game/engine";
import type { Activity, GameEvent, Manifest } from "../src/game/types";

const dir = `${process.cwd()}/../tests/fixtures/games/kitchen-sink/`;
const load = () => ({
  manifest: JSON.parse(readFileSync(dir + "game.json", "utf8")) as Manifest,
  activity: JSON.parse(readFileSync(dir + "activity.json", "utf8")) as Activity,
});

function session() {
  const { manifest, activity } = load();
  const events: GameEvent[] = [];
  const s = new GameSession(manifest, activity, (e) => events.push(e));
  expect(s.init()).toBe(true);
  s.start();
  return { s, events };
}

describe("conditions", () => {
  const v = new Set<string>(["a"]);
  it("evaluates field, var, visited and combinators", () => {
    const answers = { x: "teal", n: 7, list: ["a", "b"], t: true };
    expect(evaluate({ field: "x", equals: "teal" }, answers, {}, v)).toBe(true);
    expect(evaluate({ field: "x", in: ["red", "teal"] }, answers, {}, v)).toBe(true);
    expect(evaluate({ field: "list", includes: "b" }, answers, {}, v)).toBe(true);
    expect(evaluate({ field: "n", gte: 7 }, answers, {}, v)).toBe(true);
    expect(evaluate({ field: "n", lt: 7 }, answers, {}, v)).toBe(false);
    expect(evaluate({ field: "missing", answered: false }, answers, {}, v)).toBe(true);
    expect(evaluate({ field: "missing", equals: "x" }, answers, {}, v)).toBe(false);
    expect(evaluate({ var: "p", gt: 1 }, answers, { p: 2 }, v)).toBe(true);
    expect(evaluate({ visited: "a" }, answers, {}, v)).toBe(true);
    expect(evaluate({ all: [{ field: "t", equals: true }, { not: { field: "x", equals: "red" } }] }, answers, {}, v)).toBe(true);
    expect(evaluate({ any: [{ field: "x", equals: "red" }, { field: "n", equals: 7 }] }, answers, {}, v)).toBe(true);
  });
});

describe("GameSession", () => {
  it("emits init, ready, start, screenchange and progress", () => {
    const { s, events } = session();
    expect(events.map((e) => e.type).slice(0, 5)).toEqual(["init", "ready", "start", "screenchange", "progress"]);
    expect(s.screen.id).toBe("intro");
    expect(events[0].gameId).toBe("fixture-kitchen-sink");
  });

  it("hides conditional fields until their condition holds", () => {
    const { s } = session();
    s.next();
    expect(s.visibleFields().map((f) => f.id)).not.toContain("followup");
    s.setAnswer("agree", true);
    expect(s.visibleFields().map((f) => f.id)).toContain("followup");
  });

  it("blocks on required and min-selected fields", () => {
    const { s } = session();
    s.next();
    expect(s.next()).toBe("blocked");
    expect(s.problems().map((p) => p.fieldId)).toContain("color");
    s.setAnswer("color", "teal");
    s.setAnswer("shapes", ["circle", "square", "star"]);
    expect(s.problems().map((p) => p.fieldId)).toEqual(["shapes"]);
  });

  it("shows feedback first, then branches by rule and applies effects", () => {
    const { s, events } = session();
    s.next();
    s.setAnswer("color", "teal");
    s.setAnswer("card", "right");
    s.setAnswer("level", 9);
    expect(s.next()).toBe("feedback");
    expect(s.state.feedback!.map((f) => f.text)).toEqual(["Teal noted.", "You feel very sure."]);
    expect(events.some((e) => e.type === "feedback")).toBe(true);
    expect(s.next()).toBe("moved");
    expect(s.screen.id).toBe("right");
    expect(s.state.vars).toEqual({ points: 2, path: "right" });
  });

  it("takes the default branch, requires all perspectives, and completes with a score", () => {
    const { s, events } = session();
    s.next();
    s.setAnswer("color", "teal");
    s.next(); s.next();
    expect(s.screen.id).toBe("left");
    s.viewPerspective("a");
    expect(s.next()).toBe("blocked");
    s.viewPerspective("b");
    expect(s.next()).toBe("moved");
    s.setAnswer("fact", "four");
    s.next();
    expect(s.next()).toBe("complete");
    expect(s.screen.id).toBe("done-high");
    const done = events.find((e) => e.type === "complete")!;
    expect(done.detail.score).toEqual({ correct: 1, total: 1 });
    expect(s.progress().fraction).toBe(1);
  });

  it("goes back with state restored, and restarts cleanly", () => {
    const { s, events } = session();
    s.next();
    s.setAnswer("color", "violet");
    s.next(); s.next();
    expect(s.state.vars.points).toBe(1);
    s.back();
    expect(s.screen.id).toBe("basics");
    expect(s.state.vars.points).toBe(0);
    s.restart();
    expect(s.screen.id).toBe("intro");
    expect(s.state.answers).toEqual({});
    expect(events.some((e) => e.type === "restart")).toBe(true);
  });

  it("never puts written answers in events", () => {
    const { s, events } = session();
    s.next();
    s.setAnswer("notes", "private words");
    const input = events.filter((e) => e.type === "input").pop()!;
    expect(JSON.stringify(input)).not.toContain("private words");
    expect(input.detail.answered).toBe(true);
  });

  it("reports exit and skip", () => {
    const { s, events } = session();
    s.exit("skip");
    expect(events.pop()!.type).toBe("skip");
    expect(s.state.status).toBe("exited");
  });

  it("rejects packages it can't run, with an error event", () => {
    const { manifest, activity } = load();
    const events: GameEvent[] = [];
    const bad = new GameSession({ ...manifest, apiVersion: "9.0" }, activity, (e) => events.push(e));
    expect(bad.init()).toBe(false);
    expect(events.pop()).toMatchObject({ type: "error", detail: { code: "invalid-package" } });
    expect(checkPackage(manifest, { ...activity, start: "nope" })).toContain("Start screen nope not found");
    expect(checkPackage({ ...manifest, requiredCapabilities: ["webcam"] }, activity)[0]).toMatch(/capability/);
  });
});

describe("API 1.1", () => {
  const tpl = `${process.cwd()}/../docs/game-developer/templates/reflection-package/`;
  const load11 = () => ({
    manifest: JSON.parse(readFileSync(tpl + "game.json", "utf8")) as Manifest,
    activity: JSON.parse(readFileSync(tpl + "activity.json", "utf8")) as Activity,
  });

  it("starts rankings in a stable shuffled order and fills placeholders", () => {
    const { manifest, activity } = load11();
    const s = new GameSession(manifest, activity, undefined, () => 0); // deterministic shuffle
    expect(s.init()).toBe(true);
    s.start();
    expect(s.next()).toBe("moved"); // intro -> rank
    const field = s.screen.fields![0];
    const order = s.state.answers.priorities as string[];
    expect(order).toHaveLength(5);
    expect(s.optionOrder(field)).toEqual(order); // same order every time this play
    s.setAnswer("priorities", ["space", ...order.filter((v) => v !== "space")]);
    expect(s.next()).toBe("moved");
    expect(s.text(s.screen.title)).toBe("Your top choice: 1. Having time and space of your own; 2. " +
      s.answerText("priorities").split("; 2. ")[1]);
    s.setAnswer("firmness", "unsure");
    expect(s.next()).toBe("feedback");
    expect(s.state.feedback!.map((f) => f.tone)).toEqual(["positive", "neutral"]); // "first" + equals rules
    expect(s.next()).toBe("complete");
    const notes = s.notes();
    expect(notes).toContain("To take with you");
    expect(notes).toContain("How firm is your first choice?");
    expect(s.text("{{answer:why}} / {{var:none}}")).toBe("— / —");
  });

  it("evaluates first and score conditions and shows completion results", () => {
    expect(evaluate({ field: "r", first: "a" }, { r: ["a", "b"] }, {}, new Set())).toBe(true);
    expect(evaluate({ field: "r", first: "b" }, { r: ["a", "b"] }, {}, new Set())).toBe(false);
    expect(evaluate({ score: { gte: 0.5 } }, {}, {}, new Set(), 0.5)).toBe(true);
    expect(evaluate({ score: { gte: 0.5 } }, {}, {}, new Set(), null)).toBe(false);

    const { manifest } = load();
    const activity = {
      apiVersion: "1.1", start: "q",
      screens: [
        { id: "q", type: "form", title: "Q", next: "done",
          fields: [{ id: "a", type: "single-choice", label: "A", scored: true,
                     options: [{ value: "y", label: "Y", correct: true }, { value: "n", label: "N" }] }] },
        { id: "done", type: "completion", title: "Done", takeaways: ["Keep {{answer:a}}."],
          feedback: [{ when: { score: { gte: 1 } }, text: "All matched.", tone: "positive" },
                     { when: { score: { lt: 1 } }, text: "Some differ.", tone: "consider" }] },
      ],
    } as Activity;
    const s = new GameSession({ ...manifest, apiVersion: "1.1" }, activity);
    expect(s.init()).toBe(true);
    s.start();
    s.setAnswer("a", "y");
    expect(s.next()).toBe("complete");
    expect(s.state.feedback?.map((f) => f.text)).toEqual(["All matched."]);
    expect(s.text(s.screen.takeaways![0])).toBe("Keep Y.");
    s.restart(); s.setAnswer("a", "n"); s.next();
    expect(s.state.feedback?.map((f) => f.text)).toEqual(["Some differ."]);
  });

  it("runs 1.0 packages unchanged", () => {
    const { manifest, activity } = load();
    expect(manifest.apiVersion).toBe("1.0");
    expect(checkPackage(manifest, activity)).toEqual([]);
  });
});
