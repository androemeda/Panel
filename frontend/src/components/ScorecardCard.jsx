function scoreClass(score) {
  if (score >= 8) return "score-high";
  if (score >= 6) return "score-mid";
  return "score-low";
}


export default function ScorecardCard({ scorecard, profile }) {
  if (!scorecard) return null;

  return (
    <article className="scorecard-card">
      <details>
        <summary className="candidate-summary">
          <div>
            <strong>{profile?.name ?? scorecard.candidate_id}</strong>
            <span>{scorecard.summary}</span>
          </div>
          <span className={`score-chip ${scoreClass(scorecard.overall_score)}`}>
            {Number(scorecard.overall_score).toFixed(1)}
          </span>
        </summary>

        <div className="competency-list">
          {scorecard.competency_scores.map((item) => (
            <div className="competency-row" key={`${scorecard.candidate_id}-${item.competency}`}>
              <div>
                <strong>{item.competency}</strong>
                <p>{item.evidence}</p>
              </div>
              <div className="competency-score">
                <span>{item.score}/10</span>
                <small>{item.rubric_level}</small>
              </div>
            </div>
          ))}
        </div>
      </details>
    </article>
  );
}
