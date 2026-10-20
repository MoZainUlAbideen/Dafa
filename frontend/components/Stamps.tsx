import type { Schedule } from "@/lib/api";
import { verdict } from "@/lib/api";

// CrPC Schedule II facts rendered as rubber stamps.
// Red ink for the facts that make things harder for an accused person.

type StampSpec = { text: string; sub?: string; tone: "violet" | "red" | "quiet" };

export function stampsFor(s: Schedule): StampSpec[] {
  const out: StampSpec[] = [];
  const bail = verdict(s.bailable, /bailable|^yes/, /not bailable|non-bailable|^no/);
  if (bail === "yes") out.push({ text: "Bailable", tone: "violet" });
  if (bail === "no") out.push({ text: "Not bailable", tone: "red" });

  const cog = verdict(s.cognizable, /may arrest|^yes|cognizable/, /shall not|^no|non-cognizable/);
  if (cog === "yes") out.push({ text: "Cognizable", sub: "police may arrest without warrant", tone: "red" });
  if (cog === "no") out.push({ text: "Non-cognizable", sub: "arrest needs a warrant", tone: "violet" });

  const comp = verdict(s.compoundable, /compoundable|^yes/, /not compoundable|non-compoundable|^no/);
  if (comp === "yes") out.push({ text: "Compoundable", sub: "can be settled between parties", tone: "violet" });
  if (comp === "no") out.push({ text: "Not compoundable", tone: "quiet" });

  if (s.court) out.push({ text: s.court.replace(/\.$/, ""), sub: "trial court", tone: "quiet" });
  return out;
}

const TILTS = ["-2.5deg", "1.5deg", "-1deg", "2deg", "-1.5deg"];

export default function Stamps({ schedule, animate }: { schedule: Schedule; animate?: boolean }) {
  const specs = stampsFor(schedule);
  if (!specs.length) return null;
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
          <span>Punishment per Schedule II: </span>
          {schedule.punishment}
        </p>
      )}
    </>
  );
}
