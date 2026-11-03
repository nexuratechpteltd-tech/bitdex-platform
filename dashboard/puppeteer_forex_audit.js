const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const SCREENSHOT_DIR = '/opt/tauric-platform/dashboard/forex_screenshots';
if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

(async () => {
    console.log('[Puppeteer] Launching headless browser...');
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1600,1100']
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 1100 });

    const requests = [];
    page.on('request', req => {
        if (req.url().includes('/api/')) {
            requests.push({ method: req.method(), url: req.url(), postData: req.postData() });
        }
    });

    page.on('console', msg => console.log('[Browser Console]', msg.text()));

    console.log('[Puppeteer] Navigating to http://127.0.0.1:8080/trading/ ...');
    await page.goto('http://127.0.0.1:8080/trading/', { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(2000);

    // 1. Initial Mount: Top Market Tabs & Crypto Workspace
    console.log('[Puppeteer] Step 1: Capturing Initial Mount (Crypto Workspace)');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01_market_tabs_crypto_forex.png') });

    // 2. Open Crypto Tauric Deep Research Dropdown
    console.log('[Puppeteer] Step 2: Navigating to Tauric Deep Research tab in Crypto');
    await page.click('button[data-testid="strategy-tab-tauric-deep-research"]');
    await sleep(1000);

    console.log('[Puppeteer] Opening Crypto Pair Selector dropdown...');
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02_crypto_dropdown_open.png') });

    // Close dropdown
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(500);

    // 3. Switch to FOREX Workspace
    console.log('[Puppeteer] Step 3: Switching to [ FOREX ] Top Market Tab');
    await page.click('button[data-testid="market-tab-forex"]');
    await sleep(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03_forex_tab_and_session.png') });

    // 4. Open Forex Pair Selector Dropdown (Categorized: Major FX, Minor FX, Precious Metals)
    console.log('[Puppeteer] Step 4: Opening Forex Pair Selector Dropdown');
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04_forex_dropdown_open.png') });

    // Close dropdown
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(500);

    // 5. Navigate to Scalping Tab in Forex & Find Opportunities
    console.log('[Puppeteer] Step 5: Testing Scalping (10m) in Forex Workspace');
    await page.click('button[data-testid="strategy-tab-scalping"]');
    await sleep(1000);

    // Click "Find Opportunities" button
    console.log('[Puppeteer] Clicking "Find Forex Opportunities"...');
    await page.click('button[data-testid="find-opportunities-btn"]');
    
    // Wait for scan results
    await sleep(4500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05_forex_scalping_candidates.png') });

    // 6. Select a candidate card to generate Forex Execution Plan
    console.log('[Puppeteer] Step 6: Selecting candidate card for Forex Execution Plan');
    const firstCard = await page.$('div[data-testid^="candidate-card-"]');
    if (firstCard) {
        await firstCard.click();
    }
    await sleep(5000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06_forex_scalping_plan_10m.png') });

    // 7. Test Precious Metals (XAU/USD Gold Setup)
    console.log('[Puppeteer] Step 7: Testing Trade Setup for XAU/USD (Gold)');
    await page.click('button[data-testid="strategy-tab-trade-setup"]');
    await sleep(1000);

    // Click "Find Opportunities" in Trade Setup
    await page.click('button[data-testid="find-opportunities-btn"]');
    await sleep(4500);

    // Select XAU/USD or first candidate
    const goldCard = await page.$('div[data-testid="candidate-card-XAU_USD"]');
    if (goldCard) {
        await goldCard.click();
    } else {
        const anyCard = await page.$('div[data-testid^="candidate-card-"]');
        if (anyCard) await anyCard.click();
    }
    await sleep(5000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07_forex_gold_trade_setup.png') });

    // 8. Test Tauric Deep Research Idle Protection in Forex
    console.log('[Puppeteer] Step 8: Verifying Tauric Deep Research Idle State in Forex');
    await page.click('button[data-testid="strategy-tab-tauric-deep-research"]');
    await sleep(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08_tauric_deep_research_idle.png') });

    // 9. History Table and Market Filtering
    console.log('[Puppeteer] Step 9: Verifying History Table');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(1000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09_unified_history_market_filter.png') });

    console.log('[Puppeteer] All steps completed successfully.');
    console.log('[Puppeteer] Total API Requests Captured:', requests.length);
    console.log('[Puppeteer] POST Requests:', requests.filter(r => r.method === 'POST').map(r => ({ url: r.url(), data: r.postData })));

    await browser.close();
})();
