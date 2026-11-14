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
import { createDefaultTile, findFirstFreeSpot } from "./utils";

export function LeftPanel({ columns = [], isOpen = false }) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages, mode, selectedTileIds } = present;
  const [showMore, setShowMore] = useState(false);
  const [flagsOpen, setFlagsOpen] = useState(false);

  const activePage = pages.find((p) => p.id === activePageId) || pages[0];
  const selectedTile = activePage?.tiles.find((t) => selectedTileIds?.includes(t.id));

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

  // Advanced client-side column classification
  const categorized = useMemo(() => {
    const res = {
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
      const samples = col.sample_values || [];

      // Check date pattern in sample values (e.g. DD-MM-YYYY, YYYY-MM-DD, ISO)
      const hasDateSample = samples.some((v) => {
        if (!v) return false;
        const s = String(v).trim();
        return /^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}/.test(s) || !isNaN(Date.parse(s));
      });

      // Flags & Boolean
      if (
        nameLower.endsWith("_outlier") ||
        nameLower.includes("_flag_") ||
        nameLower.startsWith("is_") ||
        nameLower.startsWith("has_") ||
        inferred.includes("bool")
      ) {
        res.flags.push(name);
      }
      // Location
      else if (
        nameLower.includes("lat") ||
        nameLower.includes("lon") ||
        nameLower.includes("coord") ||
        nameLower === "country" ||
        nameLower === "state" ||
        nameLower === "city" ||
        inferred.includes("location") ||
        inferred.includes("geo")
      ) {
        res.location.push(name);
      }
      // Date
      else if (
        hasDateSample ||
        inferred.includes("date") ||
        inferred.includes("time") ||
        nameLower.includes("date") ||
        nameLower.includes("year") ||
        nameLower.includes("month") ||
        nameLower.includes("dob")
      ) {
        res.date.push(name);
      }
      // Numerical
      else if (
        inferred.includes("int") ||
        inferred.includes("float") ||
        inferred.includes("numeric") ||
        inferred.includes("number") ||
        inferred.includes("currency") ||
        col.numeric_stats
      ) {
        res.numerical.push(name);
      }
      // Text / Categorical
      else {
        res.text.push(name);
      }
    });

    return res;
  }, [columns]);

  // Click-to-assign field to currently selected chart tile
  const handleFieldClick = (colName, colType) => {
    if (mode === "view" || !selectedTile || selectedTile.kind !== "chart") return;

    if (colType === "numerical") {
      dispatch({
        type: "UPDATE_TILE",
        payload: {
          tileId: selectedTile.id,
          updates: {
            chartConfig: {
              ...selectedTile.chartConfig,
              yCol: colName,
            },
          },
        },
      });
    } else {
      dispatch({
        type: "UPDATE_TILE",
        payload: {
          tileId: selectedTile.id,
          updates: {
            chartConfig: {
              ...selectedTile.chartConfig,
              xCol: colName,
            },
          },
        },
      });
    }
  };

  return (
    <aside className={`rpt-left-panel ${isOpen ? "drawer-open" : ""}`}>
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
            {categorized.numerical.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "numerical")}
                title={selectedTile ? `Assign ${name} to selected visual` : name}
                style={{
                  padding: "5px 8px",
                  fontSize: 11,
                  color: "#e4e4e7",
                  cursor: selectedTile ? "pointer" : "default",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  backgroundColor: selectedTile?.chartConfig?.yCol === name ? "rgba(59, 130, 246, 0.2)" : "transparent",
                  border: selectedTile?.chartConfig?.yCol === name ? "1px solid #3b82f6" : "1px solid transparent",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                <span style={{ fontSize: 9, color: "#60a5fa" }}>
                  {selectedTile?.chartConfig?.yCol === name ? "Y-Axis" : "123"}
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
            {categorized.text.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "text")}
                title={selectedTile ? `Assign ${name} to selected visual` : name}
                style={{
                  padding: "5px 8px",
                  fontSize: 11,
                  color: "#e4e4e7",
                  cursor: selectedTile ? "pointer" : "default",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  backgroundColor: selectedTile?.chartConfig?.xCol === name ? "rgba(16, 185, 129, 0.2)" : "transparent",
                  border: selectedTile?.chartConfig?.xCol === name ? "1px solid #10b981" : "1px solid transparent",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                <span style={{ fontSize: 9, color: "#34d399" }}>
                  {selectedTile?.chartConfig?.xCol === name ? "X-Axis" : "txt"}
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
            {categorized.date.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "date")}
                title={selectedTile ? `Assign ${name} to selected visual` : name}
                style={{
                  padding: "5px 8px",
                  fontSize: 11,
                  color: "#e4e4e7",
                  cursor: selectedTile ? "pointer" : "default",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  backgroundColor: selectedTile?.chartConfig?.xCol === name ? "rgba(245, 158, 11, 0.2)" : "transparent",
                  border: selectedTile?.chartConfig?.xCol === name ? "1px solid #f59e0b" : "1px solid transparent",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                <span style={{ fontSize: 9, color: "#fbbf24" }}>
                  {selectedTile?.chartConfig?.xCol === name ? "X-Axis" : "date"}
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
            {categorized.location.map((name) => (
              <div
                key={name}
                className="rpt-field-item"
                onClick={() => handleFieldClick(name, "location")}
                title={selectedTile ? `Assign ${name} to selected visual` : name}
                style={{
                  padding: "5px 8px",
                  fontSize: 11,
                  color: "#e4e4e7",
                  cursor: selectedTile ? "pointer" : "default",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
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
                {categorized.flags.map((name) => (
                  <div key={name} style={{ fontSize: 10, color: "#a1a1aa", padding: "3px 4px" }}>
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
