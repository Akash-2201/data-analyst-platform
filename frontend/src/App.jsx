import { useCallback, useEffect, useRef, useState } from "react";
import {
  uploadDataset,
  getSuggestions,
  savePipeline,
  applyPipeline,
  downloadCleanedFile,
  sendChatMessage,
} from "./api";
import "./App.css";

function ChatBot({ datasetId }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { sender: "assistant", text: "Ask me anything about your data" },
  ]);
  const [inputMsg, setInputMsg] = useState("");
  const [loading, setLoading] = useState(false);

  const chatEndRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, isOpen]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!inputMsg.trim() || loading) return;

    const userText = inputMsg.trim();
    setInputMsg("");
    setMessages((prev) => [...prev, { sender: "user", text: userText }]);
    setLoading(true);

    try {
      const res = await sendChatMessage(userText, datasetId);
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", text: res.reply || "No response received." },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", text: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        className="chat-toggle-btn"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label="Toggle Data Assistant"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>

      {isOpen && (
        <div className="chat-panel fadeInUp">
          <div className="chat-header">
            <div className="chat-title">Data Assistant</div>
            <div className="chat-header-actions">
              <button
                className="chat-icon-btn"
                onClick={() => setIsOpen(false)}
                title="Close"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="chat-body">
            <div className="chat-messages">
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`chat-bubble ${msg.sender === "user" ? "user" : "assistant"}`}
                >
                  {msg.text}
                </div>
              ))}
              {loading && (
                <div className="chat-bubble assistant typing-indicator">
                  <span>Assistant is typing...</span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <form className="chat-input-area" onSubmit={handleSend}>
              <input
                type="text"
                placeholder="Ask a question..."
                value={inputMsg}
                onChange={(e) => setInputMsg(e.target.value)}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !inputMsg.trim()}>
                Send
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

function Dropzone({ onFile, disabled }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file && !disabled) onFile(file);
    },
    [onFile, disabled]
  );

  return (
    <div
      className={`dropzone${dragging ? " dragging" : ""}${disabled ? " loading" : ""}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      {disabled ? (
        <div className="ledger-loader">
          <div className="loader-label">Profiling dataset structure…</div>
          <div className="ledger-loading-track">
            <div className="ledger-loading-bar" />
          </div>
          <div className="loader-hint">Analyzing types, missing values & quality metrics</div>
        </div>
      ) : (
        <>
          <div className="label">Drop a CSV or Excel file, or click to browse</div>
          <div className="hint">.csv, .xlsx, .xls</div>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
    </div>
  );
}

function QualityBars({ column }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(timer);
  }, []);

  const missingPct = Math.max(column.missing_pct, column.missing_pct > 0 ? 4 : 0);
  const uniquePct = column.unique_pct;

  return (
    <div className="quality-cell">
      <div className="bar-row">
        <span className="bar-label">missing</span>
        <div className="bar-track">
          <div
            className={`bar-fill${column.missing_pct > 0 ? " flagged" : ""}`}
            style={{ width: mounted ? `${missingPct}%` : "0%" }}
          />
        </div>
        <span className="bar-value">{column.missing_pct}%</span>
      </div>
      <div className="bar-row">
        <span className="bar-label">unique</span>
        <div className="bar-track">
          <div
            className="bar-fill"
            style={{ width: mounted ? `${uniquePct}%` : "0%" }}
          />
        </div>
        <span className="bar-value">{column.unique_pct}%</span>
      </div>
      {column.numeric_stats && (
        <div className="numeric-note">
          min {column.numeric_stats.min} · mean {column.numeric_stats.mean} · max{" "}
          {column.numeric_stats.max}
          {column.numeric_stats.outlier_count > 0 && (
            <> · {column.numeric_stats.outlier_count} outliers</>
          )}
        </div>
      )}
    </div>
  );
}

function ColumnRow({ column, index }) {
  return (
    <div className="column-row" style={{ animationDelay: `${index * 50}ms` }}>
      <div className="name-cell">
        <div className="name">{column.name}</div>
        <span className="type-badge">{column.inferred_type}</span>
      </div>
      <div className="dtype">{column.dtype}</div>
      <QualityBars column={column} />
      <div className="samples-cell">
        {column.sample_values.map((v, i) => (
          <span className="sample-chip" key={i} title={v}>
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Suggestions & cleaning pipeline state
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [cleaningLoading, setCleaningLoading] = useState(false);
  const [cleaningError, setCleaningError] = useState(null);
  const [cleaningResult, setCleaningResult] = useState(null);
  const [downloadingFormat, setDownloadingFormat] = useState(null);

  const handleFile = async (file) => {
    setLoading(true);
    setError(null);
    setCleaningResult(null);
    setCleaningError(null);
    setSuggestions([]);
    setSelectedIds(new Set());

    try {
      const data = await uploadDataset(file);
      setReport(data);

      if (data.dataset_id) {
        fetchSuggestions(data.dataset_id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSuggestions = async (datasetId) => {
    setSuggestionsLoading(true);
    try {
      const list = await getSuggestions(datasetId);
      setSuggestions(list);
      // Checked by default for high and medium severity
      const defaults = new Set(
        list
          .filter((s) => s.severity === "high" || s.severity === "medium")
          .map((s) => s.id)
      );
      setSelectedIds(defaults);
    } catch (err) {
      setCleaningError(`Could not load suggestions: ${err.message}`);
    } finally {
      setSuggestionsLoading(false);
    }
  };

  const toggleSuggestion = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleApplyCleaning = async () => {
    if (!report?.dataset_id) return;
    setCleaningLoading(true);
    setCleaningError(null);

    const approvedSteps = suggestions
      .filter((s) => selectedIds.has(s.id))
      .map((s) => ({
        action: s.action,
        params: s.params,
        description: s.description,
        severity: s.severity,
      }));

    try {
      await savePipeline(report.dataset_id, approvedSteps);
      const res = await applyPipeline(report.dataset_id);
      setCleaningResult(res);
      if (res.cleaned_profile) {
        setReport((prev) => ({
          ...prev,
          ...res.cleaned_profile,
        }));
      }
    } catch (err) {
      setCleaningError(err.message);
    } finally {
      setCleaningLoading(false);
    }
  };

  const handleDownload = async (format) => {
    if (!report?.dataset_id) return;
    setDownloadingFormat(format);
    try {
      const stem = report.filename ? report.filename.replace(/\.[^/.]+$/, "") : "dataset";
      await downloadCleanedFile(report.dataset_id, format, `${stem}_cleaned`);
    } catch (err) {
      setCleaningError(`Download failed: ${err.message}`);
    } finally {
      setDownloadingFormat(null);
    }
  };

  const resetAll = () => {
    setReport(null);
    setSuggestions([]);
    setSelectedIds(new Set());
    setCleaningResult(null);
    setCleaningError(null);
    setError(null);
  };

  const displayReport = report;

  return (
    <div className="page">
      <div className="masthead">
        <p className="eyebrow">Data profiler & cleaner · step 1 & 2</p>
        <h1>What's actually in your data</h1>
        <p>
          Upload a raw file to get an automatic audit: types, missing values,
          duplicates, and outliers, before review and rule-based cleaning.
        </p>
      </div>

      {!report && <Dropzone onFile={handleFile} disabled={loading} />}
      {error && <div className="error-banner">{error}</div>}

      {displayReport && (
        <div className="report-wrapper fadeInUp">
          <div className="filename">{displayReport.filename}</div>
          <div className="stat-strip">
            <div className="stat">
              <span className="value">{displayReport.row_count?.toLocaleString()}</span>
              <span className="label">rows</span>
            </div>
            <div className="stat">
              <span className="value">{displayReport.column_count}</span>
              <span className="label">columns</span>
            </div>
            <div className="stat">
              <span className={`value${displayReport.duplicate_row_count > 0 ? " flagged" : ""}`}>
                {displayReport.duplicate_row_count?.toLocaleString()}
              </span>
              <span className="label">duplicate rows</span>
            </div>
          </div>

          <div className="ledger-header">Columns</div>
          {displayReport.columns?.map((col, idx) => (
            <ColumnRow column={col} index={idx} key={col.name} />
          ))}

          {/* --- Cleaning suggestions section --- */}
          <div className="cleaning-section">
            <div className="ledger-header">Review suggested fixes</div>
            {suggestionsLoading ? (
              <div className="loading-note">Analyzing cleaning rules…</div>
            ) : suggestions.length === 0 ? (
              <div className="clean-note">No automated cleaning issues detected. Your data looks good!</div>
            ) : (
              <div className="suggestions-list smooth-expand">
                {suggestions.map((s) => {
                  const isChecked = selectedIds.has(s.id);
                  return (
                    <label className="suggestion-row" key={s.id}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleSuggestion(s.id)}
                      />
                      <span className="suggestion-desc">{s.description}</span>
                      <span className={`severity-badge ${s.severity}`}>{s.severity}</span>
                    </label>
                  );
                })}
              </div>
            )}

            {cleaningError && <div className="error-banner">{cleaningError}</div>}

            {suggestions.length > 0 && !cleaningResult && (
              <div className="actions-strip">
                <button
                  className="apply-button"
                  onClick={handleApplyCleaning}
                  disabled={cleaningLoading || selectedIds.size === 0}
                >
                  {cleaningLoading ? "Applying cleaning…" : `Apply cleaning (${selectedIds.size} selected)`}
                </button>
              </div>
            )}
          </div>

          {/* --- Cleaning results & Download section --- */}
          {cleaningResult && (
            <div className="result-section smooth-expand">
              <div className="ledger-header">Cleaning execution summary</div>
              <div className="row-change-banner">
                <div className="row-change-stat">
                  <span className="label">Original rows</span>
                  <span className="mono-val">{cleaningResult.original_row_count}</span>
                </div>
                <div className="row-change-arrow">→</div>
                <div className="row-change-stat">
                  <span className="label">Cleaned rows</span>
                  <span className="mono-val good">{cleaningResult.cleaned_row_count}</span>
                </div>
              </div>

              <div className="ledger-header">Transformation Log</div>
              <div className="log-list">
                {cleaningResult.log.map((item, idx) => (
                  <div className="log-row" key={idx}>
                    <span className="log-action">{item.action}</span>
                    <span className="log-desc">{item.description}</span>
                    <span className="log-count">
                      {item.rows_affected > 0 ? `-${item.rows_affected} rows` : "0 affected"}
                    </span>
                  </div>
                ))}
              </div>

              <div className="download-strip">
                <button
                  className="download-button"
                  onClick={() => handleDownload("csv")}
                  disabled={downloadingFormat !== null}
                >
                  {downloadingFormat === "csv" ? "Downloading…" : "Download cleaned CSV"}
                </button>
                <button
                  className="download-button secondary"
                  onClick={() => handleDownload("xlsx")}
                  disabled={downloadingFormat !== null}
                  style={{ marginLeft: "12px" }}
                >
                  {downloadingFormat === "xlsx" ? "Downloading…" : "Download Excel (.xlsx)"}
                </button>
              </div>
            </div>
          )}

          <button className="reset-link" onClick={resetAll}>
            ← Profile another file
          </button>
        </div>
      )}

      <ChatBot datasetId={displayReport?.dataset_id} />
    </div>
  );
}

