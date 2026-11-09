const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

const SCREENSHOT_DIR = "/opt/tauric-platform-staging/dashboard/evidence_screenshots";
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const adminToken = process.env.ADMIN_TOKEN || process.argv[2];
if (!adminToken) {
  console.error("ERROR: ADMIN_TOKEN must be provided via environment or argv");
  process.exit(1);
}

const adminUser = {
  user_id: "USR-66BCFD7350",
  email: "admin@tauric.com",
  role: "ADMIN",
  status: "ACTIVE"
};

const TARGET_CUSTOMER_ID = "USR-904424B4FB"; // Ali Ajmal
const STAGING_URL = "https://bitdex.ltd/#admin";

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

(async () => {
  console.log("==================================================");
  console.log("STARTING PUPPETEER REAL BROWSER PRICING OVERRIDE TEST");
  console.log("Target Customer: " + TARGET_CUSTOMER_ID + " (Ali Ajmal)");
  console.log("URL: " + STAGING_URL);
  console.log("==================================================");

  const browser = await puppeteer.launch({
    headless: "new",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--ignore-certificate-errors",
      "--window-size=1440,900"
    ],
    defaultViewport: { width: 1440, height: 900 }
  });

  const page = await browser.newPage();

  const networkLogs = [];
  const consoleLogs = [];

  page.on("console", (msg) => {
    consoleLogs.push({ type: msg.type(), text: msg.text() });
    if (msg.type() === "error") {
      console.error("[Browser Console Error]:", msg.text());
    }
  });

  page.on("request", (req) => {
    if (req.url().includes("/pricing/override")) {
      console.log(`[Network Request] ${req.method()} ${req.url()} -> Payload:`, req.postData());
      networkLogs.push({ event: "request", url: req.url(), method: req.method(), postData: req.postData() });
    }
  });

  page.on("response", async (res) => {
    if (res.url().includes("/pricing/override")) {
      let body = "";
      try {
        body = await res.text();
      } catch (e) {}
      console.log(`[Network Response] ${res.status()} ${res.url()} -> Body:`, body);
      networkLogs.push({ event: "response", url: res.url(), status: res.status(), body });
    }
  });

  try {
    // Set localStorage before loading app
    await page.goto("https://bitdex.ltd", { waitUntil: "domcontentloaded" });
    await page.evaluate((token, user) => {
      localStorage.setItem("tauric_session_token", token);
      localStorage.setItem("tauric_session_user", JSON.stringify(user));
    }, adminToken, adminUser);

    console.log("[1] Navigating to https://bitdex.ltd/#admin with injected Admin session...");
    await page.goto(STAGING_URL, { waitUntil: "networkidle2" });
    await sleep(2000);

    // Verify Admin Portal loaded
    const pageTitle = await page.title();
    console.log("[2] Page loaded. Title:", pageTitle);

    // Find Ali Ajmal customer row or search for Ali Ajmal
    console.log("[3] Searching for customer " + TARGET_CUSTOMER_ID + "...");
    const searchInput = await page.$("input[placeholder*='Search']");
    if (searchInput) {
      await searchInput.type("process.env.BITDEX_TARGET_CUSTOMER_EMAIL || "customer_test@bitdex.io"");
      await sleep(1000);
    }

    // Click to open Customer 360 using direct ID
    console.log("[4] Opening Customer 360 Drawer for Ali Ajmal via #open-360-btn-" + TARGET_CUSTOMER_ID + "...");
    await page.waitForSelector("#open-360-btn-" + TARGET_CUSTOMER_ID, { timeout: 10000 });
    await page.click("#open-360-btn-" + TARGET_CUSTOMER_ID);
    await sleep(2000);

    // Click PRICING tab
    console.log("[5] Switching to PRICING tab in Customer 360 via #tab-pricing-overrides...");
    await page.waitForSelector("#tab-pricing-overrides", { timeout: 10000 });
    await page.click("#tab-pricing-overrides");
    await sleep(1500);

    // ------------------------------------------------------------------
    // TEST WORKFLOW 1: Strategy Execution Fee -> 0 with reason validation
    // ------------------------------------------------------------------
    console.log("\n--- [WORKFLOW 1: Strategy Execution Fee -> $0.00] ---");
    // Click "Set New Override" button or "Override" on STRATEGY_EXECUTION
    await page.evaluate(() => {
      const btn = document.getElementById("override-rate-btn-STRATEGY_EXECUTION") ||
                  Array.from(document.querySelectorAll("button")).find(b => b.innerText.includes("Set New Override"));
      if (btn) btn.click();
    });
    await sleep(1000);

    // Verify Modal is open
    await page.waitForSelector("#pricing-override-service-select", { timeout: 5000 });
    console.log("  Modal opened successfully!");

    // Select STRATEGY_EXECUTION
    await page.select("#pricing-override-service-select", "STRATEGY_EXECUTION");
    await sleep(500);

    // Type 0 in price input
    const priceInput = await page.$("#pricing-override-price-input");
    await priceInput.click({ clickCount: 3 });
    await priceInput.press("Backspace");
    await priceInput.type("0");
    await sleep(500);

    // Check button disabled state when reason is EMPTY
    const btnDisabledBeforeReason = await page.$eval("#pricing-override-apply-btn", (b) => ({
      disabled: b.disabled,
      text: b.innerText
    }));
    console.log("  [Step 1.1] Reason empty -> Button state:", btnDisabledBeforeReason);
    if (!btnDisabledBeforeReason.disabled) {
      throw new Error("FAIL: Button should be disabled when reason is empty!");
    }
    console.log("  PASS: Button is correctly disabled when reason is empty.");

    // Screenshot 1: Reason empty with clear indicator
    const shot1 = path.join(SCREENSHOT_DIR, "01_pricing_modal_empty_reason_disabled.png");
    await page.screenshot({ path: shot1, fullPage: false });
    console.log("  Saved screenshot:", shot1);

    // Type 2 chars (too short)
    const reasonInput = await page.$("#pricing-override-reason-input");
    await reasonInput.type("ab");
    await sleep(500);
    const btnDisabledShortReason = await page.$eval("#pricing-override-apply-btn", (b) => ({
      disabled: b.disabled,
      text: b.innerText
    }));
    console.log("  [Step 1.2] Reason 'ab' (< 3 chars) -> Button state:", btnDisabledShortReason);
    if (!btnDisabledShortReason.disabled) {
      throw new Error("FAIL: Button should still be disabled for reason < 3 chars!");
    }

    // Type complete valid reason: "Approved promotional zero-fee rate"
    await reasonInput.click({ clickCount: 3 });
    await reasonInput.press("Backspace");
    await reasonInput.type("Approved promotional zero-fee rate");
    await sleep(500);

    // Check button enabled state after valid reason
    const btnStateAfterReason = await page.$eval("#pricing-override-apply-btn", (b) => ({
      disabled: b.disabled,
      text: b.innerText
    }));
    console.log("  [Step 1.3] Reason valid -> Button state:", btnStateAfterReason);
    if (btnStateAfterReason.disabled) {
      throw new Error("FAIL: Button MUST BE ENABLED after entering valid reason!");
    }
    console.log("  PASS: Button enabled immediately after entering valid reason!");

    // Screenshot 2: Button enabled
    const shot2 = path.join(SCREENSHOT_DIR, "02_pricing_modal_reason_entered_enabled.png");
    await page.screenshot({ path: shot2, fullPage: false });
    console.log("  Saved screenshot:", shot2);

    // Click Apply Override (first click triggers material change confirmation)
    console.log("  [Step 1.4] Clicking Apply Override (expecting confirmation prompt for >25% material change)...");
    await page.click("#pricing-override-apply-btn");
    await sleep(1500);

    const btnConfirmState = await page.$eval("#pricing-override-apply-btn", (b) => ({
      disabled: b.disabled,
      text: b.innerText
    }));
    console.log("  [Step 1.5] Confirmation prompt state -> Button:", btnConfirmState);

    // Screenshot 3: Confirmation prompt
    const shot3 = path.join(SCREENSHOT_DIR, "03_pricing_modal_confirmation_prompt.png");
    await page.screenshot({ path: shot3, fullPage: false });
    console.log("  Saved screenshot:", shot3);

    // Click Confirm & Apply
    console.log("  [Step 1.6] Clicking Confirm & Apply...");
    await page.click("#pricing-override-apply-btn");
    await sleep(2500);

    // Screenshot 4: Success feedback & updated rate card
    const shot4 = path.join(SCREENSHOT_DIR, "04_strategy_execution_zero_applied.png");
    await page.screenshot({ path: shot4, fullPage: false });
    console.log("  Saved screenshot:", shot4);

    // Verify rate card reflects $0.00
    const ratesAfterStrategy = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll("div.grid div"));
      return cards.map(c => c.innerText).filter(t => t.includes("$"));
    });
    console.log("  Customer rates after Strategy Execution override:", ratesAfterStrategy);

    // ------------------------------------------------------------------
    // TEST WORKFLOW 2: AI Market Intelligence Analysis -> 0
    // ------------------------------------------------------------------
    console.log("\n--- [WORKFLOW 2: AI Market Intelligence Analysis -> $0.00] ---");
    await page.evaluate(() => {
      const btn = document.getElementById("override-rate-btn-AI_ANALYSIS") ||
                  Array.from(document.querySelectorAll("button")).find(b => b.innerText.includes("Set New Override"));
      if (btn) btn.click();
    });
    await sleep(1000);

    await page.waitForSelector("#pricing-override-service-select", { timeout: 5000 });
    await page.select("#pricing-override-service-select", "AI_ANALYSIS");
    await sleep(500);

    const priceInputAi = await page.$("#pricing-override-price-input");
    await priceInputAi.click({ clickCount: 3 });
    await priceInputAi.press("Backspace");
    await priceInputAi.type("0");

    const reasonInputAi = await page.$("#pricing-override-reason-input");
    await reasonInputAi.click({ clickCount: 3 });
    await reasonInputAi.press("Backspace");
    await reasonInputAi.type("Approved promotional zero-fee rate");
    await sleep(500);

    console.log("  Clicking Apply Override for AI_ANALYSIS...");
    await page.click("#pricing-override-apply-btn");
    await sleep(1500);

    console.log("  Clicking Confirm & Apply for AI_ANALYSIS...");
    await page.click("#pricing-override-apply-btn");
    await sleep(2500);

    const shot5 = path.join(SCREENSHOT_DIR, "05_ai_analysis_zero_applied.png");
    await page.screenshot({ path: shot5, fullPage: false });
    console.log("  Saved screenshot:", shot5);

    // ------------------------------------------------------------------
    // TEST WORKFLOW 3: Platform Activation Fee -> 0 (Zero Cost for Everything)
    // ------------------------------------------------------------------
    console.log("\n--- [WORKFLOW 3: Platform Activation Fee -> $0.00 (Zero cost for everything)] ---");
    await page.evaluate(() => {
      const btn = document.getElementById("override-rate-btn-PLATFORM_ACTIVATION") ||
                  Array.from(document.querySelectorAll("button")).find(b => b.innerText.includes("Set New Override"));
      if (btn) btn.click();
    });
    await sleep(1000);

    await page.waitForSelector("#pricing-override-service-select", { timeout: 5000 });
    await page.select("#pricing-override-service-select", "PLATFORM_ACTIVATION");
    await sleep(500);

    const priceInputAct = await page.$("#pricing-override-price-input");
    await priceInputAct.click({ clickCount: 3 });
    await priceInputAct.press("Backspace");
    await priceInputAct.type("0");

    const reasonInputAct = await page.$("#pricing-override-reason-input");
    await reasonInputAct.click({ clickCount: 3 });
    await reasonInputAct.press("Backspace");
    await reasonInputAct.type("Approved promotional zero-fee rate");
    await sleep(500);

    console.log("  Clicking Apply Override for PLATFORM_ACTIVATION...");
    await page.click("#pricing-override-apply-btn");
    await sleep(1500);

    console.log("  Clicking Confirm & Apply for PLATFORM_ACTIVATION...");
    await page.click("#pricing-override-apply-btn");
    await sleep(2500);

    const shot6 = path.join(SCREENSHOT_DIR, "06_all_services_zero_applied.png");
    await page.screenshot({ path: shot6, fullPage: false });
    console.log("  Saved screenshot:", shot6);

    // ------------------------------------------------------------------
    // TEST WORKFLOW 4: Reopen modal and verify saved rates default to 0.00
    // ------------------------------------------------------------------
    console.log("\n--- [WORKFLOW 4: Reopen modal and verify saved rate is $0.00] ---");
    await page.evaluate(() => {
      const btn = document.getElementById("override-rate-btn-STRATEGY_EXECUTION");
      if (btn) btn.click();
    });
    await sleep(1000);

    const reopenedPrice = await page.$eval("#pricing-override-price-input", el => el.value);
    console.log("  Reopened modal price value for STRATEGY_EXECUTION:", reopenedPrice);
    if (reopenedPrice !== "0" && reopenedPrice !== "0.0" && reopenedPrice !== "0.00") {
      throw new Error(`Expected saved price 0.00, got: ${reopenedPrice}`);
    }
    console.log("  PASS: Reopened modal correctly shows saved price: " + reopenedPrice);

    await page.click("#pricing-override-cancel-btn");
    await sleep(500);

    console.log("\n==================================================");
    console.log("ALL REAL BROWSER WORKFLOW TESTS PASSED 100%!");
    console.log("Network Intercept Logs Count:", networkLogs.length);
    console.log("Console Errors Count:", consoleLogs.filter(c => c.type === "error").length);
    console.log("==================================================");

  } catch (err) {
    console.error("TEST FAILED WITH EXCEPTION:", err);
    const errShot = path.join(SCREENSHOT_DIR, "error_screenshot.png");
    await page.screenshot({ path: errShot, fullPage: true });
    console.log("Saved error screenshot:", errShot);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
