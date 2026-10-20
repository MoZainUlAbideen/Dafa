import type { Schedule } from "@/lib/api";
import { verdict } from "@/lib/api";

// CrPC Schedule II facts rendered as rubber stamps.
// Red ink for the facts that make things harder for an accused person;
// grey for answers that depend on which form of the offence applies.

type StampSpec = { text: string; sub?: string; tone: "violet" | "red" | "quiet" };

export function stampsFor(s: Schedule): StampSpec[] {
  const out: StampSpec[] = [];
  const bail = verdict(s.bailable, /bailable/, /not\s+bailable|non-bailable/);
  if (bail === "yes") out.push({ text: "Bailable", tone: "violet" });
  if (bail === "no") out.push({ text: "Not bailable", tone: "red" });
  if (bail === "mixed") out.push({ text: "Bail depends", sub: "on the form of the offence", tone: "quiet" });

  const cog = verdict(s.cognizable, /may\s+arrest/, /shall\s+not\s+arrest/);
  if (cog === "yes") out.push({ text: "Cognizable", sub: "police may arrest without warrant", tone: "red" });
  if (cog === "no") out.push({ text: "Non-cognizable", sub: "arrest needs a warrant", tone: "violet" });
  if (cog === "mixed") out.push({ text: "Arrest depends", sub: "on the form of the offence", tone: "quiet" });

  const comp = verdict(s.compoundable, /compo?undable/, /not\s+compo?undable|non-compo?undable/);
  const withPermission = /permission/i.test(s.compoundable || "");
  if (comp === "yes")
    out.push({ text: "Compoundable", sub: withPermission ? "with the court's permission" : "can be settled between parties", tone: "violet" });
  if (comp === "no") out.push({ text: "Not compoundable", tone: "quiet" });
  if (comp === "mixed") out.push({ text: "Settlement depends", sub: "on the form of the offence", tone: "quiet" });

  const court = (s.court || "").replace(/[;.,]+$/, "").trim();
  if (court && court.length <= 60) out.push({ text: court, sub: "trial court", tone: "quiet" });
  return out;
}

const TILTS = ["-2.5deg", "1.5deg", "-1deg", "2deg", "-1.5deg"];

export default function Stamps({ schedule, animate }: { schedule: Schedule; animate?: boolean }) {
  const specs = stampsFor(schedule);
  if (!specs.length) return null;
  const longCourt = (schedule.court || "").length > 60;
  return (
    <>
      <div className={`stamps${animate ? " thunk" : ""}`} aria-label="Procedure under CrPC Schedule II">
        {specs.map((s, i) => (
          <span
            key={s.text}
            className={`stamp${s.tone === "red" ? " red" : s.tone === "quiet" ? " quiet" : ""}`}
            style={{ ["--tilt" as string]: TILTS[i % TILTS.length], ["--i" as string]: i }}
          >
            {s.text}
            {s.sub && <small>{s.sub}</small>}
          </span>
        ))}
      </div>
      {schedule.punishment && (
        <p className="punishment">
          <span>Punishment per CrPC Schedule II: </span>
          {schedule.punishment}
        </p>
      )}
      {longCourt && (
        <p className="punishment">
          <span>Trial court: </span>
          {schedule.court}
        </p>
      )}
    </>
  );
}
