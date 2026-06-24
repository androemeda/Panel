const JD_OPTIONS = [
  {
    label: "Senior Backend",
    value: "job_descriptions/jd_senior_backend.txt"
  },
  {
    label: "Senior PM",
    value: "job_descriptions/jd_senior_pm.txt"
  },
  {
    label: "Junior Frontend",
    value: "job_descriptions/jd_junior_frontend.txt"
  }
];


export default function JdUpload({
  jdFile,
  rawJdText,
  onJdFileChange,
  onRawJdTextChange,
  onRank,
  ranking,
  canRank
}) {
  return (
    <section className="tool-section" aria-labelledby="jd-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Ranking Setup</p>
          <h2 id="jd-title">Job and Candidates</h2>
        </div>
      </div>

      <div className="form-grid single">
        <label>
          <span>JD file</span>
          <select
            value={jdFile}
            onChange={(event) => onJdFileChange(event.target.value)}
            disabled={ranking || Boolean(rawJdText.trim())}
          >
            {JD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="textarea-label">
        <span>Raw JD text</span>
        <textarea
          value={rawJdText}
          onChange={(event) => onRawJdTextChange(event.target.value)}
          disabled={ranking}
          rows={7}
        />
      </label>

      <div className="button-row">
        <button
          type="button"
          className="primary-button"
          onClick={onRank}
          disabled={!canRank || ranking}
        >
          {ranking ? "Ranking..." : "Create Ranking"}
        </button>
      </div>
    </section>
  );
}
