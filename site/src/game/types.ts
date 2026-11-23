// Types for the Book Builder Game Package API 1.1 (1.0 packages run unchanged).
// The formal definitions are docs/game-developer/schemas/*.schema.json.

export const API_VERSION = "1.1";
export const SUPPORTED_API_VERSIONS = ["1.0", "1.1"];
export const RUNTIME_CAPABILITIES = [
  "images", "audio", "branching", "variables", "perspective-switching", "reflection-summary", "scoring", "save-notes",
] as const;

export type Tone = "neutral" | "positive" | "consider" | "caution";
export type Scalar = string | number | boolean;
export type AnswerValue = string | string[] | number | boolean | undefined;
export type Answers = Record<string, AnswerValue>;
export type Vars = Record<string, Scalar>;

export interface Asset { path: string; type: "image" | "audio" | "captions" | "transcript"; alt?: string; transcript?: string; credit?: string }

export interface Manifest {
  apiVersion: string;
  id: string;
  title: string;
  description: string;
  version: string;
  chapter: number;
  activityType: "knowledge-check" | "scenario" | "reflection" | "practice" | "sorting" | "explainer";
  subjects?: string[];
  learningObjectives: string[];
  contentWarnings: string[];
  sensitive?: boolean;
  estimatedMinutes?: number;
  language?: string;
  accessibility: { summary: string; keyboard: true; screenReader: true; readingLevel?: string; notes?: string };
  requiredCapabilities: string[];
  assets: Asset[];
  authors: { name: string; role?: string; url?: string }[];
  license?: string;
  /** 1.1: a square image asset shown on activity cards. */
  icon?: string;
}

export type Condition =
  | { all: Condition[] }
  | { any: Condition[] }
  | { not: Condition }
  | ({ field: string } & Ops)
  | ({ var: string } & Ops)
  | { visited: string }
  | { score: { gt?: number; gte?: number; lt?: number; lte?: number } };

export interface Ops {
  equals?: Scalar; notEquals?: Scalar; in?: (string | number)[]; includes?: string;
  gt?: number; gte?: number; lt?: number; lte?: number; answered?: boolean;
  /** 1.1, ranking fields: this option is ranked first. */
  first?: string;
}

export interface Effect { var: string; set?: Scalar; add?: number }
export interface Option { value: string; label: string; description?: string; feedback?: string; tone?: Tone; correct?: boolean; effects?: Effect[] }
export interface ImageRef { asset: string; alt?: string }

export type FieldType = "single-choice" | "multiple-choice" | "checkbox" | "dropdown" | "slider" | "text" | "textarea" | "cards" | "ranking";
export interface Field {
  id: string; type: FieldType; label: string; help?: string; required?: boolean;
  options?: Option[]; multiple?: boolean; minSelected?: number; maxSelected?: number; scored?: boolean;
  min?: number; max?: number; step?: number; initial?: number | boolean; minLabel?: string; maxLabel?: string;
  placeholder?: string; maxLength?: number; showIf?: Condition;
  /** 1.1: random option order per play (choice, cards and ranking fields). */
  shuffle?: boolean;
  /** 1.1: an optional hint the reader can open. */
  hint?: string;
}

export type Next = string | { rules?: { when: Condition; goto: string }[]; default: string };
export interface FeedbackRule { when?: Condition; text: string; tone?: Tone }
export interface Perspective { id: string; label: string; body: string; image?: ImageRef }

export interface Screen {
  id: string;
  type: "info" | "form" | "perspective" | "feedback" | "completion";
  title: string;
  body?: string;
  image?: ImageRef;
  fields?: Field[];
  perspectives?: Perspective[];
  requireAllPerspectives?: boolean;
  feedback?: FeedbackRule[];
  effects?: Effect[];
  showSummary?: boolean;
  showScore?: boolean;
  continueLabel?: string;
  next?: Next;
  /** 1.1, completion screens: short points to take away. */
  takeaways?: string[];
  /** 1.1, completion screens: offer "Save my notes" (a text file downloaded to the reader's device). */
  allowSaveNotes?: boolean;
}

export interface Activity { apiVersion: string; start: string; variables?: Record<string, { initial: Scalar; description?: string }>; screens: Screen[] }

export type GameEventType =
  | "init" | "ready" | "start" | "input" | "screenchange" | "progress" | "submit" | "feedback"
  | "complete" | "restart" | "back" | "exit" | "skip" | "error";

export interface GameEvent {
  type: GameEventType;
  gameId: string;
  gameVersion: string;
  apiVersion: string;
  screenId?: string;
  timestamp: number;
  detail: Record<string, unknown>;
}

export interface FeedbackItem { text: string; tone: Tone; fieldId?: string }
