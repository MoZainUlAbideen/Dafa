"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import SectionCard from "@/components/SectionCard";
import { api, BOOK_NAMES, type BookId, type Section } from "@/lib/api";

export default function ReadPage() {
  const params = useParams<{ book: string; id: string }>();
  const book = params.book as BookId;
  const id = decodeURIComponent(params.id);
  const [section, setSection] = useState<Section | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSection(null);
    setError(null);
    api
      .section(book, id)
      .then(setSection)
      .catch((e) =>
        setError(e instanceof Error && e.message === "not_found" ? "not_found" : "offline"),
      );
  }, [book, id]);

  const unit = book === "constitution" ? "Article" : "Section";

  return (
    <main className="read-wrap">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/">Dafa</Link> / {BOOK_NAMES[book] ?? book} / {unit} {id}
      </nav>
      {!section && !error && <p className="thinking">Opening {unit.toLowerCase()} {id}</p>}
      {error === "not_found" && (
        <p>
          There is no {unit.toLowerCase()} {id} in the {BOOK_NAMES[book] ?? "book"}. <Link href="/ask">Search instead</Link>.
        </p>
      )}
      {error === "offline" && <p className="error">Couldn&rsquo;t reach the Dafa server. Reload the page to try again.</p>}
      {section && (
        <>
          <SectionCard section={section} animate showLink={false} />
          <nav className="pager" aria-label="Neighbouring sections">
            {section.prev ? (
              <Link href={`/read/${book}/${encodeURIComponent(section.prev.id)}`}>
                <span>Previous</span>
                <strong>{unit} {section.prev.id}: {section.prev.title}</strong>
              </Link>
            ) : <span />}
            {section.next ? (
              <Link href={`/read/${book}/${encodeURIComponent(section.next.id)}`} style={{ textAlign: "right" }}>
                <span>Next</span>
                <strong>{unit} {section.next.id}: {section.next.title}</strong>
              </Link>
            ) : <span />}
          </nav>
          <p style={{ marginTop: 32 }}>
            <Link href={`/ask?q=${encodeURIComponent(`Explain ${unit} ${section.id} in simple words`)}`} style={{ color: "var(--leaf)" }}>
              Ask Dafa to explain this {unit.toLowerCase()} in simple words
            </Link>
          </p>
        </>
      )}
    </main>
  );
}
