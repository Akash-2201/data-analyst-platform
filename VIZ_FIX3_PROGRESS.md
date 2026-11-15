# VIZ FIX 3 PROGRESS

Project Root: `C:\Users\j9698\OneDrive\Desktop\data-analyst-platform\data-analyst-platform`

## Status Overview
- [x] STEP 0: DIAGNOSE (no edits)
- [x] STEP 1: TRUE FULL-SCREEN LAYOUT (P5)
- [x] STEP 2: DATA FIELDS ALWAYS VISIBLE (P2)
- [x] STEP 3: BIGGER, RESIZABLE PAGES (P4)
- [x] STEP 4: NEW DRAG/RESIZE ENGINE (P1)
- [ ] STEP 5: LIGHT / DARK THEME (P3)
- [ ] STEP 6 / VERIFY: Real evidence & screenshots

## Diagnostic Findings (STEP 0)
- **a) Edit vs View Mode**: Mode defaults to `"edit"` in initial dashboard state (`utils.js`), toggled via pills in `TopBar.jsx`. However, there is no explicit visual badge indicating the current mode, and in View mode interactions simply fail silently without explanation toast.
- **b) Why Drag Fails Today**: Tile wrapper had `onPointerDownCapture` / `onMouseDownCapture` calling `e.stopPropagation()`. This stopped the event from propagating to `react-grid-layout`'s internal `react-draggable` listener, preventing RGL from ever receiving the drag start. In addition, RGL's CSS transform scale calculations and column-based layout conflicts with freeform pixel positioning.
- **c) Why Data Fields Is Not Visible**: The left panel rendered 12 visualization tiles in 3 columns (260px), collapsible more charts, and 4 smart recommendation cards (240px) above the Data Fields section in a single outer `overflow-y: auto` container without accordion constraints. Because total content above exceeded 500px, Data Fields was physically pushed below the screen fold. Field count is verified at 17 columns (data is present, not empty).
- **d) Page Size & Canvas Ancestor Chain**: Canvas was hardcoded to `1280x720` with no custom page size support. The ancestor chain is `html, body` -> `.page.viz-active` -> `.report-wrapper` -> `.viz-tab-container` -> `.rpt-dashboard-root`. Ancestor `.page` in `App.css` enforces `max-width: 1000px; padding: 0 24px 96px`.
- **e) Chat Bubble Z-Index**: `.chat-toggle-btn` and `.chat-panel` in `App.css` have `z-index: 1000`. The fixed Visualize workspace will use `z-index: 40`, comfortably below 1000 so the chat floating bubble remains fully accessible.
- **f) Hard-coded Theme Colors**:
  - `visualize.css` and JSX renderers hard-code dark zinc tones (`#09090b`, `#121215`, `#18181b`, `#27272a`, `#3f3f46`, `#52525b`, `#a1a1aa`, `#f4f4f5`).
  - `renderSharedChart` in `ChartComponents.jsx` uses `var(--line)` and hardcoded white text for some shapes. Scoped CSS rules on `.rpt-legacy` will dynamically adapt them to `--rpt-chart-text` and `--rpt-chart-grid`.

## Root Causes in Plain Words
1. **P1 (Cannot move charts)**: Tile click event handlers stopped mousedown event propagation, preventing `react-grid-layout` from ever detecting drag gestures.
2. **P2 (Data Fields cut off)**: Visualization tiles and smart recommendation cards stacked above Data Fields pushed it off-screen in a non-accordion flex layout.
3. **P3 (No light theme)**: No theme state or top-bar toggle existed, and colors were hard-coded in dark hex values throughout the styles.
4. **P4 (Canvas too small)**: Canvas dimensions were locked to a single 1280×720 size with no custom dimensions, presets, or auto-grow capability.
5. **P5 (Wasted screen space)**: The workspace was mounted inside normal document flow subject to ancestor page margins, headers, and paddings rather than using a fixed full-screen viewport layout.
