// Standalone bundle for the local builder's game preview (tools/web/game-runtime.js).
import { createRoot } from "react-dom/client";
import { GameRunner } from "./GameRunner";
import type { GameEvent } from "./types";

async function mount(el: HTMLElement, opts: { base: string; onEvent?: (e: GameEvent) => void }) {
  const [manifest, activity] = await Promise.all(
    ["game.json", "activity.json"].map((f) => fetch(opts.base + f, { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(`${f}: HTTP ${r.status}`);
      return r.json();
    })),
  );
  createRoot(el).render(<GameRunner manifest={manifest} activity={activity} assetBase={opts.base} onEvent={opts.onEvent} />);
}

(window as unknown as { BookBuilderGame: unknown }).BookBuilderGame = { mount };
