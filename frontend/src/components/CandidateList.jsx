export default function CandidateList({
  candidates = [],
  profiles = {},
  drafts = {},
  onAddCandidates,
  onRemoveCandidate,
  onClearPool,
  disabled
}) {
  return (
    <section className="tool-section" aria-labelledby="candidate-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Pool</p>
          <h2 id="candidate-title">Candidates</h2>
        </div>
        <div className="row-meta">
          <span className="count-pill">{candidates.length}</span>
          <button type="button" onClick={onAddCandidates} disabled={disabled}>
            Add candidates
          </button>
        </div>
      </div>

      {candidates.length ? (
        <div className="candidate-table">
          {candidates.map((candidate) => {
            const profile = profiles[candidate.candidate_id];
            const draft = drafts[candidate.candidate_id];
            const name = candidate.name || profile?.name || candidate.candidate_id;
            const email = candidate.email || profile?.email || "";
            const filename = candidate.filename || candidate.resume_file || "";

            return (
              <div className="candidate-row" key={candidate.candidate_id}>
                <div>
                  <strong>{name}</strong>
                  <span>{email}</span>
                  <span>{filename}</span>
                </div>
                <div className="row-meta">
                  <code>{candidate.candidate_id}</code>
                  {draft ? <span className={`status-badge ${draft.status}`}>{draft.status}</span> : null}
                  <button
                    type="button"
                    onClick={() => onRemoveCandidate(candidate.candidate_id)}
                    disabled={disabled}
                  >
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
          <div className="button-row">
            <button type="button" onClick={onClearPool} disabled={disabled}>
              Clear pool
            </button>
          </div>
        </div>
      ) : (
        <p className="empty-state">No candidates loaded.</p>
      )}
    </section>
  );
}
