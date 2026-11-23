// Client-side wrapper that mounts a game on a chapter page or activity page.
import { GameRunner } from "../game/GameRunner";
import type { Activity, Manifest } from "../game/types";
import "../game/game.css";

export default function GameIsland({ manifest, activity, assetBase, backHref, backLabel }: {
  manifest: Manifest; activity: Activity; assetBase: string; backHref?: string; backLabel?: string;
}) {
  return (
    <GameRunner manifest={manifest} activity={activity} assetBase={assetBase}
                exitLabel={backLabel} onExit={backHref ? () => { window.location.href = backHref; } : undefined} />
  );
}
