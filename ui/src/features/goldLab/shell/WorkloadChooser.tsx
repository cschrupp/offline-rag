import {
  GOLD_WORKLOAD_NUMERIC,
  type GoldWorkload,
} from "../state/sessionConfig";

const WORKLOAD_OPTIONS: Array<{ value: GoldWorkload; label: string }> = [
  { value: "1", label: "1" },
  { value: "5", label: "5" },
  { value: "10", label: "10" },
  { value: "25", label: "25" },
  { value: "case", label: "Complete case" },
  { value: "until_stop", label: "Until stop" },
];

type Props = {
  value: GoldWorkload;
  onChange: (workload: GoldWorkload) => void;
  caseIds: string[];
  selectedCaseId: string | null;
  onCaseChange: (caseId: string) => void;
  disabled?: boolean;
};

export function WorkloadChooser({
  value,
  onChange,
  caseIds,
  selectedCaseId,
  onCaseChange,
  disabled = false,
}: Props) {
  return (
    <fieldset className="gold-lab-fieldset" disabled={disabled}>
      <legend>Workload</legend>
      <p className="muted">
        Numeric limits are presentation-only and do not change task membership.
        Until stop omits a workload parameter from the URL.
      </p>
      <div className="row gold-lab-radio-row">
        {WORKLOAD_OPTIONS.map((option) => (
          <label key={option.value} className="gold-lab-radio">
            <input
              type="radio"
              name="gold-lab-workload"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>

      {value === "case" ? (
        <div className="field" style={{ marginTop: "0.75rem" }}>
          <label htmlFor="gold-lab-case">Case</label>
          {caseIds.length === 0 ? (
            <p className="muted" role="status">
              No cases are available from the current task list.
            </p>
          ) : (
            <select
              id="gold-lab-case"
              value={selectedCaseId ?? ""}
              onChange={(event) => onCaseChange(event.target.value)}
              required
            >
              <option value="">Select a case</option>
              {caseIds.map((caseId) => (
                <option key={caseId} value={caseId}>
                  {caseId}
                </option>
              ))}
            </select>
          )}
        </div>
      ) : null}

      {GOLD_WORKLOAD_NUMERIC.includes(
        value as (typeof GOLD_WORKLOAD_NUMERIC)[number],
      ) ? (
        <p className="muted">
          Presentation limit: {value} pending task(s) from the server order.
        </p>
      ) : null}
    </fieldset>
  );
}
