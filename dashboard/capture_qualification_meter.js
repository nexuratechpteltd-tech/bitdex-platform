const puppeteer = require('puppeteer');

const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJVU1ItOTA0NDI0QjRGQiIsImVtYWlsIjoiYWxpYWptYWx0Y2EyMkBnbWFpbC5jb20iLCJyb2xlIjoiQ1VTVE9NRVIiLCJzZXNzaW9uX2lkIjoiU0VTLTFBRUNENUVFMUI2NzgxNjUiLCJyZW1lbWJlcl9tZSI6dHJ1ZSwiZXhwIjoxNzk2Nzc1MDQ4fQ.ukAGpEBxMqYMGpV0qhBz45zBp8w0_tJP63807wCW2O0';

const ALI_USER = {
  user_id: "USR-904424B4FB",
  email: "aliajmaltca22@gmail.com",
  username: "ali_trader",
  role: "CUSTOMER",
  status: "ACTIVE",
  first_name: "Ali",
  last_name: "Ajmal",
  country: "AU",
  session_id: "SES-1AECD5EE1B678165"
};

async function run() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  // ══════════════════════════════════════════════════════════════════════════
  // A. DESKTOP VIEW (1440x950)
  // ══════════════════════════════════════════════════════════════════════════
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 950 });

  await page.goto('http://127.0.0.1:33900', { waitUntil: 'domcontentloaded' });
  await page.evaluate((tok, usr) => {
    localStorage.clear();
    localStorage.setItem('tauric_session_token', tok);
    localStorage.setItem('tauric_auth_token', tok);
    localStorage.setItem('bitdex_auth_token', tok);
    localStorage.setItem('tauric_session_user', JSON.stringify(usr));
  }, TOKEN, ALI_USER);

  await page.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2000));

  // If still on overview, click Open Scalping Engine Workspace button
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const btn = buttons.find(b => b.textContent && b.textContent.includes('Scalping Engine Workspace'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 3000));

  // Wait for qualification meter to render
  await page.waitForSelector('#live-opportunity-qualification-meter-section', { timeout: 10000 });
  console.log('FOUND: #live-opportunity-qualification-meter-section on Desktop');

  // Scroll to the Qualification Meter section
  await page.evaluate(() => {
    const el = document.getElementById('live-opportunity-qualification-meter-section');
    if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
  });
  await new Promise(r => setTimeout(r, 1500));

  // Capture Desktop 1: Default Collapsed State
  await page.screenshot({ path: '/tmp/qualification_meter_desktop_collapsed.png' });
  console.log('CAPTURED: /tmp/qualification_meter_desktop_collapsed.png');

  // Click View Detailed Analysis toggle
  await page.evaluate(() => {
    const btn = document.getElementById('btn-toggle-qualification-details');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  // Scroll to show expanded content
  await page.evaluate(() => {
    const el = document.getElementById('qualification-details-expanded-container');
    if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' });
  });
  await new Promise(r => setTimeout(r, 1500));

  // Capture Desktop 2: Expanded State (Pipeline + Why trade hasn't executed + 10 Gates)
  await page.screenshot({ path: '/tmp/qualification_meter_desktop_expanded.png' });
  console.log('CAPTURED: /tmp/qualification_meter_desktop_expanded.png');

  // Open Raw Technical Metrics drawer
  await page.evaluate(() => {
    const techBtn = document.getElementById('btn-toggle-raw-technical-metrics');
    if (techBtn) techBtn.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: '/tmp/qualification_meter_desktop_technical_metrics.png' });
  console.log('CAPTURED: /tmp/qualification_meter_desktop_technical_metrics.png');

  // ══════════════════════════════════════════════════════════════════════════
  // B. MOBILE VIEW (390x844 - iPhone 14/15)
  // ══════════════════════════════════════════════════════════════════════════
  const mobilePage = await browser.newPage();
  await mobilePage.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });

  await mobilePage.goto('http://127.0.0.1:33900', { waitUntil: 'domcontentloaded' });
  await mobilePage.evaluate((tok, usr) => {
    localStorage.clear();
    localStorage.setItem('tauric_session_token', tok);
    localStorage.setItem('tauric_auth_token', tok);
    localStorage.setItem('bitdex_auth_token', tok);
    localStorage.setItem('tauric_session_user', JSON.stringify(usr));
  }, TOKEN, ALI_USER);

  await mobilePage.goto('http://127.0.0.1:33900/#hft', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2000));

  // If still on overview, click Open Scalping Engine Workspace button
  await mobilePage.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const btn = buttons.find(b => b.textContent && b.textContent.includes('Scalping Engine Workspace'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 3000));

  await mobilePage.waitForSelector('#live-opportunity-qualification-meter-section', { timeout: 10000 });
  console.log('FOUND: #live-opportunity-qualification-meter-section on Mobile');

  // Scroll to Qualification Meter on mobile
  await mobilePage.evaluate(() => {
    const el = document.getElementById('live-opportunity-qualification-meter-section');
    if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' });
  });
  await new Promise(r => setTimeout(r, 1500));

  // Capture Mobile 1: Collapsed State
  await mobilePage.screenshot({ path: '/tmp/qualification_meter_mobile_collapsed.png' });
  console.log('CAPTURED: /tmp/qualification_meter_mobile_collapsed.png');

  // Click toggle on mobile
  await mobilePage.evaluate(() => {
    const btn = document.getElementById('btn-toggle-qualification-details');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  // Scroll to show expanded gates on mobile
  await mobilePage.evaluate(() => {
    const el = document.getElementById('why-hasnt-trade-executed-callout') || document.getElementById('qualification-details-expanded-container');
    if (el) el.scrollIntoView({ behavior: 'instant', block: 'start' });
  });
  await new Promise(r => setTimeout(r, 1500));

  // Capture Mobile 2: Expanded State
  await mobilePage.screenshot({ path: '/tmp/qualification_meter_mobile_expanded.png' });
  console.log('CAPTURED: /tmp/qualification_meter_mobile_expanded.png');

  await browser.close();
  console.log('ALL_QUALIFICATION_SCREENSHOTS_CAPTURED_SUCCESSFULLY');
}

run().catch(err => {
  console.error('CAPTURE_ERROR', err);
  process.exit(1);
});
