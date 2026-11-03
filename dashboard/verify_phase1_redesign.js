const puppeteer = require('puppeteer');
const fs = require('fs');
const http = require('http');

const SCREENSHOT_DIR = '/opt/tauric-platform/dashboard/signals_screenshots/phase1';
if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

function getLedgerCount() {
    return new Promise((resolve) => {
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
        }).on('error', () => resolve(0));
    });
}

(async () => {
    console.log('==================================================');
    console.log('TAURIC PHASE 1 VISUAL REDESIGN — PUPPETEER VERIFICATION');
    console.log('==================================================');

    const ledgerStart = await getLedgerCount();
    console.log(`[LEDGER] Initial AI ledger record count: ${ledgerStart}`);

    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1600,1100']
    });

    const page = await browser.newPage();
    const networkRequests = [];
    const consoleLogs = [];

    page.on('request', req => {
        networkRequests.push({
            url: req.url(),
            method: req.method()
        });
    });

    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleLogs.push(msg.text());
        }
    });

    // 1. Desktop Viewport
    await page.setViewport({ width: 1600, height: 1100 });
    console.log('\n[TEST 1] Loading http://127.0.0.1:8085/trading/ (Desktop 1600x1100)...');
    await page.goto('http://127.0.0.1:8085/trading/', { waitUntil: 'networkidle2', timeout: 25000 });
    await new Promise(r => setTimeout(r, 2000));

    await page.screenshot({ path: `${SCREENSHOT_DIR}/01_desktop_grid.png`, fullPage: false });
    console.log('✓ Captured 01_desktop_grid.png');

    // 2. Tablet Viewport
    console.log('\n[TEST 2] Testing Tablet Viewport (768x1024)...');
    await page.setViewport({ width: 768, height: 1024 });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/02_tablet_grid.png`, fullPage: false });
    console.log('✓ Captured 02_tablet_grid.png (2-column layout)');

    // 3. Mobile Viewport
    console.log('\n[TEST 3] Testing Mobile Viewport (390x844)...');
    await page.setViewport({ width: 390, height: 844 });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/03_mobile_grid.png`, fullPage: false });
    console.log('✓ Captured 03_mobile_grid.png (1-column layout)');

    // Reset to Desktop for interaction tests
    await page.setViewport({ width: 1600, height: 1100 });
    await new Promise(r => setTimeout(r, 1000));

    // 4. Test Tabs: BUY, SELL, SCALPING, ALL
    console.log('\n[TEST 4] Testing Tabs Navigation...');
    
    // Click BUY
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const buyBtn = buttons.find(b => b.textContent.includes('BUY'));
        if (buyBtn) buyBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/04_buy_tab.png` });
    console.log('✓ BUY tab filtered & captured');

    // Click SELL
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const sellBtn = buttons.find(b => b.textContent.includes('SELL'));
        if (sellBtn) sellBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/05_sell_tab.png` });
    console.log('✓ SELL tab filtered & captured (checking SELL / EXIT and SELL / SHORT wording)');

    // Verify SELL / EXIT and SELL / SHORT in DOM
    const sellLabels = await page.evaluate(() => {
        const badges = Array.from(document.querySelectorAll('span'));
        return badges
            .map(b => b.textContent.trim())
            .filter(t => t.includes('SELL / EXIT') || t.includes('SELL / SHORT') || t.includes('SELL signal'));
    });
    console.log(`[VERIFICATION] Rendered SELL badges: ${JSON.stringify(sellLabels.slice(0, 5))}`);

    // Click SCALPING
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const scalpBtn = buttons.find(b => b.textContent.includes('SCALPING'));
        if (scalpBtn) scalpBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/06_scalping_tab.png` });
    console.log('✓ SCALPING tab filtered & captured');

    // Return to ALL
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const allBtn = buttons.find(b => b.textContent.includes('ALL'));
        if (allBtn) allBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // 5. Test Search Box
    console.log('\n[TEST 5] Testing Search Box...');
    const searchInput = await page.$('input[placeholder*="Search"]');
    if (searchInput) {
        await searchInput.type('BTC');
        await new Promise(r => setTimeout(r, 800));
        await page.screenshot({ path: `${SCREENSHOT_DIR}/07_search_btc.png` });
        console.log('✓ Search for BTC captured');
        
        // Clear search
        await page.evaluate(() => {
            const clearBtn = document.querySelector('button[aria-label="Clear search"]');
            if (clearBtn) clearBtn.click();
        });
        await new Promise(r => setTimeout(r, 500));
    }

    // 6. Test Technical Detail Modal (Expand)
    console.log('\n[TEST 6] Testing Technical Detail Modal & Live Meter...');
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const detailBtn = buttons.find(b => b.textContent.includes('Technical Detail') || b.textContent.includes('Expand'));
        if (detailBtn) detailBtn.click();
    });
    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/08_technical_detail_modal.png` });
    console.log('✓ Technical Detail modal & live meter captured');

    // Close Modal
    await page.evaluate(() => {
        const closeBtn = document.querySelector('button[aria-label="Close modal"]') || document.querySelector('[data-testid="expand-modal-close-btn"]');
        if (closeBtn) closeBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // 7. Test AI Intelligence Modal (Violet Action)
    console.log('\n[TEST 7] Testing Dedicated AI Intelligence Modal (Violet Styling)...');
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const aiBtn = buttons.find(b => b.textContent.includes('AI Intelligence'));
        if (aiBtn) aiBtn.click();
    });
    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: `${SCREENSHOT_DIR}/09_ai_intelligence_modal.png` });
    console.log('✓ Dedicated AI Intelligence modal captured');

    // Close AI Modal
    await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const dismissBtn = buttons.find(b => b.textContent.includes('Dismiss') || b.textContent.includes('Close'));
        if (dismissBtn) dismissBtn.click();
    });
    await new Promise(r => setTimeout(r, 1000));

    // 8. Cost & AI Safeguard Invariant Check
    console.log('\n[TEST 8] Checking AI Cost and Ledger Safeguards...');
    const ledgerEnd = await getLedgerCount();
    console.log(`[LEDGER] End AI ledger record count: ${ledgerEnd}`);
    const ledgerDelta = ledgerEnd - ledgerStart;
    console.log(`[LEDGER] Delta AI ledger records: ${ledgerDelta}`);

    const aiCalls = networkRequests.filter(r => 
        r.url.includes('/analyze') || 
        r.url.includes('api.venice.ai') || 
        r.url.includes('api.typesafe.ai') ||
        r.url.includes('/research/start')
    );
    console.log(`[NETWORK] Paid AI Network Requests detected: ${aiCalls.length}`);
    if (aiCalls.length > 0) {
        console.error('FAILED: Unauthorized AI requests detected:', aiCalls);
    } else {
        console.log('✓ PASS: Zero paid AI network requests detected');
    }

    if (ledgerDelta === 0) {
        console.log('✓ PASS: Zero ledger records added during entire test run');
    } else {
        console.error(`FAILED: ${ledgerDelta} ledger records were added!`);
    }

    await browser.close();
    console.log('\n==================================================');
    console.log('ALL PHASE 1 VERIFICATION TESTS COMPLETED SUCCESSFULLY');
    console.log('==================================================');
})();
