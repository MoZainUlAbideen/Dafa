// Guilloche rosette, the watermark seal on stamp paper.
// Drawn as a hypotrochoid: the curve a point traces on a circle rolling inside another.

function hypotrochoid(R: number, r: number, d: number, scale: number, steps = 1400): string {
  const pts: string[] = [];
  const turns = r / gcd(R, r);
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2 * turns;
    const x = (R - r) * Math.cos(t) + d * Math.cos(((R - r) / r) * t);
    const y = (R - r) * Math.sin(t) - d * Math.sin(((R - r) / r) * t);
    pts.push(`${(x * scale + 100).toFixed(2)},${(y * scale + 100).toFixed(2)}`);
  }
  return "M" + pts.join("L");
}
function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

const PATHS = [
  hypotrochoid(96, 36, 52, 0.85),
  hypotrochoid(90, 30, 40, 0.8),
  hypotrochoid(84, 21, 30, 0.75),
];

export default function Rosette({ className = "rosette" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 200 200" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="0.45">
        {PATHS.map((d, i) => (
          <path key={i} d={d} opacity={1 - i * 0.2} />
        ))}
        <circle cx="100" cy="100" r="97" strokeWidth="0.8" />
        <circle cx="100" cy="100" r="93" />
      </g>
    </svg>
  );
}
