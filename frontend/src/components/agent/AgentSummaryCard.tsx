import type { ReactNode } from "react";

type AgentSummaryCardProps = {
  title?: string;
  summary?: string | null;
  constraints?: Record<string, unknown> | null;
  evaluation?: string[] | null;
  repairSummary?: Record<string, unknown> | null;
  warnings?: string[] | null;
  footer?: ReactNode;
};

export function AgentSummaryCard({
  title = "Agent review",
  summary,
  constraints,
  evaluation,
  repairSummary,
  warnings,
  footer,
}: AgentSummaryCardProps) {
  const constraintEntries = Object.entries(constraints ?? {}).filter(([, value]) => hasValue(value)).slice(0, 8);
  const repairCount = Number(repairSummary?.action_count ?? 0);
  const visibleWarnings = (warnings ?? []).filter(Boolean).slice(0, 4);
  const visibleEvaluation = (evaluation ?? []).filter(Boolean).slice(0, 4);

  if (!summary && !constraintEntries.length && !visibleEvaluation.length && !repairCount && !visibleWarnings.length && !footer) {
    return null;
  }

  return (
    <section className="agent-summary-card">
      <div className="agent-summary-header">
        <span className="agent-summary-eyebrow">AI Agent</span>
        <h3>{title}</h3>
      </div>
      {summary ? <p className="agent-summary-copy">{summary}</p> : null}

      {constraintEntries.length ? (
        <div className="agent-summary-block">
          <span className="agent-summary-label">Understood</span>
          <div className="agent-summary-chips">
            {constraintEntries.map(([key, value]) => (
              <span key={key}>{formatKey(key)}: {formatValue(value)}</span>
            ))}
          </div>
        </div>
      ) : null}

      {visibleEvaluation.length ? (
        <div className="agent-summary-block">
          <span className="agent-summary-label">Checked</span>
          <ul>
            {visibleEvaluation.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {repairCount ? (
        <div className="agent-summary-block">
          <span className="agent-summary-label">Adjusted</span>
          <p>{repairCount} repair operation{repairCount > 1 ? "s" : ""} applied before saving.</p>
        </div>
      ) : null}

      {visibleWarnings.length ? (
        <div className="agent-summary-warning">
          {visibleWarnings.map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </div>
      ) : null}

      {footer}
    </section>
  );
}

function hasValue(value: unknown) {
  if (value == null) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return String(value).trim().length > 0;
}

function formatValue(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object" && value) return Object.values(value as Record<string, unknown>).filter(hasValue).join(", ");
  return String(value);
}

function formatKey(key: string) {
  return key.replace(/_/g, " ");
}
