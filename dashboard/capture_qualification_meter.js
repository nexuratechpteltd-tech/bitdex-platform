const puppeteer = require('puppeteer');
const { execSync } = require('child_process');

let TOKEN = process.env.BITDEX_TEST_TOKEN || '';
if (!TOKEN) {
  try {
    TOKEN = execSync('/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/backend/scripts/create_ephemeral_test_token.py USR-904424B4FB', { encoding: 'utf-8' }).trim();
  } catch (e) {
    console.warn('Could not auto-generate test token:', e.message);
  }
}

const TEST_USER = process.env.BITDEX_TEST_USER ? JSON.parse(process.env.BITDEX_TEST_USER) : {
  user_id: process.env.BITDEX_TEST_USER_ID || 'USR-904424B4FB',
  email: process.env.BITDEX_TEST_EMAIL || 'test_trader@bitdex.io',
  username: 'test_trader',
  role: 'CUSTOMER',
  status: 'ACTIVE',
  first_name: 'Test',
  last_name: 'Trader',
  country: 'AU'
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
  }, TOKEN, TEST_USER);

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
  }, TOKEN, TEST_USER);

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
