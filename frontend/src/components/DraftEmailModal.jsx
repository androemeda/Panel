import { useEffect, useState } from "react";


function formatSlot(slot) {
  const start = new Date(slot.start);
  const end = new Date(slot.end);
  return `${start.toLocaleString()} - ${end.toLocaleTimeString()}`;
}


export default function DraftEmailModal({ decision, onClose, onApprove, approving }) {
  const draft = decision?.draft_email;
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  useEffect(() => {
    setTo(draft?.to ?? "");
    setSubject(draft?.subject ?? "");
    setBody(draft?.body ?? "");
  }, [draft]);

  if (!draft) return null;

  const slots = draft.proposed_slots ?? decision?.proposed_slots?.slots ?? [];

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="draft-modal" role="dialog" aria-modal="true" aria-labelledby="draft-title">
        <div className="modal-header">
          <div>
            <p className="eyebrow">{draft.email_type}</p>
            <h2 id="draft-title">Review email</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            x
          </button>
        </div>

        {slots.length ? (
          <div className="slot-list">
            {slots.map((slot) => (
              <span key={`${slot.start}-${slot.end}`}>{formatSlot(slot)}</span>
            ))}
          </div>
        ) : null}

        <label className="textarea-label">
          <span>Recipient email</span>
          <input
            type="email"
            value={to}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>

        <label className="textarea-label">
          <span>Subject</span>
          <input value={subject} onChange={(event) => setSubject(event.target.value)} />
        </label>

        <label className="textarea-label">
          <span>Body</span>
          <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={12} />
        </label>

        <div className="button-row end">
          <button type="button" onClick={onClose} disabled={approving}>
            Close
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => onApprove(decision.candidate_id, { to, subject, body })}
            disabled={approving || !to.trim() || !subject.trim() || !body.trim()}
          >
            {approving ? "Approving..." : "Approve and Send"}
          </button>
        </div>
      </section>
    </div>
  );
}
