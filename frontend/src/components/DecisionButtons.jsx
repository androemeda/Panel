export default function DecisionButtons({
  candidateId,
  disabled,
  busy,
  draft,
  noAvailability,
  onDecision
}) {
  if (draft?.status === "sent") {
    return <span className="status-badge sent">sent</span>;
  }

  return (
    <div className="decision-buttons">
      <button
        type="button"
        onClick={() => onDecision(candidateId, "invite")}
        disabled={disabled || busy}
      >
        {busy === "invite" ? "Inviting..." : "Invite"}
      </button>
      <button
        type="button"
        onClick={() => onDecision(candidateId, "reject")}
        disabled={disabled || busy || Boolean(noAvailability)}
      >
        {busy === "reject" ? "Rejecting..." : "Reject"}
      </button>
      {draft ? <span className={`status-badge ${draft.status}`}>{draft.status}</span> : null}
      {noAvailability ? <span className="status-badge blocked">no slots</span> : null}
    </div>
  );
}
