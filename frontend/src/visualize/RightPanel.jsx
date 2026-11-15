/**
 * frontend/src/visualize/RightPanel.jsx
 * Right panel (300px): DATA, FORMAT, and FILTERS tabs for the selected tile.
 */

import React, { useState, useEffect, useRef, useMemo } from "react";
import { useDashboard } from "./dashboardContext";
import { PALETTES } from "./constants";
import { FilterTab } from "./FilterTab";
import { classifyColumn } from "./utils";

export function RightPanel({ columns = [], isOpen = false, isCollapsed = false }) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages, selectedTileIds, mode } = present;
  const [activeTab, setActiveTab] = useState("data");

  const prevSelectedRef = useRef(selectedTileIds);
  useEffect(() => {
    if (selectedTileIds?.length > 0 && selectedTileIds[0] !== prevSelectedRef.current?.[0]) {
      setActiveTab("data");
    }
    prevSelectedRef.current = selectedTileIds;
  }, [selectedTileIds]);

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

  const colNames = useMemo(() => (columns || []).map((c) => (typeof c === "string" ? c : c.name)), [columns]);

  // Column role filtering for dropdowns
  const classifiedCols = useMemo(() => (columns || []).map(classifyColumn), [columns]);
  const measureCols = useMemo(() => {
    const list = classifiedCols.filter((c) => c.group === "NUMERICAL").map((c) => c.name);
    return list.length > 0 ? list : colNames;
  }, [classifiedCols, colNames]);
  const dateCols = useMemo(() => {
    const list = classifiedCols.filter((c) => c.group === "DATE").map((c) => c.name);
    return list.length > 0 ? list : colNames;
  }, [classifiedCols, colNames]);
  const categoryCols = useMemo(() => {
    const list = classifiedCols
      .filter((c) => c.group === "TEXT" || c.group === "TEXT/Identifier" || c.group === "LOCATION" || c.group === "DATE")
      .map((c) => c.name);
    return list.length > 0 ? list : colNames;
  }, [classifiedCols, colNames]);

  return (
    <aside className={`rpt-right-panel ${isOpen ? "drawer-open" : ""} ${isCollapsed ? "collapsed" : ""}`}>
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
                {/* Visual Type indicator */}
                <div style={{ fontSize: 11, color: "#8b5cf6", fontWeight: 600, textTransform: "uppercase" }}>
                  {(selectedTile.chartConfig?.chartType || "bar").replace("_", " ")} Visual Configuration
                </div>

                {/* X Axis / Category */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>
                    {selectedTile.chartConfig?.chartType === "scatter"
                      ? "X-Axis / Measure"
                      : selectedTile.chartConfig?.chartType === "line" || selectedTile.chartConfig?.chartType === "area"
                      ? "Date / X-Axis"
                      : "X-Axis / Category"}
                  </label>
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
                    <option value="">(Select column)</option>
                    {(selectedTile.chartConfig?.chartType === "scatter"
                      ? measureCols
                      : selectedTile.chartConfig?.chartType === "line"
                      ? (dateCols.length > 0 ? dateCols : categoryCols)
                      : categoryCols
                    ).map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                {/* Y Axis / Metric */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>
                    {selectedTile.chartConfig?.chartType === "kpi"
                      ? "Metric (Measure)"
                      : "Y-Axis / Metric (Measure)"}
                  </label>
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
                    <option value="">(Optional / Count-based)</option>
                    {measureCols.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                {/* Stack / Legend Column (for bar/stacked) */}
                {selectedTile.chartConfig?.chartType !== "kpi" && selectedTile.chartConfig?.chartType !== "scatter" && (
                  <div>
                    <label style={{ fontSize: 11, color: "#a1a1aa" }}>Legend / Stack Column</label>
                    <select
                      value={selectedTile.chartConfig?.stackCol || ""}
                      onChange={(e) => updateChartConfig({ stackCol: e.target.value })}
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
                      <option value="">(None)</option>
                      {categoryCols.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                )}

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

                {/* Date Grain (if Line or Area or Date) */}
                {(selectedTile.chartConfig?.chartType === "line" ||
                  selectedTile.chartConfig?.chartType === "area" ||
                  dateCols.includes(selectedTile.chartConfig?.xCol)) && (
                  <div>
                    <label style={{ fontSize: 11, color: "#a1a1aa" }}>Date Grain</label>
                    <select
                      value={selectedTile.chartConfig?.dateGrain || "month"}
                      onChange={(e) => updateChartConfig({ dateGrain: e.target.value })}
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
                      <option value="day">Day</option>
                      <option value="month">Month</option>
                      <option value="year">Year</option>
                    </select>
                  </div>
                )}

                {/* Interaction Mode */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Interaction Setting</label>
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
                    <option value="none">None (Ignore cross-filtering)</option>
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
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div className="rpt-section-title" style={{ padding: 0, color: "#a78bfa" }}>
                  📄 Page Settings ({activePage?.name || "Page"})
                </div>

                {/* Page Size Presets */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Page Size Preset</label>
                  <select
                    value={
                      activePage?.size?.w === 1920 && activePage?.size?.h === 1080 ? "16:9-1080" :
                      activePage?.size?.w === 1280 && activePage?.size?.h === 720 ? "16:9-720" :
                      activePage?.size?.w === 2560 && activePage?.size?.h === 1440 ? "16:9-1440" :
                      activePage?.size?.w === 1600 && activePage?.size?.h === 1200 ? "4:3-1200" :
                      activePage?.size?.w === 1080 && activePage?.size?.h === 1920 ? "tall-1080" : "custom"
                    }
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "16:9-1080") dispatch({ type: "UPDATE_PAGE_SIZE", payload: { w: 1920, h: 1080 } });
                      else if (val === "16:9-720") dispatch({ type: "UPDATE_PAGE_SIZE", payload: { w: 1280, h: 720 } });
                      else if (val === "16:9-1440") dispatch({ type: "UPDATE_PAGE_SIZE", payload: { w: 2560, h: 1440 } });
                      else if (val === "4:3-1200") dispatch({ type: "UPDATE_PAGE_SIZE", payload: { w: 1600, h: 1200 } });
                      else if (val === "tall-1080") dispatch({ type: "UPDATE_PAGE_SIZE", payload: { w: 1080, h: 1920 } });
                    }}
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
                    <option value="16:9-1080">16:9 (1920 × 1080) Full HD - Default</option>
                    <option value="16:9-720">16:9 (1280 × 720) HD</option>
                    <option value="16:9-1440">16:9 (2560 × 1440) 2K QHD</option>
                    <option value="4:3-1200">4:3 (1600 × 1200)</option>
                    <option value="tall-1080">Tall (1080 × 1920) Mobile / Story</option>
                    <option value="custom">Custom Size</option>
                  </select>
                </div>

                {/* Custom Width & Height */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label style={{ fontSize: 10, color: "#71717a" }}>Width (px)</label>
                    <input
                      type="number"
                      min={640}
                      max={4000}
                      value={activePage?.size?.w || 1920}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        if (!isNaN(val)) dispatch({ type: "UPDATE_PAGE_SIZE", payload: { w: val } });
                      }}
                      style={{
                        width: "100%",
                        background: "#18181b",
                        border: "1px solid #27272a",
                        color: "#f4f4f5",
                        padding: "4px 6px",
                        borderRadius: 4,
                        fontSize: 11,
                        marginTop: 2,
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, color: "#71717a" }}>Height (px)</label>
                    <input
                      type="number"
                      min={360}
                      max={4000}
                      value={activePage?.size?.h || 1080}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        if (!isNaN(val)) dispatch({ type: "UPDATE_PAGE_SIZE", payload: { h: val } });
                      }}
                      style={{
                        width: "100%",
                        background: "#18181b",
                        border: "1px solid #27272a",
                        color: "#f4f4f5",
                        padding: "4px 6px",
                        borderRadius: 4,
                        fontSize: 11,
                        marginTop: 2,
                      }}
                    />
                  </div>
                </div>

                {/* Auto-grow Height Toggle */}
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "#d4d4d8", cursor: "pointer", marginTop: 4 }}>
                  <input
                    type="checkbox"
                    checked={activePage?.autoGrowHeight || false}
                    onChange={(e) => dispatch({ type: "UPDATE_PAGE_SIZE", payload: { autoGrowHeight: e.target.checked } })}
                    style={{ accentColor: "#8b5cf6" }}
                  />
                  <span>Auto-grow height as tiles expand</span>
                </label>

                {present.lastPageResizeMovedCount > 0 && (
                  <div style={{ fontSize: 10, color: "#f59e0b", background: "rgba(245, 158, 11, 0.1)", padding: "6px 8px", borderRadius: 4 }}>
                    ⚠️ {present.lastPageResizeMovedCount} tile(s) repositioned to fit inside new page bounds.
                  </div>
                )}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {/* General Title */}
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

                {/* Position & Dimensions (px) */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label style={{ fontSize: 10, color: "#71717a" }}>X (px)</label>
                    <input
                      type="number"
                      value={selectedTile.x}
                      onChange={(e) =>
                        updateTile({ x: parseInt(e.target.value, 10) || 0 })
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
                    <label style={{ fontSize: 10, color: "#71717a" }}>Y (px)</label>
                    <input
                      type="number"
                      value={selectedTile.y}
                      onChange={(e) =>
                        updateTile({ y: parseInt(e.target.value, 10) || 0 })
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

                {/* Title Alignment & Size */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>Title Align & Size</label>
                  <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    {["left", "center", "right"].map((align) => (
                      <button
                        key={align}
                        type="button"
                        className={`rpt-btn ${selectedTile.format?.titleAlign === align ? "rpt-btn-primary" : ""}`}
                        style={{ fontSize: 11, flex: 1, textTransform: "capitalize", padding: "4px" }}
                        onClick={() => updateFormat({ titleAlign: align })}
                      >
                        {align}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Show Toggles: Legend, Data Labels */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#d4d4d8", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={selectedTile.format?.showLegend !== false}
                      onChange={(e) => updateFormat({ showLegend: e.target.checked })}
                      style={{ accentColor: "#8b5cf6" }}
                    />
                    <span>Show Legend</span>
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#d4d4d8", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={selectedTile.format?.showLabels === true}
                      onChange={(e) => updateFormat({ showLabels: e.target.checked })}
                      style={{ accentColor: "#8b5cf6" }}
                    />
                    <span>Show Data Labels</span>
                  </label>
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
                  <div style={{ display: "flex", gap: 12, marginTop: 4, alignItems: "center" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input
                        type="color"
                        value={selectedTile.format?.bg || "#18181b"}
                        onChange={(e) => updateFormat({ bg: e.target.value })}
                        style={{ background: "transparent", border: "none", cursor: "pointer", width: 28, height: 26 }}
                      />
                      <span style={{ fontSize: 11, color: "#71717a" }}>BG</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input
                        type="color"
                        value={selectedTile.format?.borderColor || "#27272a"}
                        onChange={(e) => updateFormat({ borderColor: e.target.value })}
                        style={{ background: "transparent", border: "none", cursor: "pointer", width: 28, height: 26 }}
                      />
                      <span style={{ fontSize: 11, color: "#71717a" }}>Border</span>
                    </div>
                  </div>
                </div>

                {/* Border Radius Slider */}
                <div>
                  <label style={{ fontSize: 11, color: "#a1a1aa" }}>
                    Border Radius: {selectedTile.format?.radius ?? 8}px
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={24}
                    value={selectedTile.format?.radius ?? 8}
                    onChange={(e) => updateFormat({ radius: parseInt(e.target.value, 10) })}
                    style={{ width: "100%", accentColor: "#8b5cf6", marginTop: 4 }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* FILTERS TAB */}
        {activeTab === "filters" && <FilterTab columns={columns} />}
      </div>
    </aside>
  );
}
