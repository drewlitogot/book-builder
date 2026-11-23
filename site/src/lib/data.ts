// Build-time access to the content exported by tools/website.py (src/generated). Only approved
// chapters and approved games are ever written there.
import fs from "node:fs";
import path from "node:path";
import type { Activity, Manifest } from "../game/types";

const GEN = path.resolve(process.cwd(), "src/generated");
const read = <T,>(f: string): T => JSON.parse(fs.readFileSync(path.join(GEN, f), "utf8")) as T;

export interface Entry {
  n: number | null; slug: string; title: string; part: string; partIndex: number;
  kind: "front" | "chapter" | "back"; published: boolean; status: "published" | "coming-soon";
  games: string[]; hasRefs?: boolean; toc?: { id: string; text: string }[]; words?: number; minutes?: number; callouts?: string[];
}
export interface Book {
  title: string; subtitle: string; author: string; rights: string;
  editor?: string; publisher?: string; creditLine?: string; aboutAuthors?: string; aiContributors?: string[]; origin: string; base: string;
  preview: boolean; repository?: string; generatedAt: string; entries: Entry[];
  downloads: { format: string; file: string; bytes: number }[];
}
export interface GameData { manifest: Manifest; activity: Activity; status: string }

export const book = read<Book>("book.json");
export const games = read<GameData[]>("games.json");
export interface Guide {
  n: number; slug: string; title: string; sensitive: boolean;
  terms: { term: string; definition: string }[]; sections: { id: string; text: string }[];
  related: { n: number; slug: string; title: string }[];
}
export const guides = fs.existsSync(path.join(GEN, "guides.json")) ? read<Guide[]>("guides.json") : [];
export const guideFor = (slug: string) => guides.find((g) => g.slug === slug);
export const references = read<{ id: string; html: string; chapters: string[] }[]>("references.json");

export const chapterHtml = (slug: string) => fs.readFileSync(path.join(GEN, "chapters", `${slug}.html`), "utf8");
export const chapterRefs = (slug: string) => fs.readFileSync(path.join(GEN, "chapters", `${slug}.refs.html`), "utf8");
export const gameById = (id: string) => games.find((g) => g.manifest.id === id);

export function parts() {
  const out: { title: string; index: number; entries: Entry[] }[] = [];
  for (const e of book.entries) {
    let p = out.find((x) => x.index === e.partIndex);
    if (!p) out.push((p = { title: e.part, index: e.partIndex, entries: [] }));
    p.entries.push(e);
  }
  return out;
}

/** "Part 3: Communication" -> { label: "Part 3", name: "Communication" } */
export function splitPart(title: string) {
  const m = title.match(/^(Part \d+):\s*(.*)$/);
  return m ? { label: m[1], name: m[2] } : { label: "", name: title };
}

const BASE = import.meta.env.BASE_URL.endsWith("/") ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + "/";
/** Prefix a site-relative path with the base path (GitHub Pages project sites live under /repo/). */
export const u = (p = "") => BASE + p.replace(/^\//, "");

export const CALLOUT_LABELS: Record<string, string> = {
  "perspective:men": "Men", "perspective:women": "Women", "perspective:nonbinary": "Non-binary",
};

export const ACTIVITY_TYPES: Record<string, string> = {
  "knowledge-check": "Knowledge check", scenario: "Scenario", reflection: "Reflection",
  practice: "Practice", sorting: "Sorting", explainer: "Explainer",
};

export const chapterLabel = (e: Entry) => (e.n ? `Chapter ${e.n}` : e.kind === "front" ? "Before you start" : "Back matter");
