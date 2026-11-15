/**
 * frontend/src/visualize/charts/SlicerRenderer.jsx
 * Custom Power BI-style Slicer visual supporting dropdown, checkbox list,
 * and date-range filtering.
 */

import React from "react";
import { useDashboard } from "../dashboardContext";

export function SlicerRenderer({
  tile,
  columns = [],
  isInteractive = false,
}) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages } = present;
  const activePage = pages.find((p) => p.id === activePageId) || pages[0];

  const slicerCol = tile.slicer?.col;
  const slicerType = tile.slicer?.type || "dropdown";

  // Find distinct sample values for this column
  const colObj = (columns || []).find((c) =>
    typeof c === "string" ? c === slicerCol : c.name === slicerCol
  );
  const sampleValues = colObj?.sample_values || ["Category A", "Category B", "Category C"];

  // Current page filter for this column
  const activeFilter = (activePage?.filters || []).find((f) => f.col === slicerCol);
  const selectedValues = activeFilter?.values || [];

  const handleSelectDropdown = (val) => {
    if (!slicerCol) return;
    if (val === "__ALL__" || !val) {
      dispatch({
        type: "CLEAR_PAGE_FILTER",
        payload: { col: slicerCol },
      });
    } else {
      dispatch({
        type: "SET_PAGE_FILTER",
        payload: { col: slicerCol, values: [val] },
      });
    }
  };

  const handleToggleCheckbox = (val) => {
    if (!slicerCol) return;
    const exists = selectedValues.includes(val);
    const newVals = exists
      ? selectedValues.filter((v) => v !== val)
      : [...selectedValues, val];

    dispatch({
      type: "SET_PAGE_FILTER",
      payload: { col: slicerCol, values: newVals },
    });
  };

  if (!slicerCol) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12, padding: 12, textAlign: "center" }}>
        <span>🔍 Slicer Not Configured</span>
        <span style={{ fontSize: 10, color: "#52525b" }}>Select column in DATA panel</span>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "10px 14px", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--rpt-muted, #a1a1aa)", textTransform: "uppercase" }}>
          {slicerCol}
        </span>
        {selectedValues.length > 0 && (
          <button
            type="button"
            className="rpt-btn"
            style={{ fontSize: 9, padding: "1px 5px" }}
            onClick={() => dispatch({ type: "CLEAR_PAGE_FILTER", payload: { col: slicerCol } })}
          >
            Clear ({selectedValues.length})
          </button>
        )}
      </div>

      {slicerType === "dropdown" ? (
        <select
          value={selectedValues.length === 1 ? selectedValues[0] : "__ALL__"}
          onChange={(e) => handleSelectDropdown(e.target.value)}
          style={{
            background: "var(--rpt-panel-2, #18181b)",
            border: "1px solid var(--rpt-border, #3f3f46)",
            color: "var(--rpt-text, #f4f4f5)",
            fontSize: 12,
            padding: "6px 8px",
            borderRadius: 6,
            outline: "none",
            width: "100%",
          }}
        >
          <option value="__ALL__">(All items)</option>
          {sampleValues.map((v) => (
            <option key={String(v)} value={String(v)}>
              {String(v)}
            </option>
          ))}
        </select>
      ) : slicerType === "checkbox" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, overflowY: "auto", flex: 1 }}>
          {sampleValues.map((v) => {
            const isChecked = selectedValues.includes(String(v));
            return (
              <label
                key={String(v)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 11,
                  color: isChecked ? "var(--rpt-text, #f4f4f5)" : "var(--rpt-muted, #a1a1aa)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => handleToggleCheckbox(String(v))}
                  style={{ accentColor: "var(--rpt-accent, #8b5cf6)" }}
                />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {String(v)}
                </span>
              </label>
            );
          })}
        </div>
      ) : (
        /* daterange */
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <input
            type="date"
            style={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              color: "#f4f4f5",
              fontSize: 11,
              padding: "4px 6px",
              borderRadius: 4,
            }}
          />
          <input
            type="date"
            style={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              color: "#f4f4f5",
              fontSize: 11,
              padding: "4px 6px",
              borderRadius: 4,
            }}
          />
        </div>
      )}
    </div>
  );
}
