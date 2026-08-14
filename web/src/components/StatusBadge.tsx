type Tone = "ok" | "warn" | "bad" | "unknown";

const toneLabel: Record<Tone, string> = {
  ok: "OK",
  warn: "Warning",
  bad: "Error",
  unknown: "Unknown",
};

export function StatusBadge({
  tone,
  label,
}: {
  tone: Tone;
  label: string;
}) {
  return (
    <span className={`status status-${tone}`} title={`${toneLabel[tone]}: ${label}`}>
      <span className="status-dot" aria-hidden="true" />
      <span className="sr-only">{toneLabel[tone]}:</span>
      <span>{label}</span>
    </span>
  );
}
