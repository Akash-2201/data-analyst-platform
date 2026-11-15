/**
 * frontend/src/visualize/LeftPanel.jsx
 * Left panel (260px): Visualizations gallery and dataset fields grouped by type.
 */

import React, { useState, useMemo } from "react";
import { useDashboard } from "./dashboardContext";
import {
  VISUALIZATION_TYPES,
  MORE_VISUALIZATION_TYPES,
} from "./constants";
import { createDefaultTile, findFirstFreeSpot, classifyColumn } from "./utils";
import { getSmartRecommendations } from "./autoDashboard";

export function LeftPanel({ columns = [], isOpen = false, isCollapsed = false }) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages, mode, selectedTileIds } = present;
  const [vizSectionOpen, setVizSectionOpen] = useState(true);
  const [recSectionOpen, setRecSectionOpen] = useState(false);
  const [dataFieldsSectionOpen, setDataFieldsSectionOpen] = useState(true);
  const [showMore, setShowMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Sub-group accordions inside Data Fields
  const [numOpen, setNumOpen] = useState(true);
  const [textOpen, setTextOpen] = useState(true);
  const [dateOpen, setDateOpen] = useState(true);
  const [locOpen, setLocOpen] = useState(true);
  const [flagsOpen, setFlagsOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState("");

  const showToast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(""), 2500);
  };

  const activePage = pages.find((p) => p.id === activePageId) || pages[0];
  const selectedTile = activePage?.tiles.find((t) => selectedTileIds?.includes(t.id));

  const recommendations = useMemo(() => getSmartRecommendations(columns), [columns]);

  const handleAddRecommendation = (rec) => {
    if (mode === "view") return;
    const freeSpot = findFirstFreeSpot(activePage?.tiles || []);
    const newTile = createDefaultTile("chart", {
      spot: freeSpot,
      title: rec.label,
      chartConfig: {
        chartType: rec.chartType,
        xCol: rec.xCol,
        yCol: rec.yCol,
        agg: rec.agg || "sum",
      },
    });
    dispatch({ type: "ADD_TILE", payload: newTile });
  };

  const handleAddTile = (typeId) => {
    if (mode === "view") return;
    const kind = typeId === "text" ? "text" : typeId === "slicer" ? "slicer" : "chart";
    const freeSpot = findFirstFreeSpot(activePage?.tiles || []);
    const newTile = createDefaultTile(kind, {
      spot: freeSpot,
      title: typeId === "text" ? "Dashboard Title" : typeId === "slicer" ? "Slicer Filter" : `${typeId.replace("_", " ").toUpperCase()} Chart`,
      chartConfig: { chartType: typeId },
    });
    dispatch({ type: "ADD_TILE", payload: newTile });
  };

  // Rigorous client-side column classification
  const categorized = useMemo(() => {
    const res = {
      numerical: [],
      date: [],
      location: [],
      flags: [],
      text: [],
    };

    (columns || []).forEach((col) => {
      const info = classifyColumn(col);
      if (info.group === "Flags") {
        res.flags.push(info);
      } else if (info.group === "LOCATION") {
        res.location.push(info);
      } else if (info.group === "DATE") {
        res.date.push(info);
      } else if (info.group === "NUMERICAL") {
        res.numerical.push(info);
      } else {
        res.text.push(info);
      }
    });

    return res;
  }, [columns]);

  // Search filtered fields
  const filteredCategorized = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return categorized;
    const match = (c) => c.name.toLowerCase().includes(q);
    return {
      numerical: categorized.numerical.filter(match),
      date: categorized.date.filter(match),
      location: categorized.location.filter(match),
      flags: categorized.flags.filter(match),
      text: categorized.text.filter(match),
    };
  }, [categorized, searchQuery]);

  // Click-to-assign field to currently selected chart tile
  const handleFieldClick = (colInfo) => {
    if (mode === "view") return;

    if (!selectedTile) {
      showToast("Select a tile to assign this field");
      return;
    }

    const colName = colInfo.name;
    const isNum = colInfo.group === "NUMERICAL";

    if (selectedTile.kind === "slicer") {
      dispatch({
        type: "UPDATE_TILE",
        payload: {
          tileId: selectedTile.id,
          updates: {
            slicer: { ...selectedTile.slicer, col: colName },
          },
        },
      });
      return;
    }

    if (selectedTile.kind !== "chart") return;

    const cfg = selectedTile.chartConfig || {};
    let updates = {};

    // Logical open slot assignment
    if (!cfg.xCol) {
      updates = { xCol: colName };
    } else if (!cfg.yCol) {
      updates = { yCol: colName, agg: colInfo.defaultAgg || (isNum ? "sum" : "count") };
    } else if (isNum) {
      updates = { yCol: colName, agg: colInfo.defaultAgg || "sum" };
    } else {
      updates = { xCol: colName };
    }

    dispatch({
      type: "UPDATE_TILE",
      payload: {
        tileId: selectedTile.id,
        updates: {
          chartConfig: {
            ...cfg,
            ...updates,
          },
        },
      },
    });
  };

  return (
    <aside className={`rpt-left-panel ${isOpen ? "drawer-open" : ""} ${isCollapsed ? "collapsed" : ""}`}>
      {/* =========================================================================
          SECTION 1: VISUALIZATIONS (Compact 4-column grid, Collapsible, default expanded)
          ========================================================================= */}
      <div
        className="rpt-panel-header"
        style={{ cursor: "pointer", userSelect: "none" }}
        onClick={() => setVizSectionOpen(!vizSectionOpen)}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span>📊 Visualizations</span>
          {selectedTile && (
            <span style={{ fontSize: 9, color: "#a78bfa", textTransform: "none" }}>
              (Tile Active)
            </span>
          )}
        </span>
        <span style={{ fontSize: 11, color: "#71717a" }}>{vizSectionOpen ? "▴" : "▾"}</span>
      </div>

      {vizSectionOpen && (
        <div style={{ flexShrink: 0, maxHeight: 220, overflowY: "auto", borderBottom: "1px solid #27272a" }}>
          {/* Main Visualizations 4-Column Grid */}
          <div style={{ padding: "8px 10px", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 4 }}>
            {VISUALIZATION_TYPES.map((v) => (
              <button
                key={v.id}
                type="button"
                className="rpt-btn"
                style={{
                  flexDirection: "column",
                  padding: "4px 2px",
                  gap: 2,
                  fontSize: 9,
                  textAlign: "center",
                  height: 56,
                  justifyContent: "center",
                }}
                onClick={() => handleAddTile(v.id)}
                title={`Add ${v.label} to active page`}
              >
                <span style={{ fontSize: 14 }}>
                  {v.id === "bar" ? "📊" : v.id === "line" ? "📈" : v.id === "area" ? "📉" : v.id === "pie" ? "🥧" : v.id === "donut" ? "🍩" : v.id === "scatter" ? "⚬" : v.id === "table" ? "▦" : v.id === "kpi" ? "🔢" : v.id === "map" ? "🗺️" : v.id === "slicer" ? "🔍" : v.id === "text" ? "T" : "📊"}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", width: "100%", whiteSpace: "nowrap" }}>
                  {v.label}
                </span>
              </button>
            ))}
          </div>

          {/* Collapsible More Charts */}
          <div style={{ padding: "0 10px 8px 10px" }}>
            <button
              type="button"
              className="rpt-btn"
              style={{ width: "100%", justifyContent: "center", fontSize: 10, padding: "4px 6px" }}
              onClick={() => setShowMore(!showMore)}
            >
              {showMore ? "▴ Less Charts" : "▾ More Charts (Stacked, etc.)"}
            </button>

            {showMore && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 4, marginTop: 6 }}>
                {MORE_VISUALIZATION_TYPES.map((v) => (
                  <button
                    key={v.id}
                    type="button"
                    className="rpt-btn"
                    style={{
                      fontSize: 9,
                      padding: "4px 4px",
                      justifyContent: "flex-start",
                      overflow: "hidden",
                    }}
                    onClick={() => handleAddTile(v.id)}
                    title={`Add ${v.label}`}
                  >
                    <span>📈</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {v.label}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =========================================================================
          SECTION 2: SMART RECOMMENDATIONS (Collapsible, default COLLAPSED)
          ========================================================================= */}
      {recommendations.length > 0 && (
        <div>
          <div
            className="rpt-panel-header"
            style={{ cursor: "pointer", userSelect: "none", color: "#c4b5fd" }}
            onClick={() => setRecSectionOpen(!recSectionOpen)}
          >
            <span>✨ Recommendations ({recommendations.length})</span>
            <span style={{ fontSize: 11, color: "#71717a" }}>{recSectionOpen ? "▴" : "▾"}</span>
          </div>

          {recSectionOpen && (
            <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6, maxHeight: 180, overflowY: "auto", borderBottom: "1px solid #27272a" }}>
              {recommendations.slice(0, 4).map((rec) => (
                <div
                  key={rec.id}
                  onClick={() => handleAddRecommendation(rec)}
                  className="rpt-rec-chip rpt-recommendation-card"
                  title={`${rec.reason}: click to add to canvas`}
                  style={{
                    background: "rgba(139, 92, 246, 0.12)",
                    border: "1px solid rgba(139, 92, 246, 0.3)",
                    borderRadius: 6,
                    padding: "6px 8px",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                >
                  <div style={{ fontSize: 10, fontWeight: 600, color: "#e4e4e7", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span>+ {rec.chartType.toUpperCase()}</span>
                    <span style={{ fontSize: 8, color: "#a78bfa" }}>Click to Add</span>
                  </div>
                  <div style={{ fontSize: 10, color: "#a1a1aa", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {rec.label}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          SECTION 3: DATA FIELDS (Expanded, flex: 1 1 auto, min-height: 240px, search, scroll)
          ========================================================================= */}
      <div style={{ display: "flex", flexDirection: "column", flex: "1 1 auto", minHeight: 240, overflow: "hidden" }}>
        {/* DATA FIELDS Header */}
        <div
          className="rpt-panel-header"
          style={{ cursor: "pointer", userSelect: "none" }}
          onClick={() => setDataFieldsSectionOpen(!dataFieldsSectionOpen)}
        >
          <span>Data Fields</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="rpt-badge" style={{ fontSize: 10, background: "#27272a", color: "#a1a1aa", padding: "1px 6px", borderRadius: 10 }}>
              {columns.length}
            </span>
            <span style={{ fontSize: 11, color: "#71717a" }}>{dataFieldsSectionOpen ? "▴" : "▾"}</span>
          </div>
        </div>

        {dataFieldsSectionOpen && (
          <div style={{ display: "flex", flexDirection: "column", flex: "1 1 auto", minHeight: 0, overflow: "hidden" }}>
            {/* Search Box */}
            <div style={{ padding: "6px 10px 4px 10px", flexShrink: 0 }}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="🔍 Search fields..."
                style={{
                  width: "100%",
                  padding: "5px 8px",
                  fontSize: 11,
                  background: "#18181b",
                  border: "1px solid #27272a",
                  borderRadius: 4,
                  color: "#f4f4f5",
                  outline: "none",
                }}
              />
            </div>

            {/* Tip for Field Assignment */}
            {selectedTile && selectedTile.kind === "chart" && (
              <div style={{ padding: "4px 10px", background: "rgba(139, 92, 246, 0.1)", borderBottom: "1px solid #27272a", fontSize: 10, color: "#c4b5fd", flexShrink: 0 }}>
                💡 Click field: Number → Y, Text/Date → X
              </div>
            )}

            {/* Fields List - independent scroll area */}
            <div style={{ padding: "6px 10px", display: "flex", flexDirection: "column", gap: 8, flex: "1 1 auto", overflowY: "auto" }}>
              {/* Numerical */}
              {filteredCategorized.numerical.length > 0 && (
                <div>
                  <div
                    className="rpt-section-title"
                    onClick={() => setNumOpen(!numOpen)}
                    style={{ padding: "2px 0 4px 0", color: "#60a5fa", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  >
                    <span># Numerical ({filteredCategorized.numerical.length})</span>
                    <span style={{ fontSize: 9 }}>{numOpen ? "▴" : "▾"}</span>
                  </div>
                  {numOpen && filteredCategorized.numerical.map((col) => (
                    <div
                      key={col.name}
                      className="rpt-field-item"
                      onClick={() => handleFieldClick(col)}
                      title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                      style={{
                        padding: "4px 6px",
                        fontSize: 11,
                        color: "#e4e4e7",
                        cursor: "pointer",
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        backgroundColor: selectedTile?.chartConfig?.yCol === col.name ? "rgba(59, 130, 246, 0.2)" : "transparent",
                        border: selectedTile?.chartConfig?.yCol === col.name ? "1px solid #3b82f6" : "1px solid transparent",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col.name}</span>
                      <span style={{ fontSize: 9, color: "#60a5fa" }}>
                        {selectedTile?.chartConfig?.yCol === col.name ? "Y-Axis" : col.defaultAgg || "123"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Text */}
              {filteredCategorized.text.length > 0 && (
                <div>
                  <div
                    className="rpt-section-title"
                    onClick={() => setTextOpen(!textOpen)}
                    style={{ padding: "2px 0 4px 0", color: "#34d399", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  >
                    <span>Aa Text ({filteredCategorized.text.length})</span>
                    <span style={{ fontSize: 9 }}>{textOpen ? "▴" : "▾"}</span>
                  </div>
                  {textOpen && filteredCategorized.text.map((col) => (
                    <div
                      key={col.name}
                      className="rpt-field-item"
                      onClick={() => handleFieldClick(col)}
                      title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                      style={{
                        padding: "4px 6px",
                        fontSize: 11,
                        color: "#e4e4e7",
                        cursor: "pointer",
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        backgroundColor: selectedTile?.chartConfig?.xCol === col.name ? "rgba(16, 185, 129, 0.2)" : "transparent",
                        border: selectedTile?.chartConfig?.xCol === col.name ? "1px solid #10b981" : "1px solid transparent",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col.name}</span>
                      <span style={{ fontSize: 9, color: "#34d399" }}>
                        {selectedTile?.chartConfig?.xCol === col.name ? "X-Axis" : (col.subType === "Identifier" ? "id" : "txt")}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Date */}
              {filteredCategorized.date.length > 0 && (
                <div>
                  <div
                    className="rpt-section-title"
                    onClick={() => setDateOpen(!dateOpen)}
                    style={{ padding: "2px 0 4px 0", color: "#fbbf24", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  >
                    <span>📅 Date ({filteredCategorized.date.length})</span>
                    <span style={{ fontSize: 9 }}>{dateOpen ? "▴" : "▾"}</span>
                  </div>
                  {dateOpen && filteredCategorized.date.map((col) => (
                    <div
                      key={col.name}
                      className="rpt-field-item"
                      onClick={() => handleFieldClick(col)}
                      title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                      style={{
                        padding: "4px 6px",
                        fontSize: 11,
                        color: "#e4e4e7",
                        cursor: "pointer",
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        backgroundColor: selectedTile?.chartConfig?.xCol === col.name ? "rgba(245, 158, 11, 0.2)" : "transparent",
                        border: selectedTile?.chartConfig?.xCol === col.name ? "1px solid #f59e0b" : "1px solid transparent",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col.name}</span>
                      <span style={{ fontSize: 9, color: "#fbbf24" }}>
                        {selectedTile?.chartConfig?.xCol === col.name ? "X-Axis" : "date"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Location */}
              {filteredCategorized.location.length > 0 && (
                <div>
                  <div
                    className="rpt-section-title"
                    onClick={() => setLocOpen(!locOpen)}
                    style={{ padding: "2px 0 4px 0", color: "#f472b6", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  >
                    <span>📍 Location ({filteredCategorized.location.length})</span>
                    <span style={{ fontSize: 9 }}>{locOpen ? "▴" : "▾"}</span>
                  </div>
                  {locOpen && filteredCategorized.location.map((col) => (
                    <div
                      key={col.name}
                      className="rpt-field-item"
                      onClick={() => handleFieldClick(col)}
                      title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                      style={{
                        padding: "4px 6px",
                        fontSize: 11,
                        color: "#e4e4e7",
                        cursor: "pointer",
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                      }}
                    >
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{col.name}</span>
                      <span style={{ fontSize: 9, color: "#f472b6" }}>geo</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Flags (Collapsed by default) */}
              {filteredCategorized.flags.length > 0 && (
                <div>
                  <div
                    className="rpt-section-title"
                    onClick={() => setFlagsOpen(!flagsOpen)}
                    style={{ padding: "2px 0 4px 0", color: "#a1a1aa", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                  >
                    <span>🚩 Flags ({filteredCategorized.flags.length})</span>
                    <span style={{ fontSize: 9 }}>{flagsOpen ? "▴" : "▾"}</span>
                  </div>
                  {flagsOpen && filteredCategorized.flags.map((col) => (
                    <div key={col.name} style={{ fontSize: 10, color: "#a1a1aa", padding: "3px 6px" }}>
                      {col.name}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {toastMsg && <div className="rpt-toast">{toastMsg}</div>}
    </aside>
  );
}
