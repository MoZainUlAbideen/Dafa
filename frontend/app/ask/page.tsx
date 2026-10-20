"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import AnswerText from "@/components/AnswerText";
import SectionCard from "@/components/SectionCard";
import { api, BOOK_SHORT, type AskResponse, type BookId, type Section, type TocGroup } from "@/lib/api";

type Turn = { id: number; q: string; res?: AskResponse; error?: string };

const EXAMPLES = [
  "What is the punishment for cheating under section 420?",
  "police ne bina wajah giraftar kar liya, mere kya huqooq hain",
  "Is the right to education in the Constitution?",
  "قتل کی سزا کیا ہے",
];

function labelFor(key: string) {
  const [book, id] = key.split(":");
  return book === "constitution" ? `Art. ${id}` : `PPC ${id}`;
}

function errorText(e: unknown) {
  const m = e instanceof Error ? e.message : "";
  if (m === "rate_limited") return "That's a lot of questions in one minute. Wait a moment, then ask again.";
  return "Couldn't reach the Dafa server. Check your connection and ask again.";
}

function Workspace() {
  const params = useSearchParams();
  const [book, setBook] = useState<BookId>("ppc");
  const [tocs, setTocs] = useState<Partial<Record<BookId, TocGroup[]>>>({});
  const [filter, setFilter] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [reader, setReader] = useState<Section | null>(null);
  const [readerQuotes, setReaderQuotes] = useState<string[]>([]);
  const [navOpen, setNavOpen] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const nextId = useRef(1);

  useEffect(() => {
    if (tocs[book]) return;
    api.toc(book).then((t) => setTocs((p) => ({ ...p, [book]: t }))).catch(() => {});
  }, [book, tocs]);

  const openSection = useCallback((s: Section, quotes: string[] = []) => {
    setReader(s);
    setReaderQuotes(quotes);
    setReaderOpen(true);
    setNavOpen(false);
  }, []);

  const openByRef = useCallback(
    async (b: string, id: string, fromTurn?: AskResponse) => {
      const key = `${b}:${id}`.toLowerCase();
      const local = fromTurn?.sections.find((s) => s.key.toLowerCase().replace("-", "") === key.replace("-", ""));
      const quotes = (fromTurn?.quotes || []).filter((x) => x.key.toLowerCase() === key).map((x) => x.text);
      if (local) return openSection(local, quotes);
      try {
        openSection(await api.section(b, id), quotes);
      } catch {
        /* section missing: ignore */
      }
    },
    [openSection],
  );

  const ask = useCallback(
    async (query: string) => {
      const text = query.trim();
      if (!text || busy) return;
      const id = nextId.current++;
      setTurns((t) => [...t, { id, q: text }]);
      setQ("");
      setBusy(true);
      setSlow(false);
      const slowTimer = setTimeout(() => setSlow(true), 4000);
      try {
        const res = await api.ask(text);
        setTurns((t) => t.map((x) => (x.id === id ? { ...x, res } : x)));
        if (res.sections[0]) {
          const first = res.sections[0];
          openSection(first, res.quotes.filter((x) => x.key.toLowerCase() === first.key.toLowerCase()).map((x) => x.text));
          setReaderOpen(false); // don't cover the answer on small screens
        }
      } catch (e) {
        setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: errorText(e) } : x)));
      } finally {
        clearTimeout(slowTimer);
        setBusy(false);
      }
    },
    [busy, openSection],
  );

  useEffect(() => {
    const initial = params.get("q");
    if (initial && !started.current) {
      started.current = true;
      ask(initial);
    }
  }, [params, ask]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const toc = useMemo(() => {
    const groups = tocs[book] || [];
    const f = filter.trim().toLowerCase();
    if (!f) return groups;
    return groups
      .map((g) => ({ ...g, sections: g.sections.filter((s) => s.id.toLowerCase().startsWith(f) || s.title.toLowerCase().includes(f)) }))
      .filter((g) => g.sections.length);
  }, [tocs, book, filter]);

  return (
    <>
      <div className="mobile-bar">
        <button type="button" onClick={() => setNavOpen((v) => !v)} aria-expanded={navOpen}>
          {navOpen ? "Close the books" : "Browse the books"}
        </button>
        {reader && (
          <button type="button" onClick={() => setReaderOpen(true)}>
            Open {reader.label}
          </button>
        )}
      </div>
      <div className="workspace">
        <aside className={`nav-pane${navOpen ? " open" : ""}`} aria-label="Browse the books">
          <div className="book-tabs" role="group" aria-label="Book">
            {(["ppc", "constitution"] as BookId[]).map((b) => (
              <button key={b} type="button" aria-pressed={book === b} onClick={() => setBook(b)}>
                {BOOK_SHORT[b]}
              </button>
            ))}
          </div>
          <label htmlFor="toc-filter" className="visually-hidden">Filter sections</label>
          <input
            id="toc-filter"
            className="toc-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={book === "ppc" ? "Filter by number or title" : "Filter articles"}
          />
          <div className="toc">
            {!tocs[book] && <p className="reader-empty" style={{ padding: "0 14px" }}>Loading contents…</p>}
            {toc.map((g, gi) => (
              <details key={g.name + gi} open={!!filter.trim()}>
                <summary>{g.name || "Preliminary"}</summary>
                <ul>
                  {g.sections.map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        aria-current={reader?.book === book && reader?.id === s.id ? "true" : undefined}
                        onClick={() => openByRef(book, s.id)}
                      >
                        <span className="num">{s.id}</span>
                        <span>{s.omitted ? <em>Omitted</em> : s.title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        </aside>

        <section className="chat-pane" aria-label="Questions and answers">
          <div className="thread" ref={threadRef} aria-live="polite">
            <div className="thread-inner">
              {turns.length === 0 && (
                <div className="empty">
                  <h1>Ask about the law</h1>
                  <p>Name a section or article, or describe the situation in your own words. English, Urdu and Roman Urdu all work.</p>
                  <div className="tries" style={{ flexDirection: "column", alignItems: "flex-start" }}>
                    {EXAMPLES.map((t) => (
                      <button key={t} type="button" onClick={() => ask(t)} dir="auto">{t}</button>
                    ))}
                  </div>
                </div>
              )}
              {turns.map((t) => (
                <div key={t.id}>
                  <p className="q" dir="auto">{t.q}</p>
                  <div className="a" dir={t.res?.language === "ur" ? "rtl" : "ltr"} lang={t.res?.language === "ur" ? "ur" : undefined}>
                    {!t.res && !t.error && (
                      <p className="thinking">{slow ? "Waking the server up. The first question can take up to a minute" : "Reading the books"}</p>
                    )}
                    {t.error && <p className="error">{t.error}</p>}
                    {t.res && (
                      <>
                        <AnswerText
                          text={t.res.answer}
                          labelFor={labelFor}
                          onCite={(key) => {
                            const [b, id] = key.split(":");
                            openByRef(b, id, t.res);
                          }}
                        />
                        {t.res.sections.length > 0 && (
                          <div className="found" dir="ltr">
                            {t.res.sections.map((s) => (
                              <button key={s.key} type="button" onClick={() => openByRef(s.book, s.id, t.res)}>
                                <strong>{s.label}, {BOOK_SHORT[s.book]}</strong>
                                <span>{s.title}</span>
                              </button>
                            ))}
                          </div>
                        )}
                        <div className="meta" dir="ltr">
                          {t.res.mode === "answer" &&
                            (t.res.verified ? (
                              <span className="ok">Every citation checked against the official text</span>
                            ) : (
                              <span className="warn">Some claims couldn&rsquo;t be verified and were removed</span>
                            ))}
                          {t.res.mode === "search_only" && (
                            <span>{t.res.warnings.length ? t.res.warnings[t.res.warnings.length - 1] : "Matching sections only, no written answer"}</span>
                          )}
                          {t.res.timings_ms.total != null && <span>{(t.res.timings_ms.total / 1000).toFixed(1)}s</span>}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="composer">
            <form
              className="askbox"
              onSubmit={(e) => {
                e.preventDefault();
                ask(q);
              }}
            >
              <label htmlFor="ask-q" className="visually-hidden">Your question</label>
              <input
                id="ask-q"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Ask a question or type a section number"
                autoComplete="off"
                dir="auto"
              />
              <button className="btn" type="submit" disabled={busy}>
                {busy ? "Reading" : "Ask"}
              </button>
            </form>
            <p className="hint">Legal information, not legal advice. Talk to a lawyer about your own case.</p>
          </div>
        </section>

        <aside className={`reader-pane${readerOpen ? " open" : ""}`} aria-label="Section reader">
          <button type="button" className="reader-close" onClick={() => setReaderOpen(false)}>
            Close
          </button>
          {reader ? (
            <SectionCard key={reader.key} section={reader} compact animate quotes={readerQuotes} />
          ) : (
            <p className="reader-empty">Sections you open from an answer or from the contents appear here, with their bail and arrest status.</p>
          )}
        </aside>
      </div>
    </>
  );
}

export default function AskPage() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
