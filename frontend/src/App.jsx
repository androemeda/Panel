import { useCallback, useEffect, useMemo, useState } from "react";

import {
  approveDraft,
  clearCandidates,
  deleteCandidate,
  decideCandidate,
  fetchCandidates,
  fetchHealth,
  fetchState,
  rankCandidates,
  uploadCandidates
} from "./api";
import CandidateList from "./components/CandidateList";
import CandidateUploadModal from "./components/CandidateUploadModal";
import DraftEmailModal from "./components/DraftEmailModal";
import JdUpload from "./components/JdUpload";
import RankedList from "./components/RankedList";
import ScorecardCard from "./components/ScorecardCard";
import TraceLink from "./components/TraceLink";
import "./styles.css";


function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [ranking, setRanking] = useState(false);
  const [busyCandidate, setBusyCandidate] = useState(null);
  const [approving, setApproving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [jdFile, setJdFile] = useState("job_descriptions/jd_senior_backend.txt");
  const [rawJdText, setRawJdText] = useState("");
  const [rankResult, setRankResult] = useState(null);
  const [session, setSession] = useState(null);
  const [draftDecision, setDraftDecision] = useState(null);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const result = await fetchHealth();
      setHealth(result);
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : "Unable to reach backend");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  useEffect(() => {
    fetchState()
      .then(setSession)
      .catch(() => {});
  }, []);

  const handleRank = useCallback(async () => {
    setRanking(true);
    setError("");
    setNotice("");

    try {
      const ranked = await rankCandidates({ jdFile, rawJdText });
      const savedState = await fetchState();
      setRankResult(ranked);
      setSession(savedState);
      setDraftDecision(null);
      setNotice(`Ranked ${Object.keys(ranked.scorecards).length} candidates`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create ranking");
    } finally {
      setRanking(false);
    }
  }, [jdFile, rawJdText]);

  const refreshSession = useCallback(async () => {
    const savedState = await fetchState();
    setSession(savedState);
    return savedState;
  }, []);

  const refreshCandidatePool = useCallback(async () => {
    const response = await fetchCandidates();
    setSession((current) => ({
      ...(current ?? {}),
      candidate_pool: response.candidates,
      parsed_jd: null,
      retrieved_rubric: null,
      scorecards: {},
      shortlist: null,
      decisions: {},
      drafts: {},
      no_availability: {},
      held_slots: []
    }));
    setRankResult(null);
    setDraftDecision(null);
    return response;
  }, []);

  const handleDecision = useCallback(async (candidateId, decision) => {
    setBusyCandidate({ candidateId, decision });
    setError("");
    setNotice("");

    try {
      const result = await decideCandidate(candidateId, decision);
      await refreshSession();

      if (result.no_availability) {
        setDraftDecision(null);
        setNotice(`${candidateId}: no available slots`);
      } else if (result.draft_email) {
        setDraftDecision(result);
        setNotice(`${candidateId}: draft ready`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create decision draft");
    } finally {
      setBusyCandidate(null);
    }
  }, [refreshSession]);

  const handleApprove = useCallback(async (candidateId, payload) => {
    setApproving(true);
    setError("");
    setNotice("");

    try {
      const result = await approveDraft(candidateId, payload);
      await refreshSession();
      setDraftDecision(null);
      setNotice(`${candidateId}: ${result.draft_email.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to approve draft");
    } finally {
      setApproving(false);
    }
  }, [refreshSession]);

  const handleUploadCandidates = useCallback(async (files) => {
    setUploading(true);
    setError("");
    setNotice("");

    try {
      const result = await uploadCandidates(files);
      const savedState = await fetchState();
      setSession(savedState);
      setRankResult(null);
      setDraftDecision(null);
      setUploadModalOpen(false);
      setNotice(`Pool now has ${result.candidates.length} candidate${result.candidates.length === 1 ? "" : "s"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to upload candidates");
    } finally {
      setUploading(false);
    }
  }, []);

  const handleRemoveCandidate = useCallback(async (candidateId) => {
    setError("");
    setNotice("");

    try {
      await deleteCandidate(candidateId);
      await refreshCandidatePool();
      setNotice(`${candidateId} removed`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove candidate");
    }
  }, [refreshCandidatePool]);

  const handleClearPool = useCallback(async () => {
    setError("");
    setNotice("");

    try {
      const result = await clearCandidates();
      setSession((current) => ({
        ...(current ?? {}),
        candidate_pool: result.candidates,
        candidates: {},
        parsed_jd: null,
        retrieved_rubric: null,
        scorecards: {},
        shortlist: null,
        decisions: {},
        drafts: {},
        no_availability: {},
        held_slots: []
      }));
      setRankResult(null);
      setDraftDecision(null);
      setNotice("Candidate pool cleared");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to clear candidate pool");
    }
  }, []);

  const statusText = loading
    ? "Checking backend..."
    : health?.status === "ok"
      ? "Backend connected"
      : "Backend unavailable";

  const candidates = session?.candidate_pool ?? rankResult?.candidate_pool ?? [];
  const profiles = rankResult?.candidates ?? session?.candidates ?? {};
  const scorecards = rankResult?.scorecards ?? session?.scorecards ?? {};
  const shortlist = rankResult?.shortlist ?? session?.shortlist ?? null;
  const drafts = session?.drafts ?? {};
  const noAvailability = session?.no_availability ?? {};
  const traceUrl = rankResult?.trace_url ?? session?.trace_url ?? null;

  const scorecardIds = useMemo(() => {
    if (shortlist?.ranked_candidates?.length) {
      return shortlist.ranked_candidates.map((candidate) => candidate.candidate_id);
    }
    return Object.keys(scorecards);
  }, [scorecards, shortlist]);

  const resetSessionView = useCallback(() => {
    setRankResult(null);
    setSession((current) => current
      ? {
          ...current,
          parsed_jd: null,
          retrieved_rubric: null,
          scorecards: {},
          shortlist: null,
          decisions: {},
          drafts: {},
          no_availability: {},
          held_slots: []
        }
      : current);
    setDraftDecision(null);
    setNotice("");
  }, []);

  return (
    <main className="console-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Recruiter Console</p>
          <h1>Recruiting Pipeline</h1>
        </div>

        <div className="header-actions">
          <span className={`health-pill ${health?.status === "ok" ? "is-ok" : "is-down"}`}>
            {statusText}
          </span>
          <TraceLink traceUrl={traceUrl} />
        </div>
      </header>

      {error ? <div className="alert error">{error}</div> : null}
      {notice ? <div className="alert notice">{notice}</div> : null}

      <div className="workspace-grid">
        <aside className="left-rail">
          <JdUpload
            jdFile={jdFile}
            rawJdText={rawJdText}
            onJdFileChange={(value) => {
              setJdFile(value);
              resetSessionView();
            }}
            onRawJdTextChange={(value) => {
              setRawJdText(value);
              resetSessionView();
            }}
            onRank={handleRank}
            ranking={ranking}
            canRank={Boolean(jdFile || rawJdText.trim()) && candidates.length > 0}
          />

          <CandidateList
            candidates={candidates}
            profiles={profiles}
            drafts={drafts}
            onAddCandidates={() => setUploadModalOpen(true)}
            onRemoveCandidate={handleRemoveCandidate}
            onClearPool={handleClearPool}
            disabled={ranking || uploading}
          />
        </aside>

        <section className="main-results">
          <details className="results-section collapsible-section" open>
            <summary className="section-summary" aria-labelledby="scorecards-title">
              <div>
                <p className="eyebrow">Intermediate</p>
                <h2 id="scorecards-title">Scorecards</h2>
              </div>
              <span className="count-pill">{scorecardIds.length}</span>
            </summary>

            {scorecardIds.length ? (
              <div className="scorecard-list">
                {scorecardIds.map((candidateId) => (
                  <ScorecardCard
                    key={candidateId}
                    scorecard={scorecards[candidateId]}
                    profile={profiles[candidateId]}
                  />
                ))}
              </div>
            ) : (
              <p className="empty-state">No scorecards yet.</p>
            )}
          </details>

          <RankedList
            shortlist={shortlist}
            profiles={profiles}
            drafts={drafts}
            noAvailability={noAvailability}
            busyCandidate={busyCandidate}
            onDecision={handleDecision}
          />
        </section>
      </div>

      <DraftEmailModal
        decision={draftDecision}
        onClose={() => setDraftDecision(null)}
        onApprove={handleApprove}
        approving={approving}
      />

      {uploadModalOpen ? (
        <CandidateUploadModal
          onClose={() => setUploadModalOpen(false)}
          onUpload={handleUploadCandidates}
          uploading={uploading}
        />
      ) : null}
    </main>
  );
}

export default App;
