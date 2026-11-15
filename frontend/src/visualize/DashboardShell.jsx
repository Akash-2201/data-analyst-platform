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
import {
  exportDashboardPdf,
  exportElementAsPng,
  exportDataAsCsv,
} from "./exportService";
import { generateAutoDashboardPage } from "./autoDashboard";

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
  const [exportProgress, setExportProgress] = useState(null);
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [leftPanelVisible, setLeftPanelVisible] = useState(true);
  const [rightPanelVisible, setRightPanelVisible] = useState(true);
  const canvasRef = useRef(null);
  const rootRef = useRef(null);
  const [rootHeight, setRootHeight] = useState(null);
  const [zoomMode, setZoomMode] = useState("fit"); // "fit" | number
  const [scale, setScale] = useState(1);
  const [fitScale, setFitScale] = useState(1);

  // Dynamic root height calculation to fill window without page-level scrollbar
  useEffect(() => {
    const updateHeight = () => {
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      const calculated = window.innerHeight - rect.top - 12;
      setRootHeight(Math.max(560, calculated));
    };

    updateHeight();
    window.addEventListener("resize", updateHeight);
    return () => window.removeEventListener("resize", updateHeight);
  }, []);

  const activePage = state.present.pages.find((p) => p.id === state.present.activePageId) || state.present.pages[0];

  const handleGenerateDashboard = () => {
    const autoPage = generateAutoDashboardPage(columns, state.present.pages);
    dispatch({ type: "ADD_GENERATED_PAGE", payload: autoPage });
  };

  const handleExportPdf = async () => {
    try {
      await exportDashboardPdf({
        dashboard: state.present,
        datasetFilename,
        canvasRef,
        onProgress: (msg) => setExportProgress(msg),
      });
    } catch (err) {
      console.error("PDF export failed", err);
      alert(`Export failed: ${err.message}`);
    } finally {
      setExportProgress(null);
    }
  };

  const handleExportPng = async () => {
    if (canvasRef.current) {
      await exportElementAsPng(canvasRef.current, `${datasetFilename}_${activePage?.name || "page"}`);
    }
  };

  const handleExportCsv = () => {
    // Collect sample rows from columns or tiles
    const rows = [];
    const colNames = (columns || []).map((c) => (typeof c === "string" ? c : c.name));
    for (let i = 0; i < 20; i++) {
      const row = {};
      columns.forEach((c) => {
        const name = typeof c === "string" ? c : c.name;
        row[name] = c.sample_values ? c.sample_values[i] : "";
      });
      rows.push(row);
    }
    exportDataAsCsv(`${datasetFilename}_data.csv`, rows, colNames);
  };

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
    zoom: {
      zoomMode,
      setZoomMode,
      scale,
      setScale,
      fitScale,
      setFitScale,
    },
  };

  return (
    <DashboardProvider value={contextValue}>
      <div
        ref={rootRef}
        className="rpt-dashboard-root"
        style={{ height: rootHeight ? `${rootHeight}px` : "calc(100vh - 60px)" }}
      >
        {/* LEFT PANEL (260px) */}
        <LeftPanel
          columns={columns}
          isOpen={leftDrawerOpen}
          isCollapsed={!leftPanelVisible}
        />

        {/* CENTER WORKSPACE */}
        <div className="rpt-center-col">
          {exportProgress && (
            <div
              style={{
                position: "absolute",
                top: 56,
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: 200,
                background: "#8b5cf6",
                color: "#ffffff",
                padding: "8px 16px",
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                boxShadow: "0 6px 20px rgba(0,0,0,0.5)",
              }}
            >
              ⏳ {exportProgress}
            </div>
          )}

          <TopBar
            onSave={handleSave}
            saveTime={saveTime}
            isSaving={isSaving}
            onGenerateDashboard={onGenerateDashboard || handleGenerateDashboard}
            onExportPdf={onExportPdf || handleExportPdf}
            onExportPng={onExportPng || handleExportPng}
            onExportCsv={onExportCsv || handleExportCsv}
            toggleLeftDrawer={() => {
              if (window.innerWidth <= 768) {
                setLeftDrawerOpen(!leftDrawerOpen);
              } else {
                setLeftPanelVisible(!leftPanelVisible);
              }
            }}
            toggleRightDrawer={() => {
              if (window.innerWidth <= 768) {
                setRightDrawerOpen(!rightDrawerOpen);
              } else {
                setRightPanelVisible(!rightPanelVisible);
              }
            }}
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
          isCollapsed={!rightPanelVisible}
        />
      </div>
    </DashboardProvider>
  );
}
