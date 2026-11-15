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
  const [showMore, setShowMore] = useState(false);
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
      {/* Visualizations Header */}
      <div className="rpt-panel-header">
        <span>Visualizations</span>
        {selectedTile && (
          <span style={{ fontSize: 10, color: "#a78bfa" }}>
            Tile Selected
          </span>
        )}
      </div>

      {/* Main Visualizations Grid */}
      <div style={{ padding: "10px 12px", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
        {VISUALIZATION_TYPES.map((v) => (
          <button
            key={v.id}
            type="button"
            className="rpt-btn"
            style={{
              flexDirection: "column",
              padding: "8px 2px",
              gap: 4,
              fontSize: 10,
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

      {/* Collapsible More Visualizations */}
      <div style={{ padding: "0 12px 10px 12px" }}>
        <button
          type="button"
          className="rpt-btn"
          style={{ width: "100%", justifyContent: "center", fontSize: 11 }}
          onClick={() => setShowMore(!showMore)}
        >
          {showMore ? "▴ Less Charts" : "▾ More Charts (Stacked, Waterfall, etc.)"}
        </button>

        {showMore && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 6, marginTop: 8 }}>
            {MORE_VISUALIZATION_TYPES.map((v) => (
              <button
                key={v.id}
                type="button"
                className="rpt-btn"
                style={{
                  fontSize: 10,
                  padding: "6px 4px",
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

      {/* Smart Recommendations Section */}
      {recommendations.length > 0 && (
        <div style={{ padding: "0 12px 10px 12px" }}>
          <div className="rpt-panel-header" style={{ padding: "6px 0", borderBottom: "none", color: "#c4b5fd" }}>
            <span>✨ Smart Recommendations</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
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
                <div style={{ fontSize: 11, fontWeight: 600, color: "#e4e4e7", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span>+ {rec.chartType.toUpperCase()}</span>
                  <span style={{ fontSize: 9, color: "#a78bfa" }}>Click to Add</span>
                </div>
                <div style={{ fontSize: 10, color: "#a1a1aa", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {rec.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* DATA FIELDS Header */}
      <div className="rpt-panel-header" style={{ marginTop: 8 }}>
        <span>Data Fields</span>
        <span style={{ fontSize: 10, color: "#71717a" }}>{columns.length} columns</span>
      </div>

      {/* Tip for Field Assignment */}
      {selectedTile && selectedTile.kind === "chart" && (
        <div style={{ padding: "6px 12px", background: "rgba(139, 92, 246, 0.1)", borderBottom: "1px solid #3f3f46", fontSize: 10, color: "#c4b5fd" }}>
          💡 Click a field to assign: Numeric → Y-Axis, Text/Date → X-Axis.
        </div>
      )}

      {/* Fields List */}
      <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 10, flex: 1, overflowY: "auto" }}>
        {/* Numerical */}
        {categorized.numerical.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#60a5fa" }}>
              # Numerical ({categorized.numerical.length})
            </div>
            {categorized.numerical.map((col) => (
              <div
                key={col.name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(col)}
                title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                style={{
                  padding: "5px 8px",
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
        {categorized.text.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#34d399" }}>
              Aa Text ({categorized.text.length})
            </div>
            {categorized.text.map((col) => (
              <div
                key={col.name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(col)}
                title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                style={{
                  padding: "5px 8px",
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
        {categorized.date.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#fbbf24" }}>
              📅 Date ({categorized.date.length})
            </div>
            {categorized.date.map((col) => (
              <div
                key={col.name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(col)}
                title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                style={{
                  padding: "5px 8px",
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
        {categorized.location.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#f472b6" }}>
              📍 Location ({categorized.location.length})
            </div>
            {categorized.location.map((col) => (
              <div
                key={col.name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(col)}
                title={selectedTile ? `Assign ${col.name} to selected visual` : col.name}
                style={{
                  padding: "5px 8px",
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

        {/* Collapsible Flags */}
        {categorized.flags.length > 0 && (
          <div>
            <button
              type="button"
              className="rpt-btn"
              style={{ width: "100%", justifyContent: "space-between", fontSize: 10, padding: "4px 8px" }}
              onClick={() => setFlagsOpen(!flagsOpen)}
            >
              <span>🚩 Flags ({categorized.flags.length})</span>
              <span>{flagsOpen ? "▴" : "▾"}</span>
            </button>
            {flagsOpen && (
              <div style={{ marginTop: 4, paddingLeft: 4 }}>
                {categorized.flags.map((col) => (
                  <div key={col.name} style={{ fontSize: 10, color: "#a1a1aa", padding: "3px 4px" }}>
                    {col.name}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {toastMsg && <div className="rpt-toast">{toastMsg}</div>}
    </aside>
  );
}
