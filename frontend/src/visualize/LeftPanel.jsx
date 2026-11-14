/**
 * frontend/src/visualize/LeftPanel.jsx
 * Left panel (260px): Visualizations gallery and dataset fields grouped by type.
 */

import React, { useState } from "react";
import { useDashboard } from "./dashboardContext";
import {
  VISUALIZATION_TYPES,
  MORE_VISUALIZATION_TYPES,
} from "./constants";
import { createDefaultTile, findFirstFreeSpot } from "./utils";

export function LeftPanel({ columns = [], isOpen = false }) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages, mode, selectedTileIds } = present;
  const [showMore, setShowMore] = useState(false);
  const [flagsOpen, setFlagsOpen] = useState(false);

  const activePage = pages.find((p) => p.id === activePageId) || pages[0];

  const handleAddTile = (typeId) => {
    if (mode === "view") return;
    const kind = typeId === "text" ? "text" : typeId === "slicer" ? "slicer" : "chart";
    const freeSpot = findFirstFreeSpot(activePage?.tiles || []);
    const newTile = createDefaultTile(kind, {
      spot: freeSpot,
      title: typeId === "text" ? "Title" : typeId === "slicer" ? "Slicer" : `${typeId.toUpperCase()} Chart`,
      chartConfig: { chartType: typeId },
    });
    dispatch({ type: "ADD_TILE", payload: newTile });
  };

  // Group columns by type
  const categorized = {
    numerical: [],
    date: [],
    location: [],
    flags: [],
    text: [],
  };

  (columns || []).forEach((col) => {
    const name = typeof col === "string" ? col : col.name;
    const inferred = (col.inferred_type || col.dtype || "").toLowerCase();
    const nameLower = name.toLowerCase();

    if (nameLower.endsWith("_outlier") || nameLower.includes("_flag_") || nameLower.startsWith("is_")) {
      categorized.flags.push(name);
    } else if (
      nameLower.includes("lat") ||
      nameLower.includes("lon") ||
      nameLower.includes("coord") ||
      inferred.includes("location") ||
      inferred.includes("geo")
    ) {
      categorized.location.push(name);
    } else if (
      inferred.includes("date") ||
      inferred.includes("time") ||
      nameLower.includes("date") ||
      nameLower.includes("year") ||
      nameLower.includes("month")
    ) {
      categorized.date.push(name);
    } else if (
      inferred.includes("int") ||
      inferred.includes("float") ||
      inferred.includes("numeric") ||
      col.numeric_stats
    ) {
      categorized.numerical.push(name);
    } else {
      categorized.text.push(name);
    }
  });

  const handleFieldClick = (colName, colType) => {
    if (mode === "view" || !selectedTileIds || selectedTileIds.length !== 1) return;
    const selectedId = selectedTileIds[0];
    const tile = activePage?.tiles.find((t) => t.id === selectedId);
    if (!tile || tile.kind !== "chart") return;

    // If numeric -> assign to Y, if text/date/loc -> assign to X
    if (colType === "numerical") {
      dispatch({
        type: "UPDATE_TILE",
        payload: {
          tileId: selectedId,
          updates: { chartConfig: { ...tile.chartConfig, yCol: colName } },
        },
      });
    } else {
      dispatch({
        type: "UPDATE_TILE",
        payload: {
          tileId: selectedId,
          updates: { chartConfig: { ...tile.chartConfig, xCol: colName } },
        },
      });
    }
  };

  return (
    <aside className={`rpt-left-panel ${isOpen ? "drawer-open" : ""}`}>
      <div className="rpt-panel-header">
        <span>Visualizations</span>
      </div>

      {/* Visualizations Grid */}
      <div style={{ padding: "10px 12px", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
        {VISUALIZATION_TYPES.map((v) => (
          <button
            key={v.id}
            type="button"
            className="rpt-btn"
            style={{
              flexDirection: "column",
              padding: "8px 4px",
              gap: 4,
              fontSize: 10,
              textAlign: "center",
              height: 56,
              justifyContent: "center",
            }}
            onClick={() => handleAddTile(v.id)}
            title={`Add ${v.label}`}
          >
            <span style={{ fontSize: 14 }}>📊</span>
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
          {showMore ? "▴ Less Charts" : "▾ More Charts..."}
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

      {/* DATA FIELDS Section */}
      <div className="rpt-panel-header" style={{ marginTop: 8 }}>
        <span>Data Fields</span>
        <span style={{ fontSize: 10, color: "#71717a" }}>{columns.length} cols</span>
      </div>

      <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 10 }}>
        {/* Numerical */}
        {categorized.numerical.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#3b82f6" }}>
              # Numerical ({categorized.numerical.length})
            </div>
            {categorized.numerical.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "numerical")}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  color: "#d4d4d8",
                  cursor: "pointer",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                <span style={{ fontSize: 9, color: "#71717a" }}>123</span>
              </div>
            ))}
          </div>
        )}

        {/* Text */}
        {categorized.text.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#10b981" }}>
              Aa Text ({categorized.text.length})
            </div>
            {categorized.text.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "text")}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  color: "#d4d4d8",
                  cursor: "pointer",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                <span style={{ fontSize: 9, color: "#71717a" }}>txt</span>
              </div>
            ))}
          </div>
        )}

        {/* Date */}
        {categorized.date.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#f59e0b" }}>
              📅 Date ({categorized.date.length})
            </div>
            {categorized.date.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "date")}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  color: "#d4d4d8",
                  cursor: "pointer",
                  borderRadius: 4,
                }}
              >
                {name}
              </div>
            ))}
          </div>
        )}

        {/* Location */}
        {categorized.location.length > 0 && (
          <div>
            <div className="rpt-section-title" style={{ padding: "2px 0 4px 0", color: "#ec4899" }}>
              📍 Location ({categorized.location.length})
            </div>
            {categorized.location.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "location")}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  color: "#d4d4d8",
                  cursor: "pointer",
                  borderRadius: 4,
                }}
              >
                {name}
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
              <div style={{ marginTop: 4, paddingLeft: 6 }}>
                {categorized.flags.map((name) => (
                  <div key={name} style={{ fontSize: 10, color: "#a1a1aa", padding: "2px 4px" }}>
                    {name}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
