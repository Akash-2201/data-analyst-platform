/**
 * frontend/src/visualize/charts/TableRenderer.jsx
 * Custom Power BI-style Table Visual with sorting, search, pagination,
 * and cross-filter selection.
 */

import React, { useState, useMemo } from "react";

export function TableRenderer({
  data,
  columns = [],
  crossFilter = null,
  onPointClick = null,
  isInteractive = false,
}) {
  const [searchTerm, setSearchTerm] = useState("");
  const [sortCol, setSortCol] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(0);
  const pageSize = 8;

  // Convert incoming chart data or columns into table rows
  const tableData = useMemo(() => {
    if (!data) return { cols: [], rows: [] };

    // If data has labels and values
    if (Array.isArray(data.labels) && Array.isArray(data.values)) {
      const colX = data.x_label || "Category";
      const colY = data.y_label || "Value";
      const rows = data.labels.map((lbl, idx) => ({
        [colX]: String(lbl ?? ""),
        [colY]: data.values[idx] ?? 0,
      }));
      return { cols: [colX, colY], rows };
    }

    // Fallback: preview sample values from columns prop
    if (Array.isArray(columns) && columns.length > 0) {
      const colNames = columns.slice(0, 5).map((c) => (typeof c === "string" ? c : c.name));
      const maxRows = 5;
      const rows = [];
      for (let r = 0; r < maxRows; r++) {
        const row = {};
        columns.slice(0, 5).forEach((col) => {
          const name = typeof col === "string" ? col : col.name;
          const sample = col.sample_values ? col.sample_values[r] : "";
          row[name] = sample ?? "";
        });
        rows.push(row);
      }
      return { cols: colNames, rows };
    }

    return { cols: [], rows: [] };
  }, [data, columns]);

  // Filtered rows by search term
  const filteredRows = useMemo(() => {
    if (!searchTerm.trim()) return tableData.rows;
    const term = searchTerm.toLowerCase();
    return tableData.rows.filter((row) =>
      Object.values(row).some((val) => String(val).toLowerCase().includes(term))
    );
  }, [tableData.rows, searchTerm]);

  // Sorted rows
  const sortedRows = useMemo(() => {
    if (!sortCol) return filteredRows;
    const sorted = [...filteredRows].sort((a, b) => {
      const va = a[sortCol];
      const vb = b[sortCol];
      if (typeof va === "number" && typeof vb === "number") {
        return sortAsc ? va - vb : vb - va;
      }
      return sortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
    return sorted;
  }, [filteredRows, sortCol, sortAsc]);

  // Paginated slice
  const pageCount = Math.ceil(sortedRows.length / pageSize) || 1;
  const pagedRows = sortedRows.slice(page * pageSize, (page + 1) * pageSize);

  const handleHeaderClick = (col) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
  };

  if (tableData.cols.length === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#71717a", fontSize: 12 }}>
        No table data available
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 8, overflow: "hidden" }}>
      {/* Search Input Bar */}
      <div style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
        <input
          type="text"
          placeholder="Search table..."
          value={searchTerm}
          onChange={(e) => {
            setSearchTerm(e.target.value);
            setPage(0);
          }}
          style={{
            flex: 1,
            background: "var(--rpt-panel-2, #18181b)",
            border: "1px solid var(--rpt-border, #27272a)",
            color: "var(--rpt-text, #f4f4f5)",
            fontSize: 11,
            padding: "4px 8px",
            borderRadius: 4,
            outline: "none",
          }}
        />
        <span style={{ fontSize: 10, color: "var(--rpt-muted, #71717a)", whiteSpace: "nowrap" }}>
          {sortedRows.length} rows
        </span>
      </div>

      {/* Table Container */}
      <div style={{ flex: 1, overflow: "auto", border: "1px solid var(--rpt-border, #27272a)", borderRadius: 4 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, textAlign: "left" }}>
          <thead>
            <tr style={{ background: "var(--rpt-tile-header, #151518)", borderBottom: "1px solid var(--rpt-border, #27272a)", position: "sticky", top: 0, zIndex: 2 }}>
              {tableData.cols.map((col) => (
                <th
                  key={col}
                  onClick={() => handleHeaderClick(col)}
                  style={{
                    padding: "6px 8px",
                    fontWeight: 600,
                    color: "var(--rpt-muted, #a1a1aa)",
                    cursor: "pointer",
                    userSelect: "none",
                    whiteSpace: "nowrap",
                  }}
                >
                  {col} {sortCol === col ? (sortAsc ? "▲" : "▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map((row, idx) => {
              const firstVal = String(row[tableData.cols[0]] ?? "");
              const isSelected = crossFilter ? crossFilter.value === firstVal : false;

              return (
                <tr
                  key={idx}
                  onClick={() => {
                    if (isInteractive && onPointClick) {
                      onPointClick({ label: firstVal, value: row[tableData.cols[1]] ?? 0 });
                    }
                  }}
                  style={{
                    borderBottom: "1px solid var(--rpt-border, #1f1f23)",
                    backgroundColor: isSelected ? "rgba(139, 92, 246, 0.2)" : "transparent",
                    cursor: isInteractive ? "pointer" : "default",
                  }}
                >
                  {tableData.cols.map((col) => (
                    <td key={col} style={{ padding: "6px 8px", color: "var(--rpt-text, #e4e4e7)", whiteSpace: "nowrap" }}>
                      {String(row[col] ?? "")}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {pageCount > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 6, fontSize: 10, color: "#71717a" }}>
          <button
            type="button"
            className="rpt-btn"
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
            style={{ fontSize: 10, padding: "2px 6px" }}
          >
            Previous
          </button>
          <span>Page {page + 1} of {pageCount}</span>
          <button
            type="button"
            className="rpt-btn"
            disabled={page >= pageCount - 1}
            onClick={() => setPage(page + 1)}
            style={{ fontSize: 10, padding: "2px 6px" }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
