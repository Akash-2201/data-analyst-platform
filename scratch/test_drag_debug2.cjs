const puppeteer = require('c:/Users/j9698/OneDrive/Desktop/data-analyst-platform/data-analyst-platform/frontend/node_modules/puppeteer');
const path = require('path');
const fs = require('fs');

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

(async () => {
  const tempUserDataDir = path.join(__dirname, 'temp_debug2_' + Date.now());
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    userDataDir: tempUserDataDir,
    defaultViewport: { width: 1920, height: 1080 },
  });

  try {
    const page = await browser.newPage();
    page.on('console', (msg) => console.log('PAGE_LOG:', msg.text()));

    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0' });

    // Quick login if needed
    const loginBtn = await page.$('.auth-submit-btn, button[type="submit"]');
    if (loginBtn) {
      await page.type('input[type="email"], input[placeholder*="email" i]', 'test@example.com');
      await page.type('input[type="password"]', 'password123');
      await loginBtn.click();
      await sleep(1000);
    }

    // Upload dataset
    const fileInput = await page.$('input[type="file"]');
    if (fileInput) {
      const csvPath = path.resolve('messy_project_testing_dataset_120_rows_cleaned.csv');
      await fileInput.uploadFile(csvPath);
      await sleep(2000);
    }

    // Switch to Visualize tab
    await page.evaluate(() => {
      const tabs = Array.from(document.querySelectorAll('.tab-btn'));
      const viz = tabs.find((t) => t.textContent.includes('Visualize'));
      if (viz) viz.click();
    });
    await sleep(1500);

    // Add 6 charts
    for (const kind of ['Bar', 'Line', 'Area', 'Pie', 'Table', 'KPI']) {
      await page.evaluate((k) => {
        const btns = Array.from(document.querySelectorAll('.rpt-left-panel button'));
        const b = btns.find((btn) => btn.textContent.includes(k));
        if (b) b.click();
      }, kind);
      await sleep(500);
    }

    const tileCount = await page.evaluate(() => document.querySelectorAll('.rpt-tile').length);
    console.log('Total tiles on canvas:', tileCount);

    // Test dragging the FIRST tile (Bar)
    const before = await page.evaluate(() => {
      const t = document.querySelector('.rpt-tile');
      const rect = t.getBoundingClientRect();
      const elAtPoint = document.elementFromPoint(rect.x + 30, rect.y + 15);
      return {
        id: t.id,
        x: parseInt(t.style.left, 10),
        y: parseInt(t.style.top, 10),
        w: parseInt(t.style.width, 10),
        h: parseInt(t.style.height, 10),
        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
        elTag: elAtPoint?.tagName,
        elClass: elAtPoint?.className,
      };
    });
    console.log('Tile 1 before drag:', before);

    // Click and drag tile 1
    const startX = before.rect.x + 30;
    const startY = before.rect.y + 15;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await sleep(60);
    await page.mouse.move(startX + 140, startY + 100);
    await sleep(60);
    await page.mouse.up();
    await sleep(500);

    const afterDrag = await page.evaluate(() => {
      const t = document.querySelector('.rpt-tile');
      return {
        id: t.id,
        x: parseInt(t.style.left, 10),
        y: parseInt(t.style.top, 10),
        w: parseInt(t.style.width, 10),
        h: parseInt(t.style.height, 10),
      };
    });
    console.log('Tile 1 after drag:', afterDrag);

    // Test resize on Tile 1
    const resizeInfo = await page.evaluate(() => {
      const handle = document.querySelector('.rpt-tile.selected .rpt-resize-handle.handle-se');
      if (!handle) return { noHandle: true };
      const rect = handle.getBoundingClientRect();
      const elAtHandle = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return {
        hx: rect.x + rect.width / 2,
        hy: rect.y + rect.height / 2,
        elTag: elAtHandle?.tagName,
        elClass: elAtHandle?.className,
      };
    });
    console.log('Resize handle info:', resizeInfo);

    if (!resizeInfo.noHandle) {
      await page.mouse.move(resizeInfo.hx, resizeInfo.hy);
      await page.mouse.down();
      await sleep(60);
      await page.mouse.move(resizeInfo.hx + 80, resizeInfo.hy + 60);
      await sleep(60);
      await page.mouse.up();
      await sleep(500);

      const afterResize = await page.evaluate(() => {
        const t = document.querySelector('.rpt-tile.selected');
        return {
          id: t?.id,
          x: parseInt(t.style.left, 10),
          y: parseInt(t.style.top, 10),
          w: parseInt(t.style.width, 10),
          h: parseInt(t.style.height, 10),
        };
      });
      console.log('Tile 1 after resize:', afterResize);
    }
  } finally {
    await browser.close();
    try {
      fs.rmSync(tempUserDataDir, { recursive: true, force: true });
    } catch {}
  }
})();
