export default function TraceLink({ traceUrl }) {
  if (!traceUrl) return null;

  return (
    <a className="trace-link" href={traceUrl} target="_blank" rel="noreferrer">
      LangSmith Trace
    </a>
  );
}
