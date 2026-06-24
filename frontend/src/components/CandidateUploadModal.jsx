import { useState } from "react";


export default function CandidateUploadModal({ onClose, onUpload, uploading }) {
  const [files, setFiles] = useState([]);

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="draft-modal upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
        <div className="modal-header">
          <div>
            <p className="eyebrow">Pool</p>
            <h2 id="upload-title">Add Candidates</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            x
          </button>
        </div>

        <label className="file-drop">
          <span>Select resume PDFs</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>

        {files.length ? (
          <div className="upload-list">
            {files.map((file) => (
              <span key={`${file.name}-${file.size}`}>{file.name}</span>
            ))}
          </div>
        ) : (
          <p className="empty-state">No files selected.</p>
        )}

        <div className="button-row end">
          <button type="button" onClick={onClose} disabled={uploading}>
            Close
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => onUpload(files)}
            disabled={uploading || !files.length}
          >
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </div>
      </section>
    </div>
  );
}
