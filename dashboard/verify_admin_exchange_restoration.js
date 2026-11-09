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

async function run() {
  console.log('🚀 Starting Puppeteer for Admin Exchange Connection Verification...');
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
    page.setDefaultNavigationTimeout(60000);

    // Step 1: Set Admin Token
    console.log('1️⃣ Seeding admin session into localStorage...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'domcontentloaded' });
    await page.evaluate((token, user) => {
      localStorage.setItem('tauric_session_token', token);
      localStorage.setItem('tauric_session_user', JSON.stringify(user));
    }, ADMIN_TOKEN, ADMIN_USER);

    // Step 2: Open Admin Panel (should default directly to PROVIDER_OPERATIONS / API & Exchange Management)
    console.log('2️⃣ Navigating to https://bitdex.ltd as Administrator...');
    await page.goto('https://bitdex.ltd', { waitUntil: 'networkidle0' });

    // Wait for the primary Binance card to appear
    console.log('⏳ Waiting for exchange connections to render...');
    await page.waitForFunction(
      () => document.body.innerText.includes('CONN-DK-BIN-LIVE') && document.body.innerText.includes('14.37'),
      { timeout: 15000 }
    );
    await new Promise(r => setTimeout(r, 2000));

    // Step 3: Verify All 3 Sections and the 4 Primary Exchange Connections
    console.log('3️⃣ Inspecting rendered sections and exchange connections...');
    const verification = await page.evaluate(() => {
      const text = document.body.innerText.toUpperCase();
      return {
        sectionA: text.includes('SECTION A: PROVIDER API MANAGEMENT'),
        sectionB: text.includes('SECTION B: CUSTOMER EXCHANGE CONNECTIONS'),
        sectionC: text.includes('SECTION C: WATCHED WALLETS'),
        binanceLive: text.includes('CONN-DK-BIN-LIVE'),
        binanceDemo: text.includes('CONN-DK-BIN-DEMO'),
        bitgetLive: text.includes('CONN-DK-BIT-LIVE'),
        bitgetDemo: text.includes('CONN-DK-BIT-DEMO'),
        customerEmail: text.includes('DES***@GMAIL.COM'),
        customerUser: text.includes('BILLAL95'),
        binanceBalanceUsdt: text.includes('14.37'),
        bitgetDemoBalanceUsdt: text.includes('2,000.00'),
        readOnlyBadges: text.includes('READ-ONLY LOCKED'),
        totalConnectionsCount: (text.match(/TOTAL:\s*\d+/i) || text.match(/TOTAL CONNECTIONS:\s*\d+/i) || [''])[0]
      };
    });
    console.log('📊 Verification Result:');
    console.log(JSON.stringify(verification, null, 2));

    // Capture Full Page Desktop Screenshot of the restored Admin UI
    console.log('4️⃣ Capturing 1440x900 full page admin screenshot...');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'admin_restored_full_desktop.png'), fullPage: true });

    // Capture Focused Section B Screenshot
    console.log('5️⃣ Capturing focused Section B (Exchange Connections) screenshot...');
    const sectionBElement = await page.$('#section-b-exchanges');
    if (sectionBElement) {
      await sectionBElement.screenshot({ path: path.join(OUTPUT_DIR, 'admin_section_b_exchanges_focused.png') });
    }

    // Step 4: Test Connection button click on CONN-DK-BIN-LIVE
    console.log('6️⃣ Testing click on [Test] button for CONN-DK-BIN-LIVE...');
    const testBtn = await page.$('#btn-test-CONN-DK-BIN-LIVE');
    if (testBtn) {
      await testBtn.click();
      console.log('Test button clicked successfully.');
    } else {
      console.log('⚠️ #btn-test-CONN-DK-BIN-LIVE not found');
    }
    await new Promise(r => setTimeout(r, 4000));

    // Check feedback banner
    const feedbackBannerTest = await page.evaluate(() => {
      const fb = document.querySelector('.animate-fade-in');
      return fb ? fb.innerText : null;
    });
    console.log('Feedback banner after Test click:', feedbackBannerTest);

    // Step 5: Test Refresh Connection button click on CONN-DK-BIN-LIVE
    console.log('7️⃣ Testing click on [Refresh] button for CONN-DK-BIN-LIVE...');
    const refreshBtn = await page.$('#btn-refresh-CONN-DK-BIN-LIVE');
    if (refreshBtn) {
      await refreshBtn.click();
      console.log('Refresh button clicked successfully.');
    } else {
      console.log('⚠️ #btn-refresh-CONN-DK-BIN-LIVE not found');
    }
    await new Promise(r => setTimeout(r, 4000));

    // Check feedback banner
    const feedbackBannerRefresh = await page.evaluate(() => {
      const fb = document.querySelector('.animate-fade-in');
      return fb ? fb.innerText : null;
    });
    console.log('Feedback banner after Refresh click:', feedbackBannerRefresh);

    // Step 6: Test Signals Terminal Tab and Return Banner
    console.log('8️⃣ Switching to Signals Terminal tab to test return banner...');
    const termClicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const btn = buttons.find(b => b.innerText.includes('Signals Terminal'));
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });
    console.log('Signals Terminal tab clicked:', termClicked);
    await new Promise(r => setTimeout(r, 3000));

    // Verify top return banner is visible in Terminal
    const terminalBannerCheck = await page.evaluate(() => {
      const text = document.body.innerText;
      return {
        hasReturnBanner: text.includes('Return to API & Exchange Management'),
        hasBannerButtons: text.includes('Binance / Bitget')
      };
    });
    console.log('Signals Terminal Return Banner check:', terminalBannerCheck);

    // Capture screenshot of Signals Terminal with Return Banner
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'admin_terminal_with_return_banner.png') });

    // Click Return to API & Exchange Management button
    console.log('9️⃣ Clicking Return to API & Exchange Management button...');
    const returnClicked = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const returnBtn = buttons.find(b => b.innerText.includes('Return to API & Exchange Management'));
      if (returnBtn) {
        returnBtn.click();
        return true;
      }
      return false;
    });
    console.log('Return button clicked:', returnClicked);

    // Wait for Section B to reappear
    await page.waitForFunction(
      () => document.body.innerText.includes('CONN-DK-BIN-LIVE'),
      { timeout: 15000 }
    );
    await new Promise(r => setTimeout(r, 2000));

    // Verify returned to Section B
    const returnVerify = await page.evaluate(() => {
      const text = document.body.innerText.toUpperCase();
      return {
        returnedToSectionB: text.includes('SECTION B: CUSTOMER EXCHANGE CONNECTIONS'),
        hasBinanceLive: text.includes('CONN-DK-BIN-LIVE')
      };
    });
    console.log('Returned to API & Exchange Management verification:', returnVerify);

    // Step 7: Mobile Viewport Screenshot (390x844 iPhone 14 / Pro)
    console.log('🔟 Capturing mobile screenshot (390x844)...');
    await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
    // Wait for card element in mobile view
    await page.waitForSelector('#btn-test-CONN-DK-BIN-LIVE', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'admin_restored_mobile_390.png'), fullPage: true });

    console.log('✅ ALL VERIFICATION STEPS AND EVIDENCE SCREENSHOTS COMPLETED SUCCESSFULLY!');
  } catch (err) {
    console.error('❌ Error during verification:', err);
  } finally {
    await browser.close();
  }
}

run();
