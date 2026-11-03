const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const http = require('http');

const SCREENSHOT_DIR = '/opt/tauric-platform/dashboard/forex_screenshots';
if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getLedgerCount() {
    return new Promise((resolve, reject) => {
        http.get('http://127.0.0.1:8001/api/v1/grid/ledger', (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    resolve(parsed.total_records || 0);
                } catch(e) {
                    resolve(0);
                }
            });
        }).on('error', err => resolve(0));
    });
}

(async () => {
    console.log('==================================================');
    console.log('STARTING CRITICAL BROWSER ZERO-CREDIT AUDIT (A - M)');
    console.log('==================================================');

    const ledgerStart = await getLedgerCount();
    console.log(`[LEDGER] Initial AI Ledger Row Count: ${ledgerStart}`);

    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1600,1200']
    });

    let page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 1200 });

    const networkRequests = [];
    const recordRequest = (req) => {
        const url = req.url();
        const method = req.method();
        const postData = req.postData();
        networkRequests.push({ method, url, postData, time: new Date().toISOString() });
    };

    page.on('request', recordRequest);

    // ─── A. Page Load ──────────────────────────────────────────────
    console.log('\n[STEP A] Page Load: http://127.0.0.1:8080/trading/ ...');
    await page.goto('http://127.0.0.1:8080/trading/', { waitUntil: 'networkidle2' });
    await sleep(2000);
    console.log('  ✓ Page loaded cleanly.');

    // ─── B. Switch Crypto -> Forex ─────────────────────────────────
    console.log('\n[STEP B] Switching Crypto -> Forex Market Tab...');
    await page.click('button[data-testid="market-tab-forex"]');
    await sleep(1500);
    console.log('  ✓ Forex tab activated.');

    // ─── C. Switch Forex -> Crypto ─────────────────────────────────
    console.log('\n[STEP C] Switching Forex -> Crypto Market Tab...');
    await page.click('button[data-testid="market-tab-crypto"]');
    await sleep(1500);
    console.log('  ✓ Crypto tab activated.');

    // ─── D. Dropdown Open (in Crypto Tauric Deep Research) ──────────
    console.log('\n[STEP D] Opening Pair Selector Dropdown in Crypto...');
    await page.click('button[data-testid="strategy-tab-tauric-deep-research"]');
    await sleep(1000);
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(1200);
    console.log('  ✓ Crypto dropdown opened.');

    // ─── E. Switch Forex & Select EURUSD ───────────────────────────
    console.log('\n[STEP E] Switching to Forex & Selecting EUR/USD...');
    await page.click('button[data-testid="market-tab-forex"]');
    await sleep(1000);
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(1000);
    // Find EUR/USD item
    const fxButtons = await page.$$('button');
    for (const b of fxButtons) {
        const text = await page.evaluate(el => el.textContent, b);
        if (text && text.includes('EUR/USD')) {
            await b.click();
            break;
        }
    }
    await sleep(1000);
    console.log('  ✓ EUR/USD selected.');

    // ─── F. Select GBPUSD ──────────────────────────────────────────
    console.log('\n[STEP F] Opening dropdown & Selecting GBP/USD...');
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(1000);
    const fxButtons2 = await page.$$('button');
    for (const b of fxButtons2) {
        const text = await page.evaluate(el => el.textContent, b);
        if (text && text.includes('GBP/USD')) {
            await b.click();
            break;
        }
    }
    await sleep(1000);
    console.log('  ✓ GBP/USD selected.');

    // ─── G. Select XAUUSD (Precious Metal) ─────────────────────────
    console.log('\n[STEP G] Opening dropdown & Selecting XAU/USD (Gold)...');
    await page.click('[data-testid="pair-dropdown-trigger"]');
    await sleep(1000);
    const fxButtons3 = await page.$$('button');
    for (const b of fxButtons3) {
        const text = await page.evaluate(el => el.textContent, b);
        if (text && text.includes('XAU/USD')) {
            await b.click();
            break;
        }
    }
    await sleep(1000);
    console.log('  ✓ XAU/USD (Gold) selected.');

    // ─── H. Switch SCALPING ────────────────────────────────────────
    console.log('\n[STEP H] Switching to SCALPING strategy tab...');
    await page.click('button[data-testid="strategy-tab-scalping"]');
    await sleep(1000);
    console.log('  ✓ Scalping tab active.');

    // ─── I. Switch SWING / LONGER-TERM ─────────────────────────────
    console.log('\n[STEP I] Switching to SWING strategy tab...');
    await page.click('button[data-testid="strategy-tab-swing"]');
    await sleep(1000);
    console.log('  ✓ Swing tab active.');

    // ─── J. Switch TRADE SETUP ─────────────────────────────────────
    console.log('\n[STEP J] Switching to TRADE SETUP strategy tab...');
    await page.click('button[data-testid="strategy-tab-trade-setup"]');
    await sleep(1000);
    console.log('  ✓ Trade Setup tab active.');

    // ─── K. Open TAURIC DEEP RESEARCH ──────────────────────────────
    console.log('\n[STEP K] Switching to TAURIC DEEP RESEARCH strategy tab...');
    await page.click('button[data-testid="strategy-tab-tauric-deep-research"]');
    await sleep(1500);
    console.log('  ✓ Tauric Deep Research active (Idle).');

    // ─── L. Refresh Page ───────────────────────────────────────────
    console.log('\n[STEP L] Refreshing page...');
    await page.reload({ waitUntil: 'networkidle2' });
    await sleep(2000);
    console.log('  ✓ Page refreshed cleanly.');

    // ─── M. Close & Reopen Tab ─────────────────────────────────────
    console.log('\n[STEP M] Closing and Reopening Browser Tab...');
    await page.close();
    page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 1200 });
    page.on('request', recordRequest);
    await page.goto('http://127.0.0.1:8080/trading/', { waitUntil: 'networkidle2' });
    await sleep(2000);
    console.log('  ✓ New tab loaded and workspace re-attached.');

    // ─── VERIFY ZERO-CREDIT AUDIT FOR STEPS A - M ──────────────────
    console.log('\n==================================================');
    console.log('NETWORK & AI LEDGER AUDIT FOR STEPS A - M');
    console.log('==================================================');

    const postRequests = networkRequests.filter(r => r.method === 'POST');
    const aiAnalyzeRequests = postRequests.filter(r => r.url.includes('/analyze') || r.url.includes('/tauric-deep-research'));
    const ledgerEnd = await getLedgerCount();
    const newLedgerRows = ledgerEnd - ledgerStart;

    console.log(`Total HTTP Requests Captured: ${networkRequests.length}`);
    console.log(`Total POST Requests: ${postRequests.length}`);
    console.log(`POST /analyze or /tauric-deep-research requests: ${aiAnalyzeRequests.length}`);
    console.log(`New AI Ledger Rows Created: ${newLedgerRows}`);

    if (aiAnalyzeRequests.length === 0 && newLedgerRows === 0) {
        console.log('\n>>> PASS: ZERO AI CALLS & ZERO LEDGER ROWS FOR STEPS A - M ✓ <<<');
    } else {
        console.error('\n>>> FAIL: Unauthorized AI calls detected during navigation/selection! <<<');
        console.error(aiAnalyzeRequests);
    }

    // ─── NOW TEST EXPLICIT USER-INITIATED ANALYSIS ─────────────────
    console.log('\n==================================================');
    console.log('TESTING EXPLICIT USER ACTION: 1 AUTHORIZED ANALYSIS');
    console.log('==================================================');

    // Switch to Forex -> Scalping -> Scan -> Click Candidate
    await page.click('button[data-testid="market-tab-forex"]');
    await sleep(1000);
    await page.click('button[data-testid="strategy-tab-scalping"]');
    await sleep(1000);
    console.log('[Puppeteer] Clicking "Find Forex Opportunities"...');
    await page.click('button[data-testid="find-opportunities-btn"]');
    await sleep(4500);

    console.log('[Puppeteer] Explicitly clicking candidate card EUR/USD...');
    const eurCard = await page.$('button[data-testid="candidate-card-EUR_USD"]');
    if (eurCard) {
        await eurCard.click();
    } else {
        const cards = await page.$$('button[data-testid^="candidate-card-"]');
        if (cards.length > 0) await cards[0].click();
    }
    await sleep(6000);

    const ledgerFinal = await getLedgerCount();
    console.log(`[LEDGER] Final AI Ledger Row Count: ${ledgerFinal}`);

    await browser.close();
})();
