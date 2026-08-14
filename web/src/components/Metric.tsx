type MetricProps = {
  label: string;
  value: string;
  unit?: string;
  unavailable?: string;
};

export function Metric({ label, value, unit, unavailable }: MetricProps) {
  return (
    <div className="panel">
      <div className="metric-label">{label}</div>
      {unavailable ? (
        <div className="metric-value status-unknown" title={unavailable}>
          unavailable
          <span className="metric-unit">({unavailable})</span>
        </div>
      ) : (
        <div className="metric-value">
          {value}
          {unit ? <span className="metric-unit">{unit}</span> : null}
        </div>
      )}
    </div>
  );
}
