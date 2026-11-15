const puppeteer = require('c:/Users/j9698/OneDrive/Desktop/data-analyst-platform/data-analyst-platform/frontend/node_modules/puppeteer');
const path = require('path');
const fs = require('fs');

(async () => {
  const tempDir = path.join(__dirname, 'temp_inspect_' + Date.now());
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
    userDataDir: tempDir
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  await page.goto('http://127.0.0.1:5173');

  const emailInput = await page.$('input[type="email"]');
  if (emailInput) {
    await page.type('input[type="email"]', 'testuser@datalyst.local');
    await page.type('input[type="password"]', 'TestPassword123!');
    await page.click('button[type="submit"]');
    await new Promise(r => setTimeout(r, 2000));
  }

  const fileInput = await page.$('input[type="file"]');
  if (fileInput) {
    await fileInput.uploadFile(path.resolve('messy_project_testing_dataset_120_rows_cleaned.csv'));
    await page.waitForSelector('.tab-btn', { timeout: 20000 });
  }

  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('.tab-btn'));
    const viz = btns.find(b => b.textContent.includes('Visualize'));
    if (viz) viz.click();
  });

  await new Promise(r => setTimeout(r, 1200));

  const info = await page.evaluate(() => {
    const root = document.querySelector('.rpt-dashboard-root');
    const tabs = document.querySelector('.rpt-page-tabs');
    const tabSwitcher = document.querySelector('.tab-switcher');
    const navbar = document.querySelector('.app-navbar');
    const vizContainer = document.querySelector('.viz-tab-container');
    const reportWrapper = document.querySelector('.report-wrapper');
    return {
      navbarBottom: navbar?.getBoundingClientRect().bottom,
      tabSwitcherTop: tabSwitcher?.getBoundingClientRect().top,
      tabSwitcherBottom: tabSwitcher?.getBoundingClientRect().bottom,
      reportWrapperTop: reportWrapper?.getBoundingClientRect().top,
      vizContainerTop: vizContainer?.getBoundingClientRect().top,
      rootTop: root?.getBoundingClientRect().top,
      rootBottom: root?.getBoundingClientRect().bottom,
      rootHeight: root?.getBoundingClientRect().height,
      tabsBottom: tabs?.getBoundingClientRect().bottom,
      windowH: window.innerHeight,
    };
  });
  console.log('LAYOUT INFO:', info);
  await browser.close();
  try { fs.rmSync(tempDir, { recursive: true, force: true }); } catch {}
})();
