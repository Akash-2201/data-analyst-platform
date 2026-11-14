/**
 * frontend/src/visualize/TopBar.jsx
 * Top bar header with dashboard name, save, undo/redo, edit/view toggle,
 * generate dashboard, and export menu.
 */

import React, { useState, useRef, useEffect } from "react";
import { useDashboard } from "./dashboardContext";

export function TopBar({
  onSave,
  saveTime,
  isSaving,
  onGenerateDashboard,
  onExportPdf,
  onExportPng,
  onExportCsv,
  toggleLeftDrawer,
  toggleRightDrawer,
}) {
  const { state, dispatch } = useDashboard();
  const { present, past, future } = state;
  const [isEditingName, setIsEditingName] = useState(false);
  const [nameVal, setNameVal] = useState(present.name);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef(null);

  useEffect(() => {
    setNameVal(present.name);
  }, [present.name]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target)) {
        setExportMenuOpen(false);
      }
    }
    if (exportMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [exportMenuOpen]);

  const handleNameBlur = () => {
    setIsEditingName(false);
    if (nameVal.trim() && nameVal !== present.name) {
      dispatch({ type: "SET_DASHBOARD_NAME", payload: nameVal.trim() });
    } else {
      setNameVal(present.name);
    }
  };

  const handleNameKeyDown = (e) => {
    if (e.key === "Enter") {
      handleNameBlur();
    } else if (e.key === "Escape") {
      setNameVal(present.name);
      setIsEditingName(false);
    }
  };

  return (
    <header className="rpt-topbar">
      {/* Left: Mobile drawer toggles + Editable Title */}
      <div className="rpt-topbar-left">
        {toggleLeftDrawer && (
          <button
            type="button"
            className="rpt-btn rpt-mobile-drawer-toggle"
            onClick={toggleLeftDrawer}
            title="Toggle Visualizations & Fields"
          >
            ☰ Left
          </button>
        )}

        {isEditingName ? (
          <input
            type="text"
            className="rpt-dash-name-input"
            value={nameVal}
            onChange={(e) => setNameVal(e.target.value)}
            onBlur={handleNameBlur}
            onKeyDown={handleNameKeyDown}
            autoFocus
          />
        ) : (
          <span
            className="rpt-dash-name-input"
            onClick={() => setIsEditingName(true)}
            title="Click to rename dashboard"
            style={{ cursor: "pointer" }}
          >
            {present.name || "Untitled Dashboard"}
          </span>
        )}

        <button
          type="button"
          className="rpt-btn"
          onClick={onSave}
          disabled={isSaving}
          title="Save dashboard to local storage"
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
        {saveTime && (
          <span className="rpt-save-status">
            Saved at {saveTime}
          </span>
        )}
      </div>

      {/* Center: Undo, Redo, Edit / View Mode Toggle */}
      <div className="rpt-topbar-center">
        <button
          type="button"
          className="rpt-btn"
          disabled={past.length === 0}
          onClick={() => dispatch({ type: "UNDO" })}
          title="Undo (Ctrl+Z)"
        >
          ↩ Undo
        </button>
        <button
          type="button"
          className="rpt-btn"
          disabled={future.length === 0}
          onClick={() => dispatch({ type: "REDO" })}
          title="Redo (Ctrl+Y)"
        >
          ↪ Redo
        </button>

        <div className="rpt-mode-toggle">
          <button
            type="button"
            className={`rpt-mode-btn ${present.mode === "edit" ? "active edit" : ""}`}
            onClick={() => dispatch({ type: "SET_MODE", payload: "edit" })}
          >
            Edit
          </button>
          <button
            type="button"
            className={`rpt-mode-btn ${present.mode === "view" ? "active" : ""}`}
            onClick={() => dispatch({ type: "SET_MODE", payload: "view" })}
          >
            View
          </button>
        </div>

        {present.mode === "edit" && (
          <div style={{ display: "inline-flex", gap: 4, marginLeft: 4 }}>
            <button
              type="button"
              className={`rpt-btn ${present.settings?.snap ? "rpt-btn-primary" : ""}`}
              onClick={() =>
                dispatch({
                  type: "SET_SETTINGS",
                  payload: { snap: !present.settings?.snap },
                })
              }
              title="Toggle Snap to Grid (20px vs 4px)"
              style={{ fontSize: 11, padding: "4px 8px" }}
            >
              🧲 Snap {present.settings?.snap ? "ON" : "OFF"}
            </button>
            <button
              type="button"
              className={`rpt-btn ${present.settings?.showGrid ? "rpt-btn-primary" : ""}`}
              onClick={() =>
                dispatch({
                  type: "SET_SETTINGS",
                  payload: { showGrid: !present.settings?.showGrid },
                })
              }
              title="Toggle Grid Dots"
              style={{ fontSize: 11, padding: "4px 8px" }}
            >
              ▦ Grid
            </button>
          </div>
        )}
      </div>

      {/* Right: Generate Dashboard + Export Menu + Right drawer toggle */}
      <div className="rpt-topbar-right">
        <button
          type="button"
          className="rpt-btn rpt-btn-primary"
          onClick={onGenerateDashboard}
          title="Auto-create recommended dashboard page"
        >
          ✨ Generate Dashboard
        </button>

        <div className="rpt-export-wrapper" style={{ position: "relative" }} ref={exportMenuRef}>
          <button
            type="button"
            className="rpt-btn"
            onClick={() => setExportMenuOpen(!exportMenuOpen)}
          >
            Export ▾
          </button>

          {exportMenuOpen && (
            <div
              className="rpt-export-menu"
              style={{
                position: "absolute",
                top: "100%",
                right: 0,
                marginTop: 4,
                backgroundColor: "#18181b",
                border: "1px solid #27272a",
                borderRadius: 6,
                boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
                zIndex: 100,
                minWidth: 160,
                padding: "4px 0",
              }}
            >
              <button
                type="button"
                className="rpt-export-menu-item"
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  color: "#e4e4e7",
                  fontSize: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExportMenuOpen(false);
                  onExportPdf?.();
                }}
              >
                📄 Export PDF (All Pages)
              </button>
              <button
                type="button"
                className="rpt-export-menu-item"
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  color: "#e4e4e7",
                  fontSize: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExportMenuOpen(false);
                  onExportPng?.();
                }}
              >
                🖼️ Export PNG (Current Page)
              </button>
              <button
                type="button"
                className="rpt-export-menu-item"
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 14px",
                  background: "transparent",
                  border: "none",
                  color: "#e4e4e7",
                  fontSize: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExportMenuOpen(false);
                  onExportCsv?.();
                }}
              >
                📊 Export CSV Data
              </button>
            </div>
          )}
        </div>

        {toggleRightDrawer && (
          <button
            type="button"
            className="rpt-btn rpt-mobile-drawer-toggle"
            onClick={toggleRightDrawer}
            title="Toggle Format & Filter Panel"
          >
            Right ☰
          </button>
        )}
      </div>
    </header>
  );
}
