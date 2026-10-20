import Link from "next/link";
import type { Section } from "@/lib/api";
import { BOOK_NAMES } from "@/lib/api";
import Rosette from "./Rosette";
import Stamps from "./Stamps";

// Split statute text into readable paragraphs at clause markers like (1), (a), (i).
function paragraphs(text: string): { text: string; clause: boolean }[] {
  const parts = text
    .replace(/\s+/g, " ")
    .split(/\s(?=\((?:\d{1,2}[A-Z]?|[a-z]{1,2}|[ivx]{1,5})\)\s)|\s(?=Explanation\b)|\s(?=Illustrations?\b)|\s(?=Provided that\b)/)
    .map((p) => p.trim())
    .filter(Boolean);
  return parts.map((p) => ({ text: p, clause: /^\(/.test(p) }));
}

function highlight(text: string, quotes: string[]) {
  const q = quotes.find((x) => x && text.toLowerCase().includes(x.toLowerCase()));
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  );
}

export default function SectionCard({
  section,
  compact,
  animate,
  quotes = [],
  showLink = true,
}: {
  section: Section;
  compact?: boolean;
  animate?: boolean;
  quotes?: string[];
  showLink?: boolean;
}) {
  const paras = paragraphs(section.text);
  return (
    <article className={`sheet${compact ? " compact" : ""}`} aria-labelledby={`h-${section.key}`}>
      <Rosette />
      <div className="sheet-head">
        <span className="sheet-ref">
          <strong>{section.label}</strong>, {BOOK_NAMES[section.book]}
        </span>
      </div>
      <h3 id={`h-${section.key}`}>{section.title}</h3>
      {section.group && <p className="group">{section.group}</p>}
      {section.schedule && <Stamps schedule={section.schedule} animate={animate} />}
      <div className="body">
        {section.omitted ? (
          <p className="omitted">This provision has been omitted by amendment.</p>
        ) : (
          paras.map((p, i) => (
            <p key={i} className={p.clause ? "clause" : undefined}>
              {highlight(p.text, quotes)}
            </p>
          ))
        )}
      </div>
      <div className="sheet-foot">
        <span style={{ color: "var(--ink-soft)" }}>{section.page ? `Source PDF, page ${section.page}` : ""}</span>
        {showLink && <Link href={`/read/${section.book}/${encodeURIComponent(section.id)}`}>Open full page</Link>}
      </div>
    </article>
  );
}
