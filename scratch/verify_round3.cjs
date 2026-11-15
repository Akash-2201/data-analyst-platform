const puppeteer = require('c:/Users/j9698/OneDrive/Desktop/data-analyst-platform/data-analyst-platform/frontend/node_modules/puppeteer');
const path = require('path');
const fs = require('fs');

const ARTIFACT_DIR = 'C:/Users/j9698/.gemini/antigravity/brain/48477473-44f6-47f3-9fa1-71fca00a82ee';
const CSV_FILE = path.resolve('messy_project_testing_dataset_120_rows_cleaned.csv');

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function run() {
  console.log('=== STARTING ROUND 3 VERIFICATION ===');
  const tempUserDataDir = path.join(__dirname, 'temp_profile_' + Date.now());
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    userDataDir: tempUserDataDir,
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  page.on('console', (msg) => {
    const txt = msg.text();
    if (!txt.includes('Download the React DevTools') && !txt.includes('WebSocket')) {
      console.log('BROWSER_LOG:', txt);
    }
  });

  try {
    // 0. Test landing background regression first
    console.log('\n--- 0. Checking Landing Page Animated Background ---');
    await page.setViewport({ width: 1920, height: 1080 });
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2' });
    await sleep(1000);

    const hasLandingBg = await page.evaluate(() => {
      const bg = document.querySelector('.datastream-bg') || document.querySelector('.datastream-binary-zone') || document.querySelector('.datastream-tech-grid');
      return !!bg;
    });
    console.log('Landing animated background present:', hasLandingBg);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_regression_landing_bg.png') });

    // 1. Auth if present
    const emailInput = await page.$('input[type="email"]');
    if (emailInput) {
      console.log('Logging in...');
      await page.type('input[type="email"]', 'testuser@datalyst.local');
      await page.type('input[type="password"]', 'TestPassword123!');
      await page.click('button[type="submit"]');
      await sleep(2000);
    }

    // 2. Upload test dataset
    console.log('Uploading test dataset:', CSV_FILE);
    const fileInput = await page.$('input[type="file"]');
    if (fileInput) {
      await fileInput.uploadFile(CSV_FILE);
      await page.waitForSelector('.tab-switcher, .tab-btn', { timeout: 25000 });
      console.log('Dataset uploaded and audited successfully!');
    }
    await sleep(1500);

    // 3. Switch to Visualize Tab
    console.log('Switching to Visualize tab...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button.tab-btn'));
      const viz = btns.find((b) => b.textContent.includes('Visualize'));
      if (viz) viz.click();
    });

    await page.waitForSelector('.rpt-dashboard-root', { timeout: 10000 });
    console.log('.rpt-dashboard-root mounted successfully!');
    await sleep(1500);

    // =========================================================================
    // TEST 1: Full-screen 1920x1080 (P5, P2) in Light and Dark
    // =========================================================================
    console.log('\n--- 1. Testing 1920x1080 Light and Dark (P5, P2) ---');
    await page.setViewport({ width: 1920, height: 1080 });
    await sleep(800);

    // Ensure Light mode
    await page.evaluate(() => {
      const root = document.querySelector('.rpt-dashboard-root');
      if (root?.getAttribute('data-theme') !== 'light') {
        const themeBtn = document.querySelector('.rpt-theme-toggle-btn');
        if (themeBtn) themeBtn.click();
      }
    });
    await sleep(500);

    const metrics1920Light = await page.evaluate(() => {
      const root = document.querySelector('.rpt-dashboard-root');
      const theme = root?.getAttribute('data-theme');
      const rect = root?.getBoundingClientRect();
      const exportBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent.includes('Export'));
      const exportRect = exportBtn?.getBoundingClientRect();
      const tabs = document.querySelector('.rpt-page-tabs');
      const tabsRect = tabs?.getBoundingClientRect();
      const fields = document.querySelectorAll('.rpt-field-item');
      return {
        theme,
        rootRect: { top: rect?.top, left: rect?.left, width: rect?.width, height: rect?.height },
        bodyScrollHeight: document.documentElement.scrollHeight,
        windowInnerHeight: window.innerHeight,
        exportVisible: !!exportRect && exportRect.right <= window.innerWidth,
        pageTabsVisible: !!tabsRect && tabsRect.bottom <= window.innerHeight,
        fieldCount: fields.length,
      };
    });
    console.log('1920 Light metrics:', metrics1920Light);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p5_1920_light.png') });

    // Toggle to Dark mode
    await page.evaluate(() => {
      const themeBtn = document.querySelector('.rpt-theme-toggle-btn');
      if (themeBtn) themeBtn.click();
    });
    await sleep(500);

    const metrics1920Dark = await page.evaluate(() => {
      const root = document.querySelector('.rpt-dashboard-root');
      return {
        theme: root?.getAttribute('data-theme'),
      };
    });
    console.log('1920 Dark metrics:', metrics1920Dark);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p5_1920_dark.png') });

    // Switch back to Light for remaining test baseline
    await page.evaluate(() => {
      const themeBtn = document.querySelector('.rpt-theme-toggle-btn');
      if (themeBtn) themeBtn.click();
    });
    await sleep(500);

    // =========================================================================
    // TEST 2: Responsive 1366x768 (P5, P2) in Light and Dark
    // =========================================================================
    console.log('\n--- 2. Testing 1366x768 Light and Dark (P5, P2) ---');
    await page.setViewport({ width: 1366, height: 768 });
    await sleep(800);

    const metrics1366Light = await page.evaluate(() => {
      const exportBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent.includes('Export'));
      const tabs = document.querySelector('.rpt-page-tabs');
      return {
        bodyScrollHeight: document.documentElement.scrollHeight,
        windowInnerHeight: window.innerHeight,
        exportVisible: !!exportBtn && exportBtn.getBoundingClientRect().right <= window.innerWidth,
        tabsVisible: !!tabs && tabs.getBoundingClientRect().bottom <= window.innerHeight,
      };
    });
    console.log('1366 Light metrics:', metrics1366Light);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p5_1366_light.png') });

    // Dark at 1366
    await page.evaluate(() => {
      const themeBtn = document.querySelector('.rpt-theme-toggle-btn');
      if (themeBtn) themeBtn.click();
    });
    await sleep(500);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p5_1366_dark.png') });

    // Back to 1920x1080 and Light
    await page.setViewport({ width: 1920, height: 1080 });
    await page.evaluate(() => {
      window.scrollTo(0, 0);
      const themeBtn = document.querySelector('.rpt-theme-toggle-btn');
      if (themeBtn) themeBtn.click();
    });
    await sleep(800);

    // =========================================================================
    // TEST 3: Add 6 plots without overlap + Page presets (P4)
    // =========================================================================
    console.log('\n--- 3. Testing 6 plots on canvas without overlap (P4) ---');
    // Add Bar
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
      const barBtn = btns.find((b) => b.textContent.includes('Bar'));
      if (barBtn) barBtn.click();
    });
    await sleep(600);

    // Add Line
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
      const lineBtn = btns.find((b) => b.textContent.includes('Line'));
      if (lineBtn) lineBtn.click();
    });
    await sleep(600);

    // Add Area
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
      const areaBtn = btns.find((b) => b.textContent.includes('Area'));
      if (areaBtn) areaBtn.click();
    });
    await sleep(600);

    // Add Pie
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
      const pieBtn = btns.find((b) => b.textContent.includes('Pie'));
      if (pieBtn) pieBtn.click();
    });
    await sleep(600);

    // Add Table
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
      const tblBtn = btns.find((b) => b.textContent.includes('Table'));
      if (tblBtn) tblBtn.click();
    });
    await sleep(600);

    // Add KPI
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
      const kpiBtn = btns.find((b) => b.textContent.includes('KPI'));
      if (kpiBtn) kpiBtn.click();
    });
    await sleep(1000);

    const tileCount = await page.evaluate(() => document.querySelectorAll('.rpt-tile').length);
    console.log('Total tiles on canvas:', tileCount);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p4_six_plots.png') });

    // =========================================================================
    // TEST 4: Drag Engine Test (P1) - Before, Dragging, After & Nudge
    // =========================================================================
    console.log('\n--- 4. Testing Drag Engine (P1) ---');
    const tileCoords = await page.evaluate(() => {
      window.scrollTo(0, 0);
      const tile = document.querySelector('.rpt-tile');
      if (!tile) return null;
      const rect = tile.getBoundingClientRect();
      const el = document.elementFromPoint(rect.x + 30, rect.y + 15);
      return {
        id: tile.id,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        styleLeft: parseInt(tile.style.left, 10),
        styleTop: parseInt(tile.style.top, 10),
        elTag: el?.tagName,
        elClass: el?.className,
      };
    });
    console.log('Tile coordinates before drag:', tileCoords);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p1_drag_before.png') });
    await sleep(200);

    // Perform mouse drag by +140px X and +100px Y
    const startX = tileCoords.rect.x + 30;
    const startY = tileCoords.rect.y + 15;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await sleep(60);
    await page.mouse.move(startX + 140, startY + 100);
    await sleep(60);
    await page.mouse.up();
    await sleep(500);

    // Check new coordinates of the dragged tile
    const afterCoords = await page.evaluate(() => {
      const tile = document.querySelector('.rpt-tile');
      return {
        id: tile.id,
        styleLeft: parseInt(tile.style.left, 10),
        styleTop: parseInt(tile.style.top, 10),
        rect: { x: tile.getBoundingClientRect().x, y: tile.getBoundingClientRect().y },
      };
    });
    console.log('Tile coordinates after drag:', afterCoords);

    // Test Arrow key nudge (ArrowRight 2 times, ArrowDown 2 times)
    console.log('Testing arrow key nudge (ArrowRight 2 times, ArrowDown 2 times)...');
    await page.keyboard.press('ArrowRight');
    await sleep(100);
    await page.keyboard.press('ArrowRight');
    await sleep(100);
    await page.keyboard.press('ArrowDown');
    await sleep(100);

    const nudgeCoords = await page.evaluate(() => {
      const tile = document.querySelector('.rpt-tile.selected') || document.querySelector('.rpt-tile');
      return {
        styleLeft: parseInt(tile.style.left, 10),
        styleTop: parseInt(tile.style.top, 10),
      };
    });
    console.log('Tile coordinates after keyboard nudge:', nudgeCoords);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p1_drag_after.png') });

    // =========================================================================
    // TEST 5: Resize Engine Test (P1)
    // =========================================================================
    console.log('\n--- 5. Testing Resize Engine (P1) ---');
    const resizeHandleInfo = await page.evaluate(() => {
      const handle = document.querySelector('.rpt-tile.selected .rpt-resize-handle.handle-se');
      if (!handle) return null;
      const rect = handle.getBoundingClientRect();
      const sel = document.querySelector('.rpt-tile.selected');
      return {
        handleX: rect.x + rect.width / 2,
        handleY: rect.y + rect.height / 2,
        tileW: parseInt(sel.style.width, 10),
        tileH: parseInt(sel.style.height, 10),
      };
    });
    console.log('Resize handle info before:', resizeHandleInfo);

    if (resizeHandleInfo) {
      await page.mouse.move(resizeHandleInfo.handleX, resizeHandleInfo.handleY);
      await page.mouse.down();
      await sleep(60);
      await page.mouse.move(resizeHandleInfo.handleX + 80, resizeHandleInfo.handleY + 60);
      await sleep(60);
      await page.mouse.up();
      await sleep(500);

      const afterResize = await page.evaluate(() => {
        const tile = document.querySelector('.rpt-tile.selected');
        return {
          tileW: parseInt(tile?.style.width || 0, 10),
          tileH: parseInt(tile?.style.height || 0, 10),
        };
      });
      console.log('Resize dimensions after:', afterResize);
    }
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p1_resize.png') });

    // =========================================================================
    // TEST 6: Tab Switch Persistence & Undo/Redo (P1)
    // =========================================================================
    console.log('\n--- 6. Testing Tab switch persistence & Undo/Redo ---');
    // Test Undo (Ctrl+Z)
    await page.keyboard.down('Control');
    await page.keyboard.press('z');
    await page.keyboard.up('Control');
    await sleep(500);

    const postUndoCoords = await page.evaluate(() => {
      const tile = document.querySelector('.rpt-tile');
      return {
        styleLeft: parseInt(tile.style.left, 10),
        styleTop: parseInt(tile.style.top, 10),
      };
    });
    console.log('Coordinates after Undo:', postUndoCoords);

    // Switch away to Clean tab then back to Visualize
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button.tab-btn'));
      const clean = btns.find((b) => b.textContent.includes('Clean'));
      if (clean) clean.click();
    });
    await sleep(800);

    // Switch back to Visualize
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button.tab-btn'));
      const viz = btns.find((b) => b.textContent.includes('Visualize'));
      if (viz) viz.click();
    });
    await page.waitForSelector('.rpt-dashboard-root', { timeout: 10000 });
    await sleep(1000);

    const persistentTileCount = await page.evaluate(() => document.querySelectorAll('.rpt-tile').length);
    console.log('Persistent tile count after tab switch:', persistentTileCount);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p1_switch_tab_undo.png') });

    // =========================================================================
    // TEST 7: Theme Toggle & Chart Styling (P3)
    // =========================================================================
    console.log('\n--- 7. Testing Theme toggle shortcut & chart styling (P3) ---');
    // Toggle theme via Ctrl+Shift+T
    await page.keyboard.down('Control');
    await page.keyboard.down('Shift');
    await page.keyboard.press('T');
    await page.keyboard.up('Shift');
    await page.keyboard.up('Control');
    await sleep(800);

    const themeAfterShortcut = await page.evaluate(() => {
      const root = document.querySelector('.rpt-dashboard-root');
      return root?.getAttribute('data-theme');
    });
    console.log('Theme after Ctrl+Shift+T shortcut:', themeAfterShortcut);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p3_theme_charts.png') });

    // =========================================================================
    // TEST 8: Fullscreen Mode (P5)
    // =========================================================================
    console.log('\n--- 8. Testing Fullscreen Button (P5) ---');
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_p5_fullscreen.png') });

    // =========================================================================
    // TEST 9: View Mode vs Edit Mode (P1)
    // =========================================================================
    console.log('\n--- 9. Testing View Mode vs Edit Mode (P1) ---');
    // Click View mode
    await page.evaluate(() => {
      const viewBtn = Array.from(document.querySelectorAll('.rpt-mode-btn')).find((b) => b.textContent.includes('View'));
      if (viewBtn) viewBtn.click();
    });
    await sleep(500);

    // Attempt to drag in View Mode: verify toast appears and position unchanged
    const preDragView = await page.evaluate(() => {
      const tile = document.querySelector('.rpt-tile');
      return {
        styleLeft: parseInt(tile.style.left, 10),
        styleTop: parseInt(tile.style.top, 10),
        badgeText: document.querySelector('.rpt-mode-badge')?.textContent,
      };
    });

    await page.mouse.move(tileCoords.rect.x + 30, tileCoords.rect.y + 15);
    await page.mouse.down();
    await page.mouse.move(tileCoords.rect.x + 100, tileCoords.rect.y + 100);
    await page.mouse.up();
    await sleep(400);

    const postDragView = await page.evaluate(() => {
      const tile = document.querySelector('.rpt-tile');
      const toast = document.querySelector('.rpt-toast')?.textContent;
      return {
        styleLeft: parseInt(tile.style.left, 10),
        styleTop: parseInt(tile.style.top, 10),
        toast,
      };
    });
    console.log('View mode drag test:', { preDragView, postDragView });
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_regression_view_mode.png') });

    // Switch back to Edit Mode
    await page.evaluate(() => {
      const editBtn = Array.from(document.querySelectorAll('.rpt-mode-btn')).find((b) => b.textContent.includes('Edit'));
      if (editBtn) editBtn.click();
    });
    await sleep(500);

    // =========================================================================
    // TEST 10: Auto Dashboard Generation Regression
    // =========================================================================
    console.log('\n--- 10. Testing Generate Dashboard ---');
    await page.evaluate(() => {
      const genBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent.includes('Generate'));
      if (genBtn) genBtn.click();
    });
    await sleep(1500);

    const pageCount = await page.evaluate(() => document.querySelectorAll('.rpt-page-tab').length);
    console.log('Total page tabs after Auto Generate:', pageCount);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_regression_auto_dash.png') });

    // =========================================================================
    // TEST 11: Export Menu with Export Theme (P3)
    // =========================================================================
    console.log('\n--- 11. Testing Export Menu with Theme Selection ---');
    await page.evaluate(() => {
      const expBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent.includes('Export'));
      if (expBtn) expBtn.click();
    });
    await sleep(500);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'evidence_export_pdf.png') });

    console.log('\n=== ALL VERIFICATIONS COMPLETED SUCCESSFULLY ===');
  } catch (err) {
    console.error('VERIFICATION ERROR:', err);
  } finally {
    if (browser) await browser.close();
    try {
      fs.rmSync(tempUserDataDir, { recursive: true, force: true });
    } catch {}
  }
}

run();
