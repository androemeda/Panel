const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";


async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {})
    },
    ...options
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof body === "object" && body?.detail
      ? body.detail
      : `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return body;
}


async function formRequest(path, formData, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData,
    ...options
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof body === "object" && body?.detail
      ? body.detail
      : `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return body;
}


export async function fetchHealth() {
  return request("/health");
}


export async function rankCandidates({ jdFile, rawJdText }) {
  return request("/api/rank", {
    method: "POST",
    body: JSON.stringify({
      jd_file: rawJdText?.trim() ? null : jdFile,
      raw_jd_text: rawJdText?.trim() || null
    })
  });
}


export async function fetchState() {
  return request("/api/state");
}


export async function fetchCandidates() {
  return request("/api/candidates");
}


export async function uploadCandidates(files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return formRequest("/api/candidates/upload", formData);
}


export async function deleteCandidate(candidateId) {
  return request(`/api/candidates/${candidateId}`, {
    method: "DELETE"
  });
}


export async function clearCandidates() {
  return request("/api/candidates", {
    method: "DELETE"
  });
}


export async function decideCandidate(candidateId, decision) {
  return request(`/api/candidates/${candidateId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision })
  });
}


export async function approveDraft(candidateId, { subject, body }) {
  return request(`/api/candidates/${candidateId}/approve`, {
    method: "POST",
    body: JSON.stringify({ subject, body })
  });
}
