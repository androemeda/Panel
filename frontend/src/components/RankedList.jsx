import DecisionButtons from "./DecisionButtons";


function recommendationLabel(value) {
  return value.replace("_", " ");
}


export default function RankedList({
  shortlist,
  profiles = {},
  drafts = {},
  noAvailability = {},
  busyCandidate,
  onDecision
}) {
  return (
    <details className="results-section collapsible-section" open>
      <summary className="section-summary" aria-labelledby="ranking-title">
        <div>
          <p className="eyebrow">Final</p>
          <h2 id="ranking-title">Ranking</h2>
        </div>
        <span className="count-pill">{shortlist?.ranked_candidates?.length ?? 0}</span>
      </summary>

      {shortlist ? (
        <>
          <p className="rationale">{shortlist.ranking_rationale}</p>
          <div className="ranked-list">
            {shortlist.ranked_candidates.map((candidate) => {
              const profile = profiles[candidate.candidate_id];

              return (
                <article className="ranked-card" key={candidate.candidate_id}>
                  <details>
                    <summary className="candidate-summary">
                      <div className="rank-main">
                        <span className="rank-number">#{candidate.rank}</span>
                        <div>
                          <h3>{profile?.name ?? candidate.candidate_id}</h3>
                          <div className="meta-line">
                            <span>{recommendationLabel(candidate.recommendation)}</span>
                            <span>{Number(candidate.overall_score).toFixed(1)}</span>
                          </div>
                        </div>
                      </div>

                      {drafts[candidate.candidate_id] ? (
                        <span className={`status-badge ${drafts[candidate.candidate_id].status}`}>
                          {drafts[candidate.candidate_id].status}
                        </span>
                      ) : null}
                    </summary>

                    <div className="rank-details">
                      <p>{candidate.reasoning}</p>

                      <div className="two-column-list">
                        <div>
                          <h4>Strengths</h4>
                          <ul>
                            {candidate.standout_strengths.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <h4>Concerns</h4>
                          <ul>
                            {candidate.concerns.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      </div>

                      <DecisionButtons
                        candidateId={candidate.candidate_id}
                        busy={busyCandidate?.candidateId === candidate.candidate_id ? busyCandidate.decision : ""}
                        draft={drafts[candidate.candidate_id]}
                        noAvailability={noAvailability[candidate.candidate_id]}
                        onDecision={onDecision}
                      />
                    </div>
                  </details>
                </article>
              );
            })}
          </div>
        </>
      ) : (
        <p className="empty-state">No ranking yet.</p>
      )}
    </details>
  );
}
