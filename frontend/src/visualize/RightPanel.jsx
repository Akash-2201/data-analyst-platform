/**
 * frontend/src/visualize/RightPanel.jsx
 * Right panel (300px): DATA, FORMAT, and FILTERS tabs for the selected tile.
 */

import React, { useState } from "react";
import { useDashboard } from "./dashboardContext";
import { PALETTES } from "./constants";

export function RightPanel({ columns = [], isOpen = false }) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages, selectedTileIds, mode } = present;
  const [activeTab, setActiveTab] = useState("data"); // "data" | "format" | "filters"

  const activePage = pages.find((p) => p.id === activePageId) || pages[0];
  const selectedTile = activePage?.tiles.find((t) => selectedTileIds?.includes(t.id));

  const updateTile = (updates) => {
    if (!selectedTile) return;
    dispatch({
      type: "UPDATE_TILE",
      payload: { tileId: selectedTile.id, updates },
    });
  };

  const updateChartConfig = (cfgUpdates) => {
    if (!selectedTile) return;
    updateTile({
      chartConfig: { ...selectedTile.chartConfig, ...cfgUpdates },
    });
  };

  const updateFormat = (fmtUpdates) => {
    if (!selectedTile) return;
    updateTile({
      format: { ...selectedTile.format, ...fmtUpdates },
    });
  };

  const colNames = (columns || []).map((c) => (typeof c === "string" ? c : c.name));

  return (
    <aside className={`rpt-right-panel ${isOpen ? "drawer-open" : ""}`}>
      {/* Tab Navigation */}
      <div className="rpt-right-panel-tabs">
        <button
          type="button"
          className={`rpt-right-tab-btn ${activeTab === "data" ? "active" : ""}`}
          onClick={() => setActiveTab("data")}
        >
          DATA
        </button>
        <button
          type="button"
          className={`rpt-right-tab-btn ${activeTab === "format" ? "active" : ""}`}
          onClick={() => setActiveTab("format")}
        >
          FORMAT
        </button>
        <button
          type="button"
          className={`rpt-right-tab-btn ${activeTab === "filters" ? "active" : ""}`}
          onClick={() => setActiveTab("filters")}
        >
          FILTERS {activePage?.filters?.length ? `(${activePage.filters.length})` : ""}
        </button>
      </div>

      <div className="rpt-right-panel-content">
        {/* DATA TAB */}
        {activeTab === "data" && (
          <div>
            {!selectedTile ? (
              <div className="rpt-empty-state-hint">
                <span>📊</span>
                <span>Select a visual on the canvas to configure data fields.</span>
              </div>
            ) : selectedTile.kind === "text" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ fontSize: 11, color: "#a1a1aa" }}>Text Content</label>
                <textarea
                  value={selectedTile.text?.value || ""}
                  onChange={(e) =>
                    updateTile({ text: { ...selectedTile.text, value: e.target.value } })
                  }
                  rows={4}
                  style={{
                    background: "#18181b",
                    border: "1px solid #27272a",
                    color: "#f4f4f5",
                    padding: 8,
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                />
              </div>
            ) : selectedTile.kind === "slicer" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label style={{ fontSize: 11, color: "#a1a1aa" }}>Slicer Column</label>
                <select
                  value={selectedTile.slicer?.col || ""}
                  onChange={(e) =>
                    updateTile({ slicer: { ...selectedTile.slicer, col: e.target.value } })
                  }
                  style={{
                    background: "#18181b",
                    border: "1px solid #27272a",
                    color: "#f4f4f5",
                    padding: "6px 8px",
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                >
                  <option value="">(Select column)</option>
                  {colNames.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* X Axis */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>X-Axis / Category</label>
                  <select
                    value={selectedTile.chartConfig?.xCol || ""}
                    onChange={(e) => updateChartConfig({ xCol: e.target.value })}
                    style={{
                      width: "100%",
                      background: "#18181b",
                      border: "1px solid #27272a",
                      color: "#f4f4f5",
                      padding: "6px 8px",
                      borderRadius: 6,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  >
                    <option value="">(Select X column)</option>
                    {colNames.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                {/* Y Axis */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Y-Axis / Value</label>
                  <select
                    value={selectedTile.chartConfig?.yCol || ""}
                    onChange={(e) => updateChartConfig({ yCol: e.target.value })}
                    style={{
                      width: "100%",
                      background: "#18181b",
                      border: "1px solid #27272a",
                      color: "#f4f4f5",
                      padding: "6px 8px",
                      borderRadius: 6,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  >
                    <option value="">(Optional / None)</option>
                    {colNames.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                {/* Aggregation */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Aggregation</label>
                  <select
                    value={selectedTile.chartConfig?.agg || "sum"}
                    onChange={(e) => updateChartConfig({ agg: e.target.value })}
                    style={{
                      width: "100%",
                      background: "#18181b",
                      border: "1px solid #27272a",
                      color: "#f4f4f5",
                      padding: "6px 8px",
                      borderRadius: 6,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  >
                    <option value="sum">SUM</option>
                    <option value="avg">AVERAGE</option>
                    <option value="count">COUNT</option>
                    <option value="min">MIN</option>
                    <option value="max">MAX</option>
                    <option value="median">MEDIAN</option>
                  </select>
                </div>

                {/* Sort */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Sort</label>
                  <select
                    value={selectedTile.chartConfig?.sort || "none"}
                    onChange={(e) => updateChartConfig({ sort: e.target.value })}
                    style={{
                      width: "100%",
                      background: "#18181b",
                      border: "1px solid #27272a",
                      color: "#f4f4f5",
                      padding: "6px 8px",
                      borderRadius: 6,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  >
                    <option value="none">None (Default)</option>
                    <option value="desc">Descending</option>
                    <option value="asc">Ascending</option>
                  </select>
                </div>

                {/* Interaction Mode */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Interaction</label>
                  <select
                    value={selectedTile.interaction || "filter"}
                    onChange={(e) => updateTile({ interaction: e.target.value })}
                    style={{
                      width: "100%",
                      background: "#18181b",
                      border: "1px solid #27272a",
                      color: "#f4f4f5",
                      padding: "6px 8px",
                      borderRadius: 6,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  >
                    <option value="filter">Filter other visuals</option>
                    <option value="highlight">Highlight non-matching</option>
                    <option value="none">None (Ignore)</option>
                  </select>
                </div>
              </div>
            )}
          </div>
        )}

        {/* FORMAT TAB */}
        {activeTab === "format" && (
          <div>
            {!selectedTile ? (
              <div className="rpt-empty-state-hint">
                <span>🎨</span>
                <span>Select a visual on the canvas to format its appearance.</span>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* Title */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Visual Title</label>
                  <input
                    type="text"
                    value={selectedTile.title || ""}
                    onChange={(e) => updateTile({ title: e.target.value })}
                    style={{
                      width: "100%",
                      background: "#18181b",
                      border: "1px solid #27272a",
                      color: "#f4f4f5",
                      padding: "6px 8px",
                      borderRadius: 6,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  />
                </div>

                {/* Dimensions (px) */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label style={{ fontSize: 10, color: "#71717a" }}>Width (px)</label>
                    <input
                      type="number"
                      value={selectedTile.w}
                      onChange={(e) =>
                        updateTile({ w: parseInt(e.target.value, 10) || selectedTile.w })
                      }
                      style={{
                        width: "100%",
                        background: "#18181b",
                        border: "1px solid #27272a",
                        color: "#f4f4f5",
                        padding: "4px 6px",
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, color: "#71717a" }}>Height (px)</label>
                    <input
                      type="number"
                      value={selectedTile.h}
                      onChange={(e) =>
                        updateTile({ h: parseInt(e.target.value, 10) || selectedTile.h })
                      }
                      style={{
                        width: "100%",
                        background: "#18181b",
                        border: "1px solid #27272a",
                        color: "#f4f4f5",
                        padding: "4px 6px",
                        borderRadius: 4,
                        fontSize: 11,
                      }}
                    />
                  </div>
                </div>

                {/* Color Palette */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Color Palette</label>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 6, marginTop: 4 }}>
                    {Object.keys(PALETTES).map((pal) => (
                      <button
                        key={pal}
                        type="button"
                        className={`rpt-btn ${selectedTile.format?.palette === pal ? "rpt-btn-primary" : ""}`}
                        style={{ fontSize: 11, textTransform: "capitalize", padding: "4px 6px" }}
                        onClick={() => updateFormat({ palette: pal })}
                      >
                        {pal}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Background & Border */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Background & Border</label>
                  <div style={{ display: "flex", gap: 8, marginTop: 4, alignItems: "center" }}>
                    <input
                      type="color"
                      value={selectedTile.format?.bg || "#18181b"}
                      onChange={(e) => updateFormat({ bg: e.target.value })}
                      style={{ background: "transparent", border: "none", cursor: "pointer", width: 32, height: 28 }}
                    />
                    <span style={{ fontSize: 11, color: "#71717a" }}>Card BG</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* FILTERS TAB */}
        {activeTab === "filters" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ fontSize: 11, color: "#a1a1aa" }}>
              Page Filters for <strong>{activePage.name}</strong>
            </div>
            {/* Filter selection UI will be fully wired in Step 5 */}
            <div style={{ fontSize: 12, color: "#71717a" }}>
              {activePage?.filters?.length === 0
                ? "No filters applied to this page yet."
                : `${activePage.filters.length} active page filter(s).`}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
