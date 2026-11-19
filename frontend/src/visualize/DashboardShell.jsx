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
  isActive = true,
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
  const [toastMsg, setToastMsg] = useState("");
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [workspaceTop, setWorkspaceTop] = useState(0);

  const showToast = useCallback((msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(""), 3000);
  }, []);

  // Panel visibility remembered in session
  const [leftPanelVisible, setLeftPanelVisible] = useState(() => {
    try {
      const s = sessionStorage.getItem("datalyst_viz_left_visible");
      return s !== null ? JSON.parse(s) : true;
    } catch {
      return true;
    }
  });
  const [rightPanelVisible, setRightPanelVisible] = useState(() => {
    try {
      const s = sessionStorage.getItem("datalyst_viz_right_visible");
      return s !== null ? JSON.parse(s) : true;
    } catch {
      return true;
    }
  });

  const toggleLeftPanel = useCallback(() => {
    setLeftPanelVisible((prev) => {
      const next = !prev;
      try { sessionStorage.setItem("datalyst_viz_left_visible", JSON.stringify(next)); } catch { }
      return next;
    });
  }, []);

  const toggleRightPanel = useCallback(() => {
    setRightPanelVisible((prev) => {
      const next = !prev;
      try { sessionStorage.setItem("datalyst_viz_right_visible", JSON.stringify(next)); } catch { }
      return next;
    });
  }, []);

  const canvasRef = useRef(null);
  const rootRef = useRef(null);
  const placeholderRef = useRef(null);
  const [zoomMode, setZoomMode] = useState("fitWidth"); // "fitWidth" | "fitPage" | number
  const [scale, setScale] = useState(1);
  const [fitScale, setFitScale] = useState(1);

  // Measure top offset relative to document top so fixed workspace starts exactly below navbar/tabs
  const measureTop = useCallback(() => {
    window.scrollTo(0, 0);
    if (placeholderRef.current) {
      const rect = placeholderRef.current.getBoundingClientRect();
      setWorkspaceTop(Math.max(0, Math.round(rect.top)));
    }
  }, []);

  useEffect(() => {
    if (!isActive) {
      // Not the active tab — ensure body can scroll
      document.body.style.overflow = "";
      return;
    }
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    measureTop();
    window.addEventListener("resize", measureTop);
    const interval = setInterval(measureTop, 600);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("resize", measureTop);
      clearInterval(interval);
    };
  }, [measureTop, isActive]);

  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const handleToggleFullscreen = async () => {
    try {
      if (!document.fullscreenElement) {
        if (rootRef.current?.requestFullscreen) {
          await rootRef.current.requestFullscreen();
        }
      } else {
        if (document.exitFullscreen) {
          await document.exitFullscreen();
        }
      }
    } catch (err) {
      console.warn("Fullscreen toggle error:", err);
      showToast("Fullscreen blocked by browser");
    }
  };

  const activePage = state.present.pages.find((p) => p.id === state.present.activePageId) || state.present.pages[0];
  const theme = state.present.settings?.theme || "light";

  const handleToggleTheme = useCallback((targetTheme) => {
    const next = targetTheme || (theme === "light" ? "dark" : "light");
    try {
      localStorage.setItem("datalyst_viz_theme", next);
    } catch { }
    dispatch({
      type: "SET_SETTINGS",
      payload: { theme: next },
    });
    showToast(`Switched to ${next} theme`);
  }, [theme, dispatch, showToast]);

  const handleGenerateDashboard = () => {
    const autoPage = generateAutoDashboardPage(columns, state.present.pages);
    dispatch({ type: "ADD_GENERATED_PAGE", payload: autoPage });
  };

  const handleExportPdf = async (exportTheme = "current") => {
    try {
      await exportDashboardPdf({
        dashboard: state.present,
        datasetFilename,
        canvasRef,
        exportTheme,
        currentTheme: theme,
        onProgress: (msg) => setExportProgress(msg),
      });
    } catch (err) {
      console.error("PDF export failed", err);
      alert(`Export failed: ${err.message}`);
    } finally {
      setExportProgress(null);
    }
  };

  const handleExportPng = async (exportTheme = "current") => {
    if (canvasRef.current) {
      await exportElementAsPng(
        canvasRef.current,
        `${datasetFilename}_${activePage?.name || "page"}`,
        exportTheme,
        theme
      );
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
      } else if (modKey && e.shiftKey && e.key.toLowerCase() === "t") {
        e.preventDefault();
        handleToggleTheme();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.present.mode, state.present.selectedTileIds, state.present.clipboard, handleToggleTheme]);

  const contextValue = {
    state,
    dispatch,
    theme,
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
      {/* Normal flow placeholder to measure top offset below tabs & navbar */}
      <div ref={placeholderRef} style={{ width: "100%", height: 0, visibility: "hidden" }} />

      {/* Floating Toast */}
      {toastMsg && (
        <div
          className="rpt-toast"
          style={{
            position: "fixed",
            bottom: 32,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 9999,
            background: "#8b5cf6",
            color: "#ffffff",
            padding: "8px 18px",
            borderRadius: 20,
            fontSize: 12,
            fontWeight: 600,
            boxShadow: "0 6px 20px rgba(0,0,0,0.5)",
            pointerEvents: "none",
          }}
        >
          {toastMsg}
        </div>
      )}

      {/* Fixed Fullscreen Workspace */}
      <div
        ref={rootRef}
        className="rpt-dashboard-root"
        data-theme={theme}
        style={{
          position: "fixed",
          left: 0,
          right: 0,
          bottom: 0,
          top: isFullscreen ? 0 : `${workspaceTop}px`,
          zIndex: 40,
          width: "100vw",
          height: isFullscreen ? "100vh" : `calc(100vh - ${workspaceTop}px)`,
        }}
      >
        {/* LEFT PANEL (240px) */}
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
            onExportPdf={handleExportPdf}
            onExportPng={handleExportPng}
            onExportCsv={onExportCsv || handleExportCsv}
            isFullscreen={isFullscreen}
            onToggleFullscreen={handleToggleFullscreen}
            theme={theme}
            onToggleTheme={handleToggleTheme}
            toggleLeftDrawer={() => {
              if (window.innerWidth <= 768) {
                setLeftDrawerOpen(!leftDrawerOpen);
              } else {
                toggleLeftPanel();
              }
            }}
            toggleRightDrawer={() => {
              if (window.innerWidth <= 768) {
                setRightDrawerOpen(!rightDrawerOpen);
              } else {
                toggleRightPanel();
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

        {/* RIGHT PANEL (280px) */}
        <RightPanel
          columns={columns}
          isOpen={rightDrawerOpen}
          isCollapsed={!rightPanelVisible}
        />
      </div>
    </DashboardProvider>
  );
}
