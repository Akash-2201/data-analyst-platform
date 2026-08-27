import { useCallback, useEffect, useRef, useState } from "react";
import {
  BarChart, Bar,
  LineChart, Line,
  ScatterChart, Scatter,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts";
import {
  uploadDataset,
  getSuggestions,
  savePipeline,
  applyPipeline,
  previewPipeline,
  downloadCleanedFile,
  sendChatMessage,
  getChartData,
} from "./api";
import "./App.css";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a proposed_action from the chat API into a pipeline step shape. */
function proposedActionToStep(proposed_action) {
  const { column, operation, reasoning, severity = "medium" } = proposed_action;
  const params = operation === "drop_duplicates" ? {} : { column };
  return {
    action: operation,
    params,
    description: reasoning,
    severity,
  };
}

function ChatBot({ datasetId, onPreviewChatAction, chartContext }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { sender: "assistant", text: "Ask me anything about your data" },
  ]);
  const [inputMsg, setInputMsg] = useState("");
  const [loading, setLoading] = useState(false);
  // Track inline pending action cards: array of { msgIdx, proposed_action, previewLoading }
  const [pendingActions, setPendingActions] = useState([]);

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
      const res = await sendChatMessage(userText, datasetId, chartContext || null);
      const newMsgIdx = messages.length + 1; // +1 for user msg just added
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", text: res.reply || "No response received.", proposed_action: res.proposed_action || null },
      ]);
      if (res.proposed_action) {
        setPendingActions((prev) => [
          ...prev,
          { msgIdx: newMsgIdx, proposed_action: res.proposed_action, previewLoading: false },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", text: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handlePreviewFix = async (proposed_action, actionIdx) => {
    if (!datasetId || !onPreviewChatAction) return;
    // Mark this action as loading
    setPendingActions((prev) =>
      prev.map((a, i) => (i === actionIdx ? { ...a, previewLoading: true } : a))
    );
    try {
      const step = proposedActionToStep(proposed_action);
      const previewResult = await previewPipeline(datasetId, [step]);
      // Lift to App — pass both the preview data AND the step so App knows what to apply
      onPreviewChatAction(previewResult, [step]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { sender: "assistant", text: `Preview failed: ${err.message}` },
      ]);
    } finally {
      setPendingActions((prev) =>
        prev.map((a, i) => (i === actionIdx ? { ...a, previewLoading: false } : a))
      );
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
              {messages.map((msg, idx) => {
                // Find action card entries associated with this message index
                const actionEntry = msg.proposed_action
                  ? pendingActions.find((a) => {
                      // Match by proposed_action reference (same column+operation)
                      return (
                        a.proposed_action.column === msg.proposed_action.column &&
                        a.proposed_action.operation === msg.proposed_action.operation
                      );
                    })
                  : null;

                return (
                  <div key={idx} className="chat-message-group">
                    <div
                      className={`chat-bubble ${msg.sender === "user" ? "user" : "assistant"}`}
                    >
                      {msg.text}
                    </div>
                    {msg.proposed_action && actionEntry !== undefined && (
                      <div className="chat-action-card">
                        <div className="chat-action-op">
                          <span className="chat-action-label">Suggested fix</span>
                          <span className="log-action">{msg.proposed_action.operation}</span>
                          <span className="chat-action-col">on&nbsp;<strong>{msg.proposed_action.column}</strong></span>
                        </div>
                        <div className="chat-action-reasoning">{msg.proposed_action.reasoning}</div>
                        <button
                          className="chat-preview-btn"
                          disabled={actionEntry?.previewLoading || !datasetId}
                          onClick={() => {
                            const idx2 = pendingActions.findIndex(
                              (a) =>
                                a.proposed_action.column === msg.proposed_action.column &&
                                a.proposed_action.operation === msg.proposed_action.operation
                            );
                            handlePreviewFix(msg.proposed_action, idx2);
                          }}
                        >
                          {actionEntry?.previewLoading ? "Loading preview…" : "Preview this fix"}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
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

  // Reset animation whenever the column name changes (new dataset uploaded).
  // This allows the CSS transition to re-run from 0% each time.
  useEffect(() => {
    setMounted(false);
    const timer = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(timer);
  }, [column.name]); // ← dep on column.name, not [] — fixes stale animation on re-upload

  // Clamp to [0, 100] to guard against NaN or floating-point drift exceeding 100%
  const missingPct = Math.min(100, Math.max(0, column.missing_pct || 0));
  const missingDisplay = Math.max(missingPct, missingPct > 0 ? 4 : 0); // min visible width
  const uniquePct = Math.min(100, Math.max(0, column.unique_pct || 0));

  return (
    <div className="quality-cell">
      <div className="bar-row">
        <span className="bar-label">missing</span>
        <div className="bar-track">
          <div
            className={`bar-fill${column.missing_pct > 0 ? " flagged" : ""}`}
            style={{ width: mounted ? `${missingDisplay}%` : "0%" }}
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

// ---------------------------------------------------------------------------
// Chart colours — a curated palette that works on white
// ---------------------------------------------------------------------------
const CHART_COLORS = [
  "#1c6e8c", "#3aaa7d", "#e05a4b", "#f5a623", "#7b68ee",
  "#20b2aa", "#ff7f50", "#9370db", "#32cd32", "#ff69b4",
];

// ---------------------------------------------------------------------------
// ChartBuilder — interactive chart section rendered below the profiling report
// ---------------------------------------------------------------------------
function ChartBuilder({ datasetId, columns, onChartDataFetched }) {
  const allCols = columns || [];
  const catCols = allCols.filter(
    (c) => c.inferred_type === "categorical" || c.dtype === "object"
  );
  const numCols = allCols.filter(
    (c) =>
      c.inferred_type === "numeric" ||
      c.inferred_type === "non_negative_numeric" ||
      ["int64", "float64", "int32", "float32", "int16", "float16"].includes(c.dtype)
  );

  const defaultX = (catCols[0] || allCols[0])?.name || "";
  const defaultNumX = numCols[0]?.name || "";
  const defaultY = numCols[0]?.name || "";
  const defaultStack = (catCols[1] || catCols[0])?.name || "";

  const [chartType, setChartType] = useState("bar");
  const [xCol, setXCol] = useState(defaultX);
  const [yCol, setYCol] = useState(defaultY);
  const [stackCol, setStackCol] = useState(defaultStack);
  const [agg, setAgg] = useState("count");
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const needsY =
    chartType === "line" ||
    chartType === "scatter" ||
    (chartType === "bar" && agg !== "count");
  const needsStack = chartType === "stacked_bar";
  const isHistOrBox = chartType === "histogram" || chartType === "box_plot";

  const doFetch = async (overrides = {}) => {
    const ct = overrides.chartType ?? chartType;
    const xc = overrides.xCol ?? xCol;
    const yc = overrides.yCol ?? yCol;
    const sc = overrides.stackCol ?? stackCol;
    const ag = overrides.agg ?? agg;

    if (!datasetId || !xc) return;
    const needsYNow = ct === "line" || ct === "scatter" || (ct === "bar" && ag !== "count");
    if (needsYNow && !yc) return;
    if (ct === "stacked_bar" && !sc) return;

    setLoading(true);
    setError(null);
    try {
      let fetchY;
      if (ct === "stacked_bar") fetchY = sc;
      else if (needsYNow) fetchY = yc;
      else if (ct === "box_plot" && yc) fetchY = yc; // optional grouping
      else fetchY = undefined;

      const data = await getChartData(datasetId, {
        chartType: ct, x: xc, y: fetchY, agg: ag, useCleaned: true,
      });
      setChartData(data);
      if (onChartDataFetched) {
        onChartDataFetched({ chartType: ct, x: xc, y: fetchY, agg: ag, ...data });
      }
    } catch (err) {
      setError(err.message);
      setChartData(null);
    } finally {
      setLoading(false);
    }
  };

  // Auto-fetch on mount with sensible defaults
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (datasetId && defaultX) doFetch(); }, []);

  const handleChartTypeChange = (e) => {
    const newType = e.target.value;
    setChartType(newType);
    if ((newType === "histogram" || newType === "box_plot") && defaultNumX) {
      if (!numCols.find((c) => c.name === xCol)) setXCol(defaultNumX);
    }
    if (newType === "stacked_bar") {
      if (catCols.length > 0 && !catCols.find((c) => c.name === xCol))
        setXCol(catCols[0]?.name || xCol);
      setStackCol(catCols[1]?.name || catCols[0]?.name || "");
    }
    if ((newType === "line" || newType === "scatter") && !yCol && defaultY) {
      setYCol(defaultY);
    }
  };

  // ---------------------------------------------------------------------------
  // Renderers
  // ---------------------------------------------------------------------------
  const renderHistogram = () => {
    if (!chartData) return null;
    const { labels, values, x_label } = chartData;
    const data = labels.map((l, i) => ({ label: String(l), value: values[i] ?? 0 }));
    return (
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }} barCategoryGap={1}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [v.toLocaleString(), "Count"]} />
          <Bar dataKey="value" name={x_label} fill="#1c6e8c" radius={[2, 2, 0, 0]} maxBarSize={60} />
        </BarChart>
      </ResponsiveContainer>
    );
  };

  const renderStackedBar = () => {
    if (!chartData || !chartData.series) return null;
    const { labels, series } = chartData;
    const data = labels.map((label, i) => {
      const row = { label: String(label) };
      series.forEach((s) => { row[s.name] = s.data[i] ?? 0; });
      return row;
    });
    return (
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((s, i) => (
            <Bar
              key={s.name}
              dataKey={s.name}
              stackId="a"
              fill={CHART_COLORS[i % CHART_COLORS.length]}
              radius={i === series.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  };

  const renderBoxPlot = () => {
    if (!chartData || !chartData.box_stats) return null;
    const { labels, box_stats, y_label } = chartData;

    const allVals = box_stats.flatMap((s) => [s.min, s.max]);
    const gMin = Math.min(...allVals);
    const gMax = Math.max(...allVals);
    const range = gMax - gMin || 1;

    const PAD_TOP = 20, PAD_BOT = 52, PAD_LEFT = 62, PAD_RIGHT = 20;
    const CHART_H = 320;
    const N = labels.length;
    const COL_W = Math.max(80, Math.min(160, Math.floor(540 / Math.max(N, 1))));
    const CHART_W = PAD_LEFT + N * COL_W + PAD_RIGHT;
    const PLOT_H = CHART_H - PAD_TOP - PAD_BOT;
    const BOX_HALF = Math.min(22, COL_W * 0.28);
    // In SVG, Y increases downward. Higher values appear at smaller Y coords.
    const toY = (v) => PAD_TOP + PLOT_H * (1 - (v - gMin) / range);
    const ticks = 5;
    const yTicks = Array.from({ length: ticks + 1 }, (_, i) => gMin + (range * i) / ticks);
    const fmtNum = (v) => {
      if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
      if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`;
      return v % 1 === 0 ? String(v) : v.toFixed(1);
    };

    return (
      <div style={{ overflowX: "auto", padding: "8px 0" }}>
        <svg width={CHART_W} height={CHART_H} style={{ display: "block", minWidth: "100%" }}>
          {/* Gridlines */}
          {yTicks.map((tick, i) => (
            <line key={i} x1={PAD_LEFT} y1={toY(tick)} x2={CHART_W - PAD_RIGHT} y2={toY(tick)} stroke="#f0eeea" strokeWidth={1} />
          ))}
          {/* Y axis */}
          <line x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={PAD_TOP + PLOT_H} stroke="#ccc" strokeWidth={1} />
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line x1={PAD_LEFT - 4} y1={toY(tick)} x2={PAD_LEFT} y2={toY(tick)} stroke="#aaa" strokeWidth={1} />
              <text x={PAD_LEFT - 8} y={toY(tick)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="#888">{fmtNum(tick)}</text>
            </g>
          ))}
          <text x={14} y={PAD_TOP + PLOT_H / 2} textAnchor="middle" fontSize={11} fill="#888"
            transform={`rotate(-90, 14, ${PAD_TOP + PLOT_H / 2})`}>{y_label}</text>

          {box_stats.map((stat, i) => {
            const cx = PAD_LEFT + (i + 0.5) * COL_W;
            const yQ1 = toY(stat.q1);   // lower on screen (larger Y)
            const yQ3 = toY(stat.q3);   // higher on screen (smaller Y)
            const yMed = toY(stat.median);
            const yMin = toY(stat.min);  // lowest on screen
            const yMax = toY(stat.max);  // highest on screen
            const capW = BOX_HALF * 0.6;
            const label = String(labels[i]);

            return (
              <g key={i}>
                {/* Upper whisker: from top of box (yQ3) to max (yMax, smaller Y) */}
                <line x1={cx} y1={yQ3} x2={cx} y2={yMax} stroke="#1c6e8c" strokeWidth={1.5} />
                <line x1={cx - capW} y1={yMax} x2={cx + capW} y2={yMax} stroke="#1c6e8c" strokeWidth={1.5} />
                {/* Lower whisker: from bottom of box (yQ1) to min (yMin, larger Y) */}
                <line x1={cx} y1={yQ1} x2={cx} y2={yMin} stroke="#1c6e8c" strokeWidth={1.5} />
                <line x1={cx - capW} y1={yMin} x2={cx + capW} y2={yMin} stroke="#1c6e8c" strokeWidth={1.5} />
                {/* IQR box: yQ3 is top edge, height = yQ1 - yQ3 (positive since yQ1 > yQ3) */}
                <rect x={cx - BOX_HALF} y={yQ3} width={BOX_HALF * 2} height={Math.max(1, yQ1 - yQ3)}
                  fill="rgba(28,110,140,0.13)" stroke="#1c6e8c" strokeWidth={1.5} rx={2} />
                {/* Median */}
                <line x1={cx - BOX_HALF} y1={yMed} x2={cx + BOX_HALF} y2={yMed} stroke="#1c6e8c" strokeWidth={2.5} />
                {/* Median label */}
                <text x={cx + BOX_HALF + 4} y={yMed} dominantBaseline="middle" fontSize={9} fill="#1c6e8c">{fmtNum(stat.median)}</text>
                {/* X label */}
                <text x={cx} y={PAD_TOP + PLOT_H + 18} textAnchor="middle" fontSize={11} fill="#666">
                  {label.length > 13 ? `${label.slice(0, 12)}…` : label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  };

  const renderChartInner = () => {
    if (!chartData) return null;
    if (chartType === "histogram") return renderHistogram();
    if (chartType === "stacked_bar") return renderStackedBar();
    if (chartType === "box_plot") return renderBoxPlot();

    const { labels, values, x_label, y_label } = chartData;

    if (chartType === "pie") {
      const slices = labels.slice(0, 10).map((l, i) => ({ name: String(l), value: values[i] ?? 0 }));
      return (
        <ResponsiveContainer width="100%" height={340}>
          <PieChart>
            <Pie data={slices} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={120}
              label={({ name, percent }) => `${name} (${(percent * 100).toFixed(1)}%)`} labelLine={false}>
              {slices.map((_, i) => (<Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />))}
            </Pie>
            <Tooltip formatter={(v) => [v.toLocaleString(), "Count"]} contentStyle={{ fontSize: 12, borderRadius: 4 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      );
    }

    const data = labels.map((l, i) => ({ label: String(l), value: values[i] ?? 0 }));

    if (chartType === "bar") {
      return (
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
            <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [typeof v === "number" ? v.toLocaleString() : v, y_label]} />
            <Bar dataKey="value" name={y_label} fill="#1c6e8c" radius={[3, 3, 0, 0]} maxBarSize={48} />
          </BarChart>
        </ResponsiveContainer>
      );
    }

    if (chartType === "line") {
      return (
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 72 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-soft)" }} angle={-38} textAnchor="end" interval={0} />
            <YAxis tick={{ fontSize: 11, fill: "var(--ink-soft)" }} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} formatter={(v) => [typeof v === "number" ? v.toLocaleString() : v, y_label]} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="value" name={y_label} stroke="#1c6e8c" strokeWidth={2.5} dot={{ r: 3, fill: "#1c6e8c" }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      );
    }

    if (chartType === "scatter") {
      const scatterData = labels.map((l, i) => ({ x: i, y: values[i] ?? 0, label: String(l) }));
      return (
        <ResponsiveContainer width="100%" height={340}>
          <ScatterChart margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="x" type="number" name={x_label} tick={{ fontSize: 11 }} tickFormatter={(v) => String(labels[v] ?? v).slice(0, 12)} />
            <YAxis dataKey="y" type="number" name={y_label} tick={{ fontSize: 11 }} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ payload }) => {
              if (!payload?.length) return null;
              const pt = payload[0]?.payload;
              if (!pt) return null;
              return (<div className="chart-scatter-tooltip"><div className="chart-scatter-tooltip-label">{pt.label}</div><div>{y_label}: {typeof pt.y === "number" ? pt.y.toLocaleString() : pt.y}</div></div>);
            }} />
            <Scatter name={y_label} data={scatterData} fill="#1c6e8c" opacity={0.8} />
          </ScatterChart>
        </ResponsiveContainer>
      );
    }

    return null;
  };

  return (
    <div className="chart-section smooth-expand">
      <div className="ledger-header">Visualise your data</div>

      <div className="chart-controls">
        <div className="chart-control-group">
          <label className="chart-label" htmlFor="chart-type-select">Chart type</label>
          <select id="chart-type-select" className="chart-select" value={chartType} onChange={handleChartTypeChange}>
            <option value="bar">Bar</option>
            <option value="line">Line</option>
            <option value="scatter">Scatter</option>
            <option value="pie">Pie</option>
            <option value="histogram">Histogram</option>
            <option value="stacked_bar">Stacked Bar</option>
            <option value="box_plot">Box Plot</option>
          </select>
        </div>

        <div className="chart-control-group">
          <label className="chart-label" htmlFor="chart-x-select">
            {isHistOrBox ? "Numeric column" : "X axis"}
          </label>
          <select id="chart-x-select" className="chart-select" value={xCol} onChange={(e) => setXCol(e.target.value)}>
            {(isHistOrBox ? (numCols.length > 0 ? numCols : allCols) : allCols).map((c) => (
              <option key={c.name} value={c.name}>{c.name}</option>
            ))}
          </select>
        </div>

        {needsY && (
          <div className="chart-control-group">
            <label className="chart-label" htmlFor="chart-y-select">Y axis</label>
            <select id="chart-y-select" className="chart-select" value={yCol} onChange={(e) => setYCol(e.target.value)}>
              {(numCols.length > 0 ? numCols : allCols).map((c) => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>
        )}

        {needsStack && (
          <div className="chart-control-group">
            <label className="chart-label" htmlFor="chart-stack-select">Stack by</label>
            <select id="chart-stack-select" className="chart-select" value={stackCol} onChange={(e) => setStackCol(e.target.value)}>
              {(catCols.length > 0 ? catCols : allCols).map((c) => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>
        )}

        {chartType === "box_plot" && catCols.length > 0 && (
          <div className="chart-control-group">
            <label className="chart-label" htmlFor="chart-group-select">Group by (optional)</label>
            <select id="chart-group-select" className="chart-select" value={yCol} onChange={(e) => setYCol(e.target.value)}>
              <option value="">— None —</option>
              {catCols.map((c) => (<option key={c.name} value={c.name}>{c.name}</option>))}
            </select>
          </div>
        )}

        {!isHistOrBox && chartType !== "stacked_bar" && (
          <div className="chart-control-group">
            <label className="chart-label" htmlFor="chart-agg-select">Aggregation</label>
            <select id="chart-agg-select" className="chart-select" value={agg} onChange={(e) => setAgg(e.target.value)}
              disabled={chartType === "scatter" || chartType === "pie"}>
              <option value="count">Count</option>
              <option value="sum">Sum</option>
              <option value="mean">Mean</option>
            </select>
          </div>
        )}

        <button id="chart-generate-btn" className="apply-button chart-go-btn"
          onClick={() => doFetch()}
          disabled={loading || !xCol || (needsY && !yCol) || (needsStack && !stackCol)}>
          {loading ? "Loading…" : "Generate chart"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="chart-container">
        {loading && (
          <div className="chart-loading">
            <div className="ledger-loading-track" style={{ width: 200 }}>
              <div className="ledger-loading-bar" />
            </div>
            <span className="chart-loading-label">Generating chart…</span>
          </div>
        )}
        {!loading && !chartData && (
          <div className="chart-empty">
            Select columns and click <strong>Generate chart</strong>
          </div>
        )}
        {!loading && chartData && renderChartInner()}
      </div>

      {chartData && !loading && (
        <div className="chart-meta">
          {chartData.group_count} groups&nbsp;·&nbsp;{chartData.row_count?.toLocaleString()} rows
          &nbsp;·&nbsp;{chartData.x_label}{chartData.y_label && chartData.y_label !== "Count" ? ` → ${chartData.y_label}` : ""}
        </div>
      )}
    </div>
  );
}

function PreviewPanel({ previewData, onConfirm, onCancel, loading }) {
  if (!previewData) return null;

  const { original_row_count, cleaned_row_count, column_diffs, step_log } = previewData;

  return (
    <div className="preview-panel smooth-expand">
      <div className="preview-header">
        <div className="preview-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          Preview — review before applying
        </div>
        <button className="preview-close-btn" onClick={onCancel} title="Dismiss preview">✕</button>
      </div>

      {/* Scrollable body — everything between header and the sticky footer */}
      <div className="preview-body">
        <div className="preview-summary-bar">
          <span className="preview-summary-label">Rows</span>
          <span className="preview-summary-val">{original_row_count?.toLocaleString()}</span>
          <span className="preview-summary-arrow">→</span>
          <span className={`preview-summary-val${cleaned_row_count !== original_row_count ? " changed" : ""}`}>
            {cleaned_row_count?.toLocaleString()}
          </span>
          {cleaned_row_count !== original_row_count && (
            <span className="preview-summary-delta">
              ({original_row_count - cleaned_row_count} removed)
            </span>
          )}
        </div>

        {column_diffs && column_diffs.length > 0 ? (
          <div className="preview-diffs">
            {column_diffs
              .filter((d) => d.column !== "(row count)")
              .map((diff, idx) => (
                <div className="preview-column-diff" key={idx}>
                  <div className="preview-col-header">
                    <span className="preview-col-name">{diff.column}</span>
                    {diff.summary && <span className="preview-col-summary">{diff.summary}</span>}
                    {diff.note && <span className="preview-col-note">{diff.note}</span>}
                  </div>

                  {diff.before && Object.keys(diff.before).length > 0 && (
                    <div className="preview-value-table">
                      <div className="preview-value-header">
                        <span>Value</span>
                        <span>Before</span>
                        <span>After</span>
                        <span>Change</span>
                      </div>
                      {(() => {
                        const allKeys = new Set([
                          ...Object.keys(diff.before || {}),
                          ...Object.keys(diff.after || {}),
                        ]);
                        return [...allKeys].sort().map((key) => {
                          const before = diff.before?.[key] ?? 0;
                          const after = diff.after?.[key] ?? 0;
                          const delta = after - before;
                          const isRemoved = after === 0 && before > 0;
                          const isNew = before === 0 && after > 0;
                          return (
                            <div
                              className={`preview-value-row${
                                isRemoved ? " removed" : isNew ? " added" : delta !== 0 ? " changed" : ""
                              }`}
                              key={key}
                            >
                              <span className="preview-val-name" title={key}>{key}</span>
                              <span className="preview-val-count">{before || "—"}</span>
                              <span className="preview-val-count">{after || "—"}</span>
                              <span className={`preview-val-delta${delta > 0 ? " pos" : delta < 0 ? " neg" : ""}`}>
                                {delta === 0 ? "" : delta > 0 ? `+${delta}` : delta}
                              </span>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  )}
                </div>
              ))}
          </div>
        ) : (
          <div className="preview-no-changes">No value-level changes detected. Only structural operations will run.</div>
        )}

        {step_log && step_log.length > 0 && (
          <div className="preview-step-log">
            <div className="preview-step-log-title">Operations to execute</div>
            {step_log.map((item, idx) => (
              <div className="preview-step-row" key={idx}>
                <span className="log-action">{item.action}</span>
                <span className="log-desc">{item.description}</span>
              </div>
            ))}
          </div>
        )}
      </div>{/* end .preview-body */}

      <div className="preview-actions">
        <button
          className="apply-button confirm"
          onClick={onConfirm}
          disabled={loading}
        >
          {loading ? "Applying…" : "Confirm & Apply"}
        </button>
        <button
          className="apply-button cancel"
          onClick={onCancel}
          disabled={loading}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function CategoricalReviewCard({
  column,
  distinctValues = {},
  variantConfidences = {},
  groups = [],
  mapping = {},
  totalRows = 0,
  onValueChange,
}) {
  const canonicalTargets = Array.from(
    new Set([
      ...groups.map((g) => g.canonical).filter(Boolean),
      ...Object.values(mapping).filter((v) => v && v !== "(keep as-is)"),
    ])
  );

  const [customInputs, setCustomInputs] = useState({});

  const sortedDistinct = Object.entries(distinctValues).sort((a, b) => b[1] - a[1]);

  return (
    <div className="manual-review-card">
      <div className="manual-review-header">
        <div className="manual-review-title-group">
          <span className="manual-review-title">{column}</span>
          <span className="manual-review-badge">{sortedDistinct.length} distinct values</span>
        </div>
        <div className="cat-card-hint">
          {groups.length > 0
            ? `${groups.length} suggested target group${groups.length > 1 ? "s" : ""}`
            : "Review and map values"}
        </div>
      </div>

      <div className="cat-review-table">
        <div className="cat-table-header">
          <span>Distinct Raw Value</span>
          <span>Count</span>
          <span>Detection Type</span>
          <span>Assign Canonical Group</span>
        </div>

        {sortedDistinct.map(([rawVal, count]) => {
          const conf = variantConfidences[rawVal] || (canonicalTargets.includes(rawVal) ? "canonical" : "none");
          const currentTarget = mapping[rawVal] || rawVal;
          const isCustom = customInputs[rawVal] !== undefined;
          const pct = totalRows > 0 ? ((count / totalRows) * 100).toFixed(1) : null;

          return (
            <div className="cat-table-row" key={rawVal}>
              <div className="td-val">
                <span className="raw-val-chip" title={rawVal}>
                  {rawVal === "" ? "— (empty)" : rawVal}
                </span>
              </div>

              <div className="td-count">
                <span className="count-num">{count.toLocaleString()}</span>
                {pct && <span className="count-pct">({pct}%)</span>}
              </div>

              <div className="td-conf">
                {canonicalTargets.includes(rawVal) ? (
                  <span className="conf-pill canonical">Canonical</span>
                ) : conf === "low" ? (
                  <span className="conf-pill low" title="Abbreviation or initial detected — defaults to keep original">
                    Abbreviation (low conf)
                  </span>
                ) : conf === "high" ? (
                  <span className="conf-pill high">Exact / Typo</span>
                ) : (
                  <span className="conf-pill neutral">Original</span>
                )}
              </div>

              <div className="td-target">
                {isCustom ? (
                  <div className="custom-input-group">
                    <input
                      type="text"
                      className="custom-target-input"
                      placeholder="Enter canonical target..."
                      value={customInputs[rawVal]}
                      onChange={(e) => {
                        const val = e.target.value;
                        setCustomInputs((prev) => ({ ...prev, [rawVal]: val }));
                        onValueChange(column, rawVal, val || rawVal);
                      }}
                    />
                    <button
                      type="button"
                      className="custom-cancel-btn"
                      onClick={() => {
                        setCustomInputs((prev) => {
                          const next = { ...prev };
                          delete next[rawVal];
                          return next;
                        });
                        onValueChange(column, rawVal, rawVal);
                      }}
                      title="Cancel custom target"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <select
                    className={`cat-target-select${currentTarget !== rawVal ? " mapped" : ""}`}
                    value={currentTarget}
                    onChange={(e) => {
                      const selected = e.target.value;
                      if (selected === "__custom__") {
                        setCustomInputs((prev) => ({ ...prev, [rawVal]: "" }));
                      } else {
                        onValueChange(column, rawVal, selected);
                      }
                    }}
                  >
                    <option value={rawVal}>Keep original: "{rawVal}"</option>
                    {canonicalTargets
                      .filter((c) => c !== rawVal)
                      .map((c) => (
                        <option key={c} value={c}>
                          Merge into: "{c}"
                        </option>
                      ))}
                    <option value="__custom__">+ Custom canonical group...</option>
                  </select>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StructuralReviewList({ suggestions = [], selectedIds, onToggle }) {
  if (suggestions.length === 0) return null;

  return (
    <div className="structural-review-section">
      <div className="structural-header">
        <span className="structural-title">Data Quality & Structural Fixes</span>
        <span className="structural-subtitle">
          Missing value imputations, outlier filtering, numeric coercion, etc.
        </span>
      </div>

      <div className="structural-list">
        {suggestions.map((s) => {
          const isChecked = selectedIds.has(s.id);
          return (
            <label className={`structural-row${isChecked ? " selected" : ""}`} key={s.id}>
              <input
                type="checkbox"
                checked={isChecked}
                onChange={() => onToggle(s.id)}
              />
              <div className="structural-info">
                <span className="structural-action">{s.action}</span>
                <span className="structural-desc">{s.description}</span>
              </div>
              <span className={`severity-badge ${s.severity}`}>{s.severity}</span>
            </label>
          );
        })}
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
  const [manualMappings, setManualMappings] = useState({});
  const [selectedStructuralIds, setSelectedStructuralIds] = useState(new Set());
  const [cleaningLoading, setCleaningLoading] = useState(false);
  const [cleaningError, setCleaningError] = useState(null);
  const [cleaningResult, setCleaningResult] = useState(null);
  const [downloadingFormat, setDownloadingFormat] = useState(null);

  // Preview-before-apply state
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Last chart generated — passed to ChatBot for visualization-aware replies
  const [lastChartData, setLastChartData] = useState(null);

  // Steps override — set when chat proposes an action that we want to apply.
  const [chatPendingSteps, setChatPendingSteps] = useState(null);

  const handleFile = async (file) => {
    setLoading(true);
    setError(null);
    setCleaningResult(null);
    setCleaningError(null);
    setSuggestions([]);
    setManualMappings({});
    setSelectedStructuralIds(new Set());

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

      // Initialize manualMappings for categorical columns
      const initMappings = {};
      list.forEach((s) => {
        if (s.action === "standardize_category") {
          const col = s.params?.column;
          const dv = s.params?.distinct_values || {};
          const aiMapping = s.params?.mapping || {};
          const confidences = s.params?.variant_confidences || {};
          if (col) {
            initMappings[col] = {};
            Object.keys(dv).forEach((val) => {
              // High-confidence exact/typo variants default to AI recommendation.
              // Low-confidence abbreviations default to self (keep original / unmerged).
              if (confidences[val] === "high" && aiMapping[val]) {
                initMappings[col][val] = aiMapping[val];
              } else {
                initMappings[col][val] = val;
              }
            });
          }
        }
      });
      setManualMappings(initMappings);

      // Checked by default for high and medium severity structural issues
      const structDefaults = new Set(
        list
          .filter(
            (s) =>
              s.action !== "standardize_category" &&
              (s.severity === "high" || s.severity === "medium")
          )
          .map((s) => s.id)
      );
      setSelectedStructuralIds(structDefaults);
    } catch (err) {
      setCleaningError(`Could not load suggestions: ${err.message}`);
    } finally {
      setSuggestionsLoading(false);
    }
  };

  const handleMappingChange = (column, rawVal, targetVal) => {
    setManualMappings((prev) => ({
      ...prev,
      [column]: {
        ...(prev[column] || {}),
        [rawVal]: targetVal,
      },
    }));
  };

  const toggleStructuralSuggestion = (id) => {
    setSelectedStructuralIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const _buildApprovedSteps = () => {
    const steps = [];

    // 1. Categorical standardize steps from user manual mappings
    Object.entries(manualMappings).forEach(([col, valMap]) => {
      const mapping = {};
      Object.entries(valMap).forEach(([rawVal, target]) => {
        if (target && target !== rawVal && target !== "(keep as-is)") {
          mapping[rawVal] = target;
        }
      });
      if (Object.keys(mapping).length > 0) {
        steps.push({
          action: "standardize_category",
          params: { column: col, mapping },
          description: `Standardize ${Object.keys(mapping).length} value(s) in '${col}'`,
          severity: "medium",
        });
      }
    });

    // 2. Structural steps
    suggestions
      .filter((s) => s.action !== "standardize_category" && selectedStructuralIds.has(s.id))
      .forEach((s) => {
        steps.push({
          action: s.action,
          params: s.params,
          description: s.description,
          severity: s.severity,
        });
      });

    return steps;
  };

  const handlePreview = async () => {
    if (!report?.dataset_id) return;
    setPreviewLoading(true);
    setCleaningError(null);
    setPreviewData(null);
    setChatPendingSteps(null);

    try {
      const steps = _buildApprovedSteps();
      if (steps.length === 0) {
        setCleaningError("No modifications or fixes are currently selected to preview.");
        return;
      }
      const preview = await previewPipeline(report.dataset_id, steps);
      setPreviewData(preview);
    } catch (err) {
      setCleaningError(`Preview failed: ${err.message}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleChatPreviewAction = (previewResult, steps) => {
    setChatPendingSteps(steps);
    setPreviewData(previewResult);
    setCleaningError(null);
  };

  const handleConfirmApply = async () => {
    if (!report?.dataset_id) return;
    setCleaningLoading(true);
    setCleaningError(null);

    const stepsToApply = chatPendingSteps !== null ? chatPendingSteps : _buildApprovedSteps();

    try {
      await savePipeline(report.dataset_id, stepsToApply);
      const res = await applyPipeline(report.dataset_id);
      setCleaningResult(res);
      setPreviewData(null);
      setChatPendingSteps(null);
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
    setManualMappings({});
    setSelectedStructuralIds(new Set());
    setCleaningResult(null);
    setCleaningError(null);
    setPreviewData(null);
    setChatPendingSteps(null);
    setLastChartData(null);
    setError(null);
  };

  const displayReport = report;

  // Separate suggestions
  const categoricalSuggestions = suggestions.filter((s) => s.action === "standardize_category");
  const structuralSuggestions = suggestions.filter((s) => s.action !== "standardize_category");

  // Calculate count of remapped values
  const totalRemappedValues = Object.values(manualMappings).reduce((acc, valMap) => {
    return (
      acc +
      Object.entries(valMap).filter(([k, v]) => v && v !== k && v !== "(keep as-is)").length
    );
  }, 0);

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

          {/* --- Cleaning suggestions / manual per-column review section --- */}
          <div className="cleaning-section">
            <div className="ledger-header">Review & Standardize Values</div>
            {suggestionsLoading ? (
              <div className="loading-note">Analyzing cleaning rules & category groupings…</div>
            ) : suggestions.length === 0 ? (
              <div className="clean-note">No automated cleaning issues detected. Your data looks good!</div>
            ) : (
              <div className="manual-review-scroll-container smooth-expand">
                <div className="manual-review-body">
                  {/* Categorical per-column review cards */}
                  {categoricalSuggestions.map((s) => {
                    const col = s.params?.column;
                    return (
                      <CategoricalReviewCard
                        key={s.id}
                        column={col}
                        distinctValues={s.params?.distinct_values || {}}
                        variantConfidences={s.params?.variant_confidences || {}}
                        groups={s.params?.groups || []}
                        mapping={manualMappings[col] || {}}
                        totalRows={displayReport.row_count || 0}
                        onValueChange={handleMappingChange}
                      />
                    );
                  })}

                  {/* Structural suggestions checklist */}
                  <StructuralReviewList
                    suggestions={structuralSuggestions}
                    selectedIds={selectedStructuralIds}
                    onToggle={toggleStructuralSuggestion}
                  />
                </div>

                {/* Sticky footer at the bottom of the review container */}
                <div className="manual-review-footer">
                  <div className="manual-review-summary">
                    {categoricalSuggestions.length > 0 && (
                      <span>
                        {categoricalSuggestions.length} column{categoricalSuggestions.length > 1 ? "s" : ""} (
                        {totalRemappedValues} value{totalRemappedValues !== 1 ? "s" : ""} remapped)
                      </span>
                    )}
                    {categoricalSuggestions.length > 0 && structuralSuggestions.length > 0 && (
                      <span> · </span>
                    )}
                    {structuralSuggestions.length > 0 && (
                      <span>{selectedStructuralIds.size} structural fix{selectedStructuralIds.size !== 1 ? "es" : ""} selected</span>
                    )}
                  </div>

                  <button
                    id="apply-all-changes-btn"
                    className="apply-button"
                    onClick={handlePreview}
                    disabled={
                      previewLoading ||
                      (totalRemappedValues === 0 && selectedStructuralIds.size === 0)
                    }
                  >
                    {previewLoading ? "Generating preview…" : "Apply all changes"}
                  </button>
                </div>
              </div>
            )}

            {cleaningError && <div className="error-banner">{cleaningError}</div>}

            {previewData && !cleaningResult && (
              <PreviewPanel
                previewData={previewData}
                onConfirm={handleConfirmApply}
                onCancel={() => { setPreviewData(null); setChatPendingSteps(null); }}
                loading={cleaningLoading}
              />
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

          {/* --- Chart Builder section --- */}
          <ChartBuilder
            datasetId={displayReport.dataset_id}
            columns={displayReport.columns || []}
            onChartDataFetched={setLastChartData}
          />

          <button className="reset-link" onClick={resetAll}>
            ← Profile another file
          </button>
        </div>
      )}

      <ChatBot
        datasetId={displayReport?.dataset_id}
        onPreviewChatAction={handleChatPreviewAction}
        chartContext={lastChartData}
      />
    </div>
  );
}

