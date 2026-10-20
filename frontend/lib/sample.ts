import type { Section } from "./api";

// Shown on the landing page until the live API responds (and if it is asleep).
// Real extracted data: PPC section 379 with its CrPC Schedule II row.
export const SAMPLE_SECTION: Section = {
  "book": "ppc",
  "id": "379",
  "title": "Punishment for theft",
  "group": "Chapter XVII: Of Offences against Property",
  "page": 137,
  "omitted": false,
  "text": "Whoever commits theft shall be punished with imprisonment of either description for a term which may extend to three years, or with fine or with both.",
  "schedule": {
    "offence": "Theft.",
    "cognizable": "May arrest without warrant.",
    "warrant_or_summons": "Warrant.",
    "bailable": "Not bailable",
    "compoundable": "Not compoundable.",
    "punishment": "Imprisonment of either description for 3 years, or fine, or both.",
    "court": "Any Magistrate."
  },
  "key": "ppc:379",
  "label": "Section 379"
};
