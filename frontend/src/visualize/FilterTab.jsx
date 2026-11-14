/**
 * frontend/src/visualize/FilterTab.jsx
 * FILTERS tab in RightPanel: per-page filter list with checkbox values,
 * Select All / Clear, and active filter badge.
 */

import React, { useState } from "react";
import { useDashboard } from "./dashboardContext";

export function FilterTab({ columns = [] }) {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { activePageId, pages } = present;
  const activePage = pages.find((p) => p.id === activePageId) || pages[0];
  const pageFilters = activePage?.filters || [];

  const [selectedColToAdd, setSelectedColToAdd] = useState("");

  const colNames = (columns || []).map((c) => (typeof c === "string" ? c : c.name));

  const handleAddFilter = (colName) => {
    if (!colName) return;
    const colObj = columns.find((c) => (typeof c === "string" ? c === colName : c.name === colName));
    const sampleVals = colObj && colObj.sample_values ? colObj.sample_values : ["Value 1", "Value 2"];
    dispatch({
      type: "SET_PAGE_FILTER",
      payload: { col: colName, values: sampleVals },
    });
    setSelectedColToAdd("");
  };

  const handleRemoveFilter = (colName) => {
    dispatch({
      type: "CLEAR_PAGE_FILTER",
      payload: { col: colName },
    });
  };

  const handleToggleValue = (colName, val) => {
    const existing = pageFilters.find((f) => f.col === colName);
    if (!existing) return;
    const currentVals = existing.values || [];
    const newVals = currentVals.includes(val)
      ? currentVals.filter((v) => v !== val)
      : [...currentVals, val];
    dispatch({
      type: "SET_PAGE_FILTER",
      payload: { col: colName, values: newVals },
    });
  };

  const handleSelectAll = (colName) => {
    const colObj = columns.find((c) => (typeof c === "string" ? c === colName : c.name === colName));
    const allVals = colObj?.sample_values || ["Value 1", "Value 2"];
    dispatch({
      type: "SET_PAGE_FILTER",
      payload: { col: colName, values: allVals },
    });
  };

  const handleClearAll = (colName) => {
    dispatch({
      type: "SET_PAGE_FILTER",
      payload: { col: colName, values: [] },
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <div style={{ fontSize: 11, fontWeight: 600, color: "#a1a1aa", textTransform: "uppercase", marginBottom: 6 }}>
          Filters on {activePage?.name || "Page"}
        </div>
        <div style={{ fontSize: 11, color: "#71717a", marginBottom: 8 }}>
          Filters configured here apply across all visuals on this page.
        </div>

        {/* Add Filter Dropdown */}
        <div style={{ display: "flex", gap: 6 }}>
          <select
            value={selectedColToAdd}
            onChange={(e) => setSelectedColToAdd(e.target.value)}
            style={{
              flex: 1,
              background: "#18181b",
              border: "1px solid #27272a",
              color: "#f4f4f5",
              padding: "5px 8px",
              borderRadius: 6,
              fontSize: 11,
            }}
          >
            <option value="">+ Add Column Filter...</option>
            {colNames.map((c) => (
              <option key={c} value={c} disabled={pageFilters.some((f) => f.col === c)}>
                {c}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rpt-btn rpt-btn-primary"
            disabled={!selectedColToAdd}
            onClick={() => handleAddFilter(selectedColToAdd)}
            style={{ fontSize: 11, padding: "4px 8px" }}
          >
            Add
          </button>
        </div>
      </div>

      {/* Filter Cards */}
      {pageFilters.length === 0 ? (
        <div className="rpt-empty-state-hint" style={{ padding: "24px 8px" }}>
          <span>🔍</span>
          <span>No filters applied to this page yet.</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {pageFilters.map((filt) => {
            const colObj = columns.find((c) => (typeof c === "string" ? c === filt.col : c.name === filt.col));
            const availableValues = colObj?.sample_values || filt.values || [];

            return (
              <div
                key={filt.col}
                style={{
                  background: "#18181b",
                  border: "1px solid #27272a",
                  borderRadius: 6,
                  padding: 10,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#e4e4e7" }}>
                    {filt.col}
                  </span>
                  <button
                    type="button"
                    className="rpt-hover-icon-btn danger"
                    onClick={() => handleRemoveFilter(filt.col)}
                    title="Remove filter"
                  >
                    ✕
                  </button>
                </div>

                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    type="button"
                    className="rpt-btn"
                    style={{ fontSize: 10, padding: "2px 6px" }}
                    onClick={() => handleSelectAll(filt.col)}
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    className="rpt-btn"
                    style={{ fontSize: 10, padding: "2px 6px" }}
                    onClick={() => handleClearAll(filt.col)}
                  >
                    Clear
                  </button>
                </div>

                {/* Values Checkbox List */}
                <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 120, overflowY: "auto" }}>
                  {availableValues.map((val) => {
                    const isChecked = (filt.values || []).includes(val);
                    return (
                      <label
                        key={String(val)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          fontSize: 11,
                          color: isChecked ? "#f4f4f5" : "#71717a",
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleToggleValue(filt.col, val)}
                          style={{ accentColor: "#8b5cf6" }}
                        />
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {String(val)}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
