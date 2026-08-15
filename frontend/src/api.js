const API_BASE = "http://localhost:8000";

export async function uploadDataset(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Upload failed (${res.status})`);
  }

  return res.json();
}

export async function getSuggestions(datasetId) {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/suggestions`);

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to fetch suggestions (${res.status})`);
  }

  return res.json();
}

export async function savePipeline(datasetId, steps) {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/pipeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(steps),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to save pipeline (${res.status})`);
  }

  return res.json();
}

export async function applyPipeline(datasetId) {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/apply`, {
    method: "POST",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to apply pipeline (${res.status})`);
  }

  return res.json();
}

export async function getPipeline(datasetId) {
  const res = await fetch(`${API_BASE}/datasets/${datasetId}/pipeline`);

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to fetch pipeline (${res.status})`);
  }

  return res.json();
}

export function getDownloadUrl(datasetId, format = "csv") {
  return `${API_BASE}/datasets/${datasetId}/download-cleaned?format=${format}`;
}

export async function downloadCleanedFile(datasetId, format = "csv", fallbackFilename = "cleaned_dataset") {
  const url = getDownloadUrl(datasetId, format);
  const res = await fetch(url);

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Download failed (${res.status})`);
  }

  // Extract filename from Content-Disposition header if present
  let filename = `${fallbackFilename}.${format}`;
  const disposition = res.headers.get("Content-Disposition");
  if (disposition && disposition.includes("filename=")) {
    const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
    if (matches && matches[1]) {
      filename = matches[1].replace(/['"]/g, "");
    }
  }

  const blob = await res.blob();
  const blobUrl = window.URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.style.display = "none";
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();

  setTimeout(() => {
    document.body.removeChild(a);
    window.URL.revokeObjectURL(blobUrl);
  }, 200);
}

export async function sendChatMessage(message, datasetId = null) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, dataset_id: datasetId }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to send chat message (${res.status})`);
  }

  return res.json();
}


