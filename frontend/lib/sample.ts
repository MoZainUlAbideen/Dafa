import type { Section } from "./api";

// Shown on the landing page until the live API responds (and if it is asleep).
// Replaced with the real extracted text by scripts after ingestion.
export const SAMPLE_SECTION: Section = {
  book: "ppc",
  id: "379",
  key: "ppc:379",
  label: "Section 379",
  title: "Punishment for theft",
  group: "Chapter XVII: Of offences against property",
  page: null,
  omitted: false,
  text: "Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine, or with both.",
  schedule: {
    offence: "Theft",
    cognizable: "May arrest without warrant",
    warrant_or_summons: "Warrant",
    bailable: "Not bailable",
    compoundable: "Compoundable",
    punishment: "Imprisonment of either description for 3 years, or fine, or both",
    court: "Any Magistrate",
  },
};
