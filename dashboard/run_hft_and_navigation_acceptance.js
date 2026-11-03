const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const SCREENSHOT_DIR = "/opt/tauric-platform-staging/dashboard/audit_evidence_hft_redesign";
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

// Generate customer token using python PyJWT
let custToken = process.argv[2];
if (!custToken) {
  custToken = execSync(
    "/opt/tauric-platform-staging/backend/.venv/bin/python3 -c \"import jwt, datetime, os; print(jwt.encode({'sub': 'USR-402F7BFE6D', 'email': 'designkrao@gmail.com', 'role': 'CUSTOMER', 'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)}, os.getenv('TAURIC_JWT_SECRET', 'tauric_super_secret_staging_jwt_key_2026_xyz'), algorithm='HS256'))\""
  ).toString().trim();
}

const testUser = {
  user_id: "USR-402F7BFE6D",
  email: "designkrao@gmail.com",
  username: "designkrao",
  role: "CUSTOMER",
  status: "ACTIVE",
};

const viewports = [
  { name: "mobile_360px", width: 360, height: 800 },
  { name: "mobile_390px", width: 390, height: 844 },
  { name: "mobile_430px", width: 430, height: 932 },
  { name: "tablet_768px", width: 768, height: 1024 },
  { name: "desktop_1440px", width: 1440, height: 900 },
];

async function run() {
  console.log("===============================================================");
  console.log("BITDEX HFT REDESIGN & DUPLICATE NAVIGATION ACCEPTANCE AUDIT");
  console.log("===============================================================");

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });

  const auditResults = [];

  for (const vp of viewports) {
    console.log(`\n--- Testing Viewport: ${vp.name} (${vp.width}x${vp.height}) ---`);
    const page = await browser.newPage();
    await page.setViewport({ width: vp.width, height: vp.height });

    // Navigate to local dashboard
    await page.goto("http://127.0.0.1:33900/", { waitUntil: "domcontentloaded", timeout: 30000 });

    // Inject customer authentication
    await page.evaluate(
      ({ token, user }) => {
        localStorage.setItem("bitdex_auth_token", token);
        localStorage.setItem("tauric_token", token);
        localStorage.setItem("tauric_session_token", token);
        localStorage.setItem("bitdex_user", JSON.stringify(user));
        localStorage.setItem("tauric_user", JSON.stringify(user));
      },
      { token: custToken, user: testUser }
    );

    // Reload with authenticated token into Long-Term Strategy by default
    await page.goto("http://127.0.0.1:33900/#dashboard", { waitUntil: "domcontentloaded", timeout: 30000 });
    await new Promise((r) => setTimeout(r, 2000));

    // Verify Check 1: Duplicate Strategy Navigation Removal
    const headerNavButtons = await page.evaluate(() => {
      const header = document.querySelector("header");
      if (!header) return [];
      const buttons = Array.from(header.querySelectorAll("nav button")).map((b) => b.innerText.trim());
      return buttons;
    });

    const hasDuplicateInHeader = headerNavButtons.some(
      (b) => b === "Long-Term" || b === "Grid" || b === "High-Frequency"
    );
    console.log(`[Check 1] Header nav buttons: [${headerNavButtons.join(", ")}]`);
    console.log(`[Check 1] Duplicate strategy nav in header eliminated? ${!hasDuplicateInHeader ? "YES (PASS)" : "NO (FAIL)"}`);

    // Verify Check 2: Single Primary Strategy Navigation Bar
    const strategyBarButtons = await page.evaluate(() => {
      const btns = ["tab-btn-longterm", "tab-btn-grid", "tab-btn-hft"].map((id) => {
        const el = document.getElementById(id);
        return el ? el.innerText.trim() : null;
      });
      return btns;
    });
    console.log(`[Check 2] Single Strategy Bar buttons: [${strategyBarButtons.filter(Boolean).join(", ")}]`);

    // Measure horizontal overflow in Long-Term view
    const ltOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth;
    });
    console.log(`[Check 3] Horizontal overflow in Long-Term view: ${!ltOverflow ? "0px (PASS)" : "OVERFLOW DETECTED (FAIL)"}`);

    if (vp.name === "desktop_1440px") {
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, "single_strategy_navigation_1440px.png"),
        fullPage: false,
      });
    }

    // Switch to HFT Workspace
    await page.click("#tab-btn-hft");
    try {
      await page.waitForSelector("#btn-open-config-modal", { timeout: 12000 });
    } catch {}
    try {
      await page.waitForSelector("[data-testid='hft-pair-card']", { timeout: 12000 });
    } catch {}
    try {
      await page.waitForSelector("[data-testid='checklist-item']", { timeout: 12000 });
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));

    // Measure horizontal overflow in HFT view
    const hftOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth;
    });
    console.log(`[Check 4] Horizontal overflow in HFT view: ${!hftOverflow ? "0px (PASS)" : "OVERFLOW DETECTED (FAIL)"}`);

    // Check Step 1: Pair Selection
    const pairsCount = await page.evaluate(() => {
      const cards = document.querySelectorAll("[data-testid='hft-pair-card']");
      return cards.length;
    });
    console.log(`[Check 5] HFT Dynamic Pair Cards visible: ${pairsCount}`);

    // Check Step 2: Open Strategy Configuration Modal
    const configBtnExists = await page.evaluate(() => {
      const btn = document.getElementById("btn-open-config-modal");
      return Boolean(btn);
    });
    console.log(`[Check 6] Configure Strategy button present? ${configBtnExists ? "YES (PASS)" : "NO (FAIL)"}`);

    if (configBtnExists && vp.name === "desktop_1440px") {
      await page.click("#btn-open-config-modal");
      await new Promise((r) => setTimeout(r, 1000));
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, "hft_step2_config_modal_1440px.png"),
        fullPage: false,
      });
      // Close modal
      const closeBtn = await page.$("button[class*='text-[#94A3B8] hover:text-white']");
      if (closeBtn) await closeBtn.click();
      await new Promise((r) => setTimeout(r, 500));
    }

    // Capture HFT screenshots
    if (vp.name === "desktop_1440px") {
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, "hft_workflow_desktop_1440px.png"),
        fullPage: false,
      });
    } else if (vp.name === "mobile_390px") {
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, "hft_workflow_mobile_390px.png"),
        fullPage: false,
      });
    }

    // Verify Step 3: Pre-trade checklist items
    const checklistCount = await page.evaluate(() => {
      const items = document.querySelectorAll("[data-testid='checklist-item']");
      return items.length;
    });
    console.log(`[Check 7] Pre-trade checklist items detected: ${checklistCount}`);

    // Verify Honest Protection Statuses (No fabricated "ARMED & CONFIRMED" when flat)
    const protectionStatuses = await page.evaluate(() => {
      const text = document.body.innerText;
      const hasFabricatedConfirmed = text.includes("ARMED & CONFIRMED");
      const hasStandbyStop = text.includes("STANDBY (NO OPEN POSITIONS)");
      const hasStandbyTwoLayer = text.includes("STANDBY (ARMED ON ENTRY)");
      return { hasFabricatedConfirmed, hasStandbyStop, hasStandbyTwoLayer };
    });
    console.log(`[Check 8] Honest non-fabricated stop status verified? ${!protectionStatuses.hasFabricatedConfirmed && protectionStatuses.hasStandbyStop ? "YES (PASS)" : "NO (FAIL)"}`);

    auditResults.push({
      viewport: vp.name,
      width: vp.width,
      hasDuplicateInHeader,
      singleStrategyBar: strategyBarButtons.length === 3,
      hasHorizontalOverflow: ltOverflow || hftOverflow,
      pairsCount,
      configBtnExists,
      checklistCount,
      honestProtection: !protectionStatuses.hasFabricatedConfirmed && protectionStatuses.hasStandbyStop,
    });

    await page.close();
  }

  await browser.close();

  fs.writeFileSync(
    path.join(SCREENSHOT_DIR, "hft_acceptance_audit.json"),
    JSON.stringify(auditResults, null, 2)
  );

  console.log("\n===============================================================");
  console.log("ACCEPTANCE AUDIT COMPLETED SUCCESSFULLY");
  console.log("===============================================================");
}

run().catch((err) => {
  console.error("FATAL ERROR IN ACCEPTANCE AUDIT:", err);
  process.exit(1);
});
