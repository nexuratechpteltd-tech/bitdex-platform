const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const SCREENSHOT_DIR = '/opt/tauric-platform/dashboard/forex_screenshots';

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

(async () => {
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--window-size=1600,1200']
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 1200 });

    console.log('[Puppeteer] Navigating to http://127.0.0.1:8080/trading/ ...');
    await page.goto('http://127.0.0.1:8080/trading/', { waitUntil: 'networkidle2' });
    await sleep(1500);

    // Switch to FOREX tab
    console.log('[Puppeteer] Switching to Forex...');
    await page.click('button[data-testid="market-tab-forex"]');
    await sleep(1000);

    // Click Scalping tab
    console.log('[Puppeteer] Clicking Scalping...');
    await page.click('button[data-testid="strategy-tab-scalping"]');
    await sleep(1000);

    // Click Find Forex Opportunities
    console.log('[Puppeteer] Scanning Forex Scalping...');
    await page.click('button[data-testid="find-opportunities-btn"]');
    await sleep(4500);

    // Click on the first candidate card
    console.log('[Puppeteer] Clicking candidate card EUR/USD...');
    const eurCard = await page.$('button[data-testid="candidate-card-EUR_USD"]');
    if (eurCard) {
        await eurCard.click();
    } else {
        const cards = await page.$$('button[data-testid^="candidate-card-"]');
        if (cards.length > 0) await cards[0].click();
    }
    
    // Wait for analysis to complete and render
    await sleep(5000);

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06_forex_scalping_plan_10m.png'), fullPage: true });
    console.log('[Puppeteer] Captured 06_forex_scalping_plan_10m.png (fullPage)');

    await browser.close();
})();
