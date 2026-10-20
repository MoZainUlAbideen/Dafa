// Thin client for the Dafa FastAPI backend.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type BookId = "constitution" | "ppc";

export type Schedule = {
  offence: string;
  cognizable: string;
  warrant_or_summons: string;
  bailable: string;
  compoundable: string;
  punishment: string;
  court: string;
};

export type Section = {
  book: BookId;
  id: string;
  key: string;
  label: string;
  title: string;
  group: string;
  page: number | null;
  omitted: boolean;
  text: string;
  schedule: Schedule | null;
  prev?: { id: string; title: string } | null;
  next?: { id: string; title: string } | null;
};

export type AskResponse = {
  query: string;
  mode: "answer" | "search_only" | "out_of_scope";
  answer: string;
  language: "en" | "ur" | "roman_ur";
  verified: boolean;
  warnings: string[];
  quotes: { key: string; text: string }[];
  sections: Section[];
  timings_ms: Record<string, number>;
  cached: boolean;
};

export type Book = { id: BookId; title: string; unit: string; count: number; with_schedule: number };
export type TocGroup = { name: string; sections: { id: string; title: string; omitted: boolean }[] };

export const BOOK_NAMES: Record<BookId, string> = {
  constitution: "Constitution of Pakistan",
  ppc: "Pakistan Penal Code",
};
export const BOOK_SHORT: Record<BookId, string> = { constitution: "Constitution", ppc: "PPC" };

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(r.status === 404 ? "not_found" : `HTTP ${r.status}`);
  return r.json();
}

export const api = {
  books: () => get<Book[]>("/books"),
  toc: (book: BookId) => get<TocGroup[]>(`/books/${book}/toc`),
  section: (book: string, id: string) => get<Section>(`/sections/${book}/${encodeURIComponent(id)}`),
  ask: async (query: string): Promise<AskResponse> => {
    const r = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (r.status === 429) throw new Error("rate_limited");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
};

export type Verdict = "yes" | "no" | "mixed" | null;

/** Turn a Schedule II cell into a verdict for the stamp.
 *  "mixed": the row covers several forms of the offence with different answers
 *  ("Bailable. Not bailable.") or the answer is conditional ("According as ...", "if ..."). */
export function verdict(cell: string | undefined, yes: RegExp, no: RegExp): Verdict {
  if (!cell) return null;
  const c = cell.toLowerCase();
  if (/\baccording\b|\bif\b|\bdepends\b/.test(c)) return "mixed";
  const noG = new RegExp(no.source, "g");
  const hasNo = noG.test(c);
  const hasYes = yes.test(c.replace(new RegExp(no.source, "g"), " "));
  if (hasNo && hasYes) return "mixed";
  if (hasNo) return "no";
  if (hasYes) return "yes";
  return null;
}
