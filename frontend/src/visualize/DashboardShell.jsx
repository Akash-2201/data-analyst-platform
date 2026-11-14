/**
 * frontend/src/visualize/DashboardShell.jsx
 * Root shell orchestrating the 3-column Power BI dashboard layout,
 * state reducer, keyboard shortcuts, and storage persistence.
 */

import React, { useReducer, useState, useEffect, useRef, useCallback } from "react";
import "./visualize.css";
import { makeInitialDashboard } from "./utils";
import { dashboardReducer, createInitialState } from "./dashboardReducer";
import { DashboardProvider } from "./dashboardContext";
import { TopBar } from "./TopBar";
import { PageTabs } from "./PageTabs";
import { LeftPanel } from "./LeftPanel";
import { RightPanel } from "./RightPanel";
import { Canvas } from "./Canvas";

export function DashboardShell({
  datasetId,
  columns = [],
  datasetFilename = "Dashboard",
  userId = "default",
  renderTileContent,
  onExportPdf,
  onExportPng,
  onExportCsv,
  onGenerateDashboard,
}) {
  const storageKey = `datalyst_dash_${userId}_${datasetId || "temp"}`;

  // Initialize from localStorage if exists, else create default
  const getInitialState = () => {
    try {
      if (datasetId) {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (parsed && Array.isArray(parsed.pages) && parsed.pages.length > 0) {
            return createInitialState({ ...parsed, mode: "edit", selectedTileIds: [] });
          }
        }
      }
    } catch (e) {
      console.warn("Could not read dashboard from localStorage", e);
    }
    return createInitialState(makeInitialDashboard(datasetFilename));
  };

  const [state, dispatch] = useReducer(dashboardReducer, null, getInitialState);
  const [saveTime, setSaveTime] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const canvasRef = useRef(null);

  // Autosave draft (debounced by 2 seconds)
  useEffect(() => {
    if (!datasetId) return;
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(state.present));
      } catch (err) {
        console.warn("Autosave to localStorage failed", err);
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, [state.present, datasetId, storageKey]);

  // Explicit Save
  const handleSave = useCallback(() => {
    setIsSaving(true);
    try {
      if (datasetId) {
        localStorage.setItem(storageKey, JSON.stringify(state.present));
      }
      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
      setSaveTime(timeStr);
    } catch (err) {
      console.error("Save failed", err);
    } finally {
      setIsSaving(false);
    }
  }, [datasetId, storageKey, state.present]);

  // Keyboard Shortcuts (Delete, Ctrl+C, Ctrl+V, Ctrl+D, Ctrl+Z, Ctrl+Y)
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't intercept if inside an input/textarea
      const tag = e.target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;

      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modKey = isMac ? e.metaKey : e.ctrlKey;

      if (e.key === "Delete" || e.key === "Backspace") {
        if (state.present.mode === "edit" && state.present.selectedTileIds.length > 0) {
          e.preventDefault();
          dispatch({ type: "DELETE_TILES" });
        }
      } else if (modKey && e.key.toLowerCase() === "z" && !e.shiftKey) {
        e.preventDefault();
        dispatch({ type: "UNDO" });
      } else if ((modKey && e.key.toLowerCase() === "y") || (modKey && e.shiftKey && e.key.toLowerCase() === "z")) {
        e.preventDefault();
        dispatch({ type: "REDO" });
      } else if (modKey && e.key.toLowerCase() === "c") {
        if (state.present.selectedTileIds.length > 0) {
          e.preventDefault();
          dispatch({ type: "COPY_TILES" });
        }
      } else if (modKey && e.key.toLowerCase() === "v") {
        if (state.present.mode === "edit" && state.present.clipboard) {
          e.preventDefault();
          dispatch({ type: "PASTE_TILES" });
        }
      } else if (modKey && e.key.toLowerCase() === "d") {
        if (state.present.mode === "edit" && state.present.selectedTileIds.length > 0) {
          e.preventDefault();
          dispatch({ type: "DUPLICATE_TILES" });
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.present.mode, state.present.selectedTileIds, state.present.clipboard]);

  const contextValue = {
    state,
    dispatch,
    activePage: state.present.pages.find((p) => p.id === state.present.activePageId) || state.present.pages[0],
  };

  return (
    <DashboardProvider value={contextValue}>
      <div className="rpt-dashboard-root">
        {/* LEFT PANEL (260px) */}
        <LeftPanel
          columns={columns}
          isOpen={leftDrawerOpen}
        />

        {/* CENTER WORKSPACE */}
        <div className="rpt-center-col">
          <TopBar
            onSave={handleSave}
            saveTime={saveTime}
            isSaving={isSaving}
            onGenerateDashboard={onGenerateDashboard}
            onExportPdf={onExportPdf}
            onExportPng={onExportPng}
            onExportCsv={onExportCsv}
            toggleLeftDrawer={() => setLeftDrawerOpen(!leftDrawerOpen)}
            toggleRightDrawer={() => setRightDrawerOpen(!rightDrawerOpen)}
          />

          <Canvas
            datasetId={datasetId}
            columns={columns}
            renderTileContent={renderTileContent}
            canvasRef={canvasRef}
          />

          <PageTabs />
        </div>

        {/* RIGHT PANEL (300px) */}
        <RightPanel
          columns={columns}
          isOpen={rightDrawerOpen}
        />
      </div>
    </DashboardProvider>
  );
}
