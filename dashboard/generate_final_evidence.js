const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = '/opt/tauric-platform-staging/dashboard/admin_restoration_evidence';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const ADMIN_TOKEN = process.env.BITDEX_ADMIN_TOKEN || "";
const ADMIN_USER = {
  user_id: "USR-66BCFD7350",
  email: "admin@tauric.com",
  username: "admin",
  role: "ADMIN",
  status: "ACTIVE",
  first_name: "Admin",
  last_name: "",
  country: "SG",
  email_verified: true,
  two_factor_enabled: true,
  must_change_password: false,
  kyc_status: "VERIFIED"
};

const VIEWPORTS = [
  { name: 'evidence_admin_restoration_1440', width: 1440, height: 900 },
  { name: 'evidence_admin_restoration_1366', width: 1366, height: 768 },
  { name: 'evidence_admin_restoration_1024', width: 1024, height: 768 },
  { name: 'evidence_admin_restoration_768', width: 768, height: 1024 },
  { name: 'evidence_admin_restoration_430', width: 430, height: 932 },
  { name: 'evidence_admin_restoration_390', width: 390, height: 844 },
  { name: 'evidence_admin_restoration_375', width: 375, height: 667 },
  { name: 'evidence_admin_restoration_320', width: 320, height: 568 },
];

async function run() {
  console.log('Launching browser for final evidence capture...');
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium-browser',
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--window-size=1440,900'
    ]
  });

  try {
    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(45000);

    console.log('1. Setting Admin credentials in localStorage...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'domcontentloaded' });
    await page.evaluate((token, user) => {
      localStorage.setItem('tauric_session_token', token);
      localStorage.setItem('tauric_session_user', JSON.stringify(user));
    }, ADMIN_TOKEN, ADMIN_USER);

    console.log('2. Loading Admin Console...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 2000));

    console.log('3. Switching to "AI & Data Provider Operations" tab...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const b = btns.find(x => x.innerText.trim() === 'AI & Data Provider Operations');
      if (b) b.click();
    });

    // Wait for provider operations to load live data (5s)
    await new Promise(r => setTimeout(r, 5000));

    // Verify DOM contains all required entities
    const check = await page.evaluate(() => {
      const t = document.body.innerText;
      return {
        binanceLive: t.includes('CONN-DK-BIN-LIVE'),
        bitgetDemo: t.includes('CONN-DK-BIT-DEMO'),
        maskedEmail: t.includes('des***@gmail.com'),
        coldVault: t.includes('WLT-VAULT-ETH-01'),
        liveBalanceUsd: t.includes('14.37')
      };
    });
    console.log('DOM Entities Verification:', JSON.stringify(check, null, 2));

    // Capture screenshots for all 8 viewports of the restored Provider Operations view
    console.log('4. Capturing 8 viewports of restored Admin Panel...');
    for (const vp of VIEWPORTS) {
      console.log(`Capturing ${vp.name} (${vp.width}x${vp.height})...`);
      await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1 });
      await new Promise(r => setTimeout(r, 800));
      const shotPath = path.join(OUTPUT_DIR, `${vp.name}.png`);
      await page.screenshot({ path: shotPath, fullPage: true });
    }

    // Now switch to Signals Terminal to capture Universal Search
    console.log('5. Switching to Signals Terminal...');
    await page.setViewport({ width: 1440, height: 900 });
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const b = btns.find(x => x.innerText.trim() === 'Signals Terminal');
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 3000));

    console.log('6. Opening Search Any Coin / Pair modal...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const b = btns.find(x => x.innerText.includes('Search Any Coin / Pair'));
      if (b) b.click();
    });
    await new Promise(r => setTimeout(r, 1500));

    console.log('7. Typing "BTC" into search box...');
    await page.evaluate(() => {
      const inp = document.querySelector('input[placeholder*="Type any symbol or pair"]');
      if (inp) {
        inp.value = 'BTC';
        inp.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
    await new Promise(r => setTimeout(r, 2500));

    const searchShotPath = path.join(OUTPUT_DIR, 'evidence_universal_pair_search_btc.png');
    await page.screenshot({ path: searchShotPath });
    console.log(`Saved Universal Search screenshot to ${searchShotPath}`);

    console.log('All evidence captures successfully created!');
  } catch (err) {
    console.error('Evidence capture error:', err);
  } finally {
    await browser.close();
  }
}

run();
