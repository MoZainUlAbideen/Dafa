import { Fragment, type ReactNode } from "react";

// Minimal markdown: paragraphs, "- " bullets, **bold**, and [ppc:302] citation chips.

const CITE_RE = /\[((?:ppc|constitution):[0-9]{1,3}[A-Za-z\-]{0,4})\]/g;

function inline(text: string, onCite: (key: string) => void, labelFor: (key: string) => string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  CITE_RE.lastIndex = 0;
  while ((m = CITE_RE.exec(text))) {
    if (m.index > last) out.push(...bold(text.slice(last, m.index), out.length));
    const key = m[1];
    out.push(
      <button key={`c${m.index}`} type="button" className="cite" onClick={() => onCite(key)} dir="ltr">
        {labelFor(key)}
      </button>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(...bold(text.slice(last), out.length));
  return out;
}

function bold(text: string, base: number): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={`b${base}-${i}`}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={`t${base}-${i}`}>{part}</Fragment>
    ),
  );
}

export default function AnswerText({
  text,
  onCite,
  labelFor,
}: {
  text: string;
  onCite: (key: string) => void;
  labelFor: (key: string) => string;
}) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, bi) => {
        const lines = block.split("\n").filter((l) => l.trim());
        if (lines.length && lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return (
            <ul key={bi}>
              {lines.map((l, li) => (
                <li key={li}>{inline(l.replace(/^\s*[-*•]\s+/, ""), onCite, labelFor)}</li>
              ))}
            </ul>
          );
        }
        return <p key={bi}>{inline(lines.join(" ").replace(/^#+\s*/, ""), onCite, labelFor)}</p>;
      })}
    </>
  );
}
