import { useCallback, useRef, useState } from "react";
import { uploadDataset } from "./api";
import "./App.css";

function Dropzone({ onFile, disabled }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) onFile(file);
    },
    [onFile]
  );

  return (
    <div
      className={`dropzone${dragging ? " dragging" : ""}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <div className="label">
        {disabled ? "Profiling…" : "Drop a CSV or Excel file, or click to browse"}
      </div>
      <div className="hint">.csv, .xlsx, .xls</div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
    </div>
  );
}

function QualityBars({ column }) {
  return (
    <div className="quality-cell">
      <div className="bar-row">
        <span className="bar-label">missing</span>
        <div className="bar-track">
          <div
            className={`bar-fill${column.missing_pct > 0 ? " flagged" : ""}`}
            style={{ width: `${Math.max(column.missing_pct, column.missing_pct > 0 ? 4 : 0)}%` }}
          />
        </div>
        <span className="bar-value">{column.missing_pct}%</span>
      </div>
      <div className="bar-row">
        <span className="bar-label">unique</span>
        <div className="bar-track">
          <div className="bar-fill" style={{ width: `${column.unique_pct}%` }} />
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

function ColumnRow({ column }) {
  return (
    <div className="column-row">
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

  const handleFile = async (file) => {
    setLoading(true);
    setError(null);
    try {
      const data = await uploadDataset(file);
      setReport(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="masthead">
        <p className="eyebrow">Data profiler · step 1</p>
        <h1>What's actually in your data</h1>
        <p>
          Upload a raw file to get an automatic audit: types, missing values,
          duplicates, and outliers, before you write a single cleaning rule.
        </p>
      </div>

      {!report && <Dropzone onFile={handleFile} disabled={loading} />}
      {error && <div className="error-banner">{error}</div>}

      {report && (
        <>
          <div className="filename">{report.filename}</div>
          <div className="stat-strip">
            <div className="stat">
              <span className="value">{report.row_count.toLocaleString()}</span>
              <span className="label">rows</span>
            </div>
            <div className="stat">
              <span className="value">{report.column_count}</span>
              <span className="label">columns</span>
            </div>
            <div className="stat">
              <span className={`value${report.duplicate_row_count > 0 ? " flagged" : ""}`}>
                {report.duplicate_row_count.toLocaleString()}
              </span>
              <span className="label">duplicate rows</span>
            </div>
          </div>

          <div className="ledger-header">Columns</div>
          {report.columns.map((col) => (
            <ColumnRow column={col} key={col.name} />
          ))}

          <button className="reset-link" onClick={() => setReport(null)}>
            ← Profile another file
          </button>
        </>
      )}
    </div>
  );
}
