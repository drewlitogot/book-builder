import { afterEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { readFileSync } from "node:fs";
import { GameRunner } from "../src/game/GameRunner";
import type { Activity, GameEvent, Manifest } from "../src/game/types";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const dir = `${process.cwd()}/../tests/fixtures/games/kitchen-sink/`;
const manifest = JSON.parse(readFileSync(dir + "game.json", "utf8")) as Manifest;
const activity = JSON.parse(readFileSync(dir + "activity.json", "utf8")) as Activity;

let root: Root | null = null;
let el: HTMLDivElement;
afterEach(() => { act(() => root?.unmount()); el?.remove(); root = null; });

function render(props: Partial<Parameters<typeof GameRunner>[0]> = {}) {
  const events: GameEvent[] = [];
  el = document.createElement("div");
  document.body.append(el);
  root = createRoot(el);
  act(() => root!.render(<GameRunner manifest={manifest} activity={activity} assetBase="/games/x/" onEvent={(e) => events.push(e)} {...props} />));
  return events;
}
const button = (text: string) => [...el.querySelectorAll("button")].find((b) => b.textContent === text)!;
const click = (b: Element) => act(() => (b as HTMLElement).click());

describe("GameRunner", () => {
  it("shows an intro card with Start and Skip", () => {
    const events = render();
    expect(el.textContent).toContain("Test fixture: every component");
    click(button("Skip activity"));
    expect(events.pop()!.type).toBe("skip");
    expect(el.textContent).toContain("You left the activity");
  });

  it("renders every field type with labels", () => {
    render({ autoStart: true });
    expect(el.querySelector("h3")!.textContent).toBe("Welcome to the fixture");
    expect(el.querySelector("strong")!.textContent).toBe("synthetic");
    expect(el.querySelector("img")!.getAttribute("src")).toBe("/games/x/assets/dot.png");
    expect(el.querySelector("a")!.getAttribute("rel")).toContain("noopener");
    click(button("Continue"));
    expect(el.querySelectorAll('input[type="radio"]').length).toBe(4);
    expect(el.querySelectorAll('input[type="checkbox"]').length).toBe(4);
    expect(el.querySelector("select")).not.toBeNull();
    expect(el.querySelector('input[type="range"]')!.getAttribute("aria-valuetext")).toBe("5");
    expect(el.querySelector("textarea")).not.toBeNull();
    expect(el.querySelector('[data-field="followup"]')).toBeNull();
    for (const f of el.querySelectorAll("fieldset")) expect(f.querySelector("legend")!.textContent!.length).toBeGreaterThan(0);
    for (const i of el.querySelectorAll("select, textarea, input[type=text], input[type=range]")) {
      expect(el.querySelector(`label[for="${i.id}"]`)).not.toBeNull();
    }
  });

  it("validates, shows conditional fields, feedback and branches", () => {
    render({ autoStart: true });
    click(button("Continue"));
    click(button("Check"));
    expect(el.querySelector('[data-field="color"] .pg-error-text')!.textContent).toBe("This one needs an answer.");
    click(el.querySelector('[data-field="color"] input[value="teal"]')!);
    click(el.querySelector('[data-field="agree"] input')!);
    expect(el.querySelector('[data-field="followup"]')).not.toBeNull();
    click(el.querySelector('[data-field="card"] input[value="right"]')!);
    click(button("Check"));
    expect(el.querySelector(".pg-feedback")!.textContent).toContain("Teal noted.");
    click(button("Continue"));
    expect(el.querySelector("h3")!.textContent).toBe("Right branch");
  });

  it("switches perspectives with the keyboard and completes, then restarts", () => {
    const events = render({ autoStart: true });
    click(button("Continue"));
    click(el.querySelector('[data-field="color"] input[value="teal"]')!);
    click(button("Check")); click(button("Continue"));
    const tabs = el.querySelectorAll('[role="tab"]');
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    act(() => tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(el.querySelectorAll('[role="tab"]')[1].getAttribute("aria-selected")).toBe("true");
    click(button("Continue"));
    click(el.querySelector('[data-field="fact"] input[value="four"]')!);
    click(button("Check")); click(button("Continue"));
    expect(el.textContent).toContain("1 of 1 matched the book");
    expect(el.querySelector(".pg-summary")!.textContent).toContain("Teal");
    expect(events.some((e) => e.type === "complete")).toBe(true);
    click(button("Restart"));
    expect(el.querySelector("h3")!.textContent).toBe("Welcome to the fixture");
  });

  it("shows a contained error for a package it can't run", () => {
    const events = render({ manifest: { ...manifest, apiVersion: "9.9" } });
    expect(el.querySelector('[role="alert"]')!.textContent).toContain("couldn't load");
    expect(events.some((e) => e.type === "error")).toBe(true);
  });
});
