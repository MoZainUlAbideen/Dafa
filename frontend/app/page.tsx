"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import SectionCard from "@/components/SectionCard";
import { api, type Book, type Section } from "@/lib/api";
import { SAMPLE_SECTION } from "@/lib/sample";

const TRIES = ["Section 302", "cheque bounce ho gaya", "Article 10 arrest rights", "رشوت کی سزا کیا ہے"];

export default function Home() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [demo, setDemo] = useState<Section>(SAMPLE_SECTION);
  const [books, setBooks] = useState<Book[] | null>(null);

  useEffect(() => {
    api.section(SAMPLE_SECTION.book, SAMPLE_SECTION.id).then(setDemo).catch(() => {});
    api.books().then(setBooks).catch(() => {});
  }, []);

  const go = (query: string) => {
    const t = query.trim();
    if (t) router.push(`/ask?q=${encodeURIComponent(t)}`);
  };
  const count = (id: string) => books?.find((b) => b.id === id)?.count;

  return (
    <main>
      <section className="hero">
        <div>
          <p className="hero-urdu" lang="ur" dir="rtl">دفعہ لگ گئی؟ پہلے پڑھیں قانون کہتا کیا ہے۔</p>
          <h1>Heard a section number? Read what it actually says.</h1>
          <p className="lede">
            Ask about Pakistan&rsquo;s Constitution or Penal Code in English, Urdu or Roman Urdu. Each answer points to the
            exact section, checked against the official text.
          </p>
          <form
            className="askbox"
            onSubmit={(e) => {
              e.preventDefault();
              go(q);
            }}
          >
            <label htmlFor="hero-q" className="visually-hidden">Section number or question</label>
            <input
              id="hero-q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Type a section number or describe what happened"
              autoComplete="off"
            />
            <button className="btn" type="submit">Ask</button>
          </form>
          <div className="tries">
            <span>Try</span>
            {TRIES.map((t) => (
              <button key={t} type="button" onClick={() => go(t)} dir="auto">{t}</button>
            ))}
          </div>
        </div>
        <div>
          <SectionCard section={demo} animate />
        </div>
      </section>

      <section className="band" aria-labelledby="how">
        <h2 id="how">How an answer is made</h2>
        <p>Dafa only answers from the law itself. If the books don&rsquo;t cover your question, it says so.</p>
        <ol className="steps">
          <li>
            <h3>Find the sections</h3>
            <p>A section number is opened directly. Everyday words like &ldquo;chori&rdquo; or &ldquo;cheque bounce&rdquo; are matched to the terms the law uses.</p>
          </li>
          <li>
            <h3>Write it in your language</h3>
            <p>The answer is written in the language you asked in, with a citation after every claim. The law&rsquo;s own words stay in English.</p>
          </li>
          <li>
            <h3>Check every citation</h3>
            <p>Before you see it, each cited section, quote and number of years is checked against the official text. Anything that doesn&rsquo;t match is removed and flagged.</p>
          </li>
        </ol>
      </section>

      <section className="band" aria-labelledby="books">
        <h2 id="books">The books</h2>
        <p>Extracted from the official PDFs, with amendment markers cleaned out and every section kept whole.</p>
        <div className="shelf">
          <Link className="spine" href="/read/constitution/1">
            <h3>Constitution of Pakistan, 1973</h3>
            <p>Your fundamental rights, Parliament, the courts and how the state works.</p>
            <p className="count">{count("constitution") ? `${count("constitution")} articles` : "Articles"}</p>
          </Link>
          <Link className="spine" href="/read/ppc/1">
            <h3>Pakistan Penal Code, 1860</h3>
            <p>Offences and punishments, with bail and arrest status from CrPC Schedule II.</p>
            <p className="count">{count("ppc") ? `${count("ppc")} sections` : "Sections"}</p>
          </Link>
        </div>
      </section>

      <footer className="footnote">
        <p>
          Dafa gives legal information, not legal advice. Laws are amended; always confirm the current text and talk to a
          lawyer about your own case.
        </p>
        <p>Built by Muhammad Zain ul Abideen.</p>
      </footer>
    </main>
  );
}
