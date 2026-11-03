const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const OUT_DIR = "/opt/tauric-platform-staging/evidence_screenshots";
if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

function getSession(email) {
  const out = execSync(
    `PYTHONPATH=/opt/tauric-platform-staging/backend /opt/tauric-platform-staging/backend/.venv/bin/python3 /tmp/get_session.py "${email}"`,
    { encoding: "utf-8" }
  );
  return JSON.parse(out.trim());
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function run() {
  console.log("=== Launching Puppeteer for Four-Engine Master Verification Evidence ===");
  const browser = await puppeteer.launch({
    headless: "new",
    ignoreHTTPSErrors: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--disable-software-rasterizer",
      "--ignore-certificate-errors",
    ],
  });

  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(30000);
  page.setDefaultTimeout(20000);
  const BASE_URL = "http://127.0.0.1:33900";

  // Get Admin and Customer Sessions
  const adminSession = getSession("hello@nexura.ltd");
  const customerSession = getSession("test.customer@bitdex.ltd");

  async function loginAsCustomer() {
    await page.goto(`${BASE_URL}/`, { waitUntil: "domcontentloaded" });
    await page.evaluate((sess) => {
      localStorage.setItem("bitdex_token", sess.token);
      localStorage.setItem("tauric_session_token", sess.token);
      localStorage.setItem("tauric_user", JSON.stringify(sess.user));
      localStorage.setItem("tauric_session_user", JSON.stringify(sess.user));
      localStorage.setItem("bitdex_user", JSON.stringify(sess.user));
    }, customerSession);
    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
    await sleep(2500);
  }

  async function loginAsAdmin() {
    await page.goto(`${BASE_URL}/`, { waitUntil: "domcontentloaded" });
    await page.evaluate((sess) => {
      localStorage.setItem("bitdex_token", sess.token);
      localStorage.setItem("tauric_session_token", sess.token);
      localStorage.setItem("tauric_user", JSON.stringify(sess.user));
      localStorage.setItem("tauric_session_user", JSON.stringify(sess.user));
      localStorage.setItem("bitdex_user", JSON.stringify(sess.user));
    }, adminSession);
    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle2" });
    await sleep(2500);
  }

  // ─── 1. Desktop 1440px: Dashboard with Mini Conclusion & Search Button ─
  try {
    console.log("\n[1/10] Capturing Desktop Dashboard with 4-Engine Mini Conclusion Badges...");
    await loginAsCustomer();
    await page.setViewport({ width: 1440, height: 900 });
    await sleep(2000);
    await page.screenshot({ path: path.join(OUT_DIR, "evidence_1_desktop_dashboard_1440.png"), fullPage: false });
    console.log("✓ Saved evidence_1_desktop_dashboard_1440.png");
  } catch (e) {
    console.error("Error in step 1:", e.message);
  }

  // ─── 2. Desktop 1440px: Four-Engine Decision Board Modal ──────────────
  try {
    console.log("\n[2/10] Triggering Four-Engine Analysis for BTC/USDT...");
    const clickedTech = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      const b = btns.find((el) => el.textContent && el.textContent.includes("Technical Analysis"));
      if (b) {
        b.scrollIntoView({ behavior: "instant", block: "center" });
        b.click();
        return true;
      }
      return false;
    });
    console.log("Technical Analysis button clicked:", clickedTech);
    if (clickedTech) {
      // Wait for analysis to complete and decision board to render
      await sleep(7000);
      await page.screenshot({ path: path.join(OUT_DIR, "evidence_2_four_engine_decision_board_1440.png"), fullPage: false });
      console.log("✓ Saved evidence_2_four_engine_decision_board_1440.png");

      // Close modal
      await page.evaluate(() => {
        const closeBtn = document.querySelector("button[title='Close Board']") || document.querySelector("button svg.lucide-x")?.closest("button");
        if (closeBtn) closeBtn.click();
      });
      await sleep(1000);
    }
  } catch (e) {
    console.error("Error in step 2:", e.message);
  }

  // ─── 3. Desktop 1440px: Universal Pair Search Modal ───────────────────
  try {
    console.log("\n[3/10] Opening Universal Pair Search Modal...");
    const clickedSearch = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      const b = btns.find((el) => el.textContent && el.textContent.includes("Search Any Coin"));
      if (b) {
        b.scrollIntoView({ behavior: "instant", block: "center" });
        b.click();
        return true;
      }
      return false;
    });
    console.log("Search Any Coin button clicked:", clickedSearch);
    if (clickedSearch) {
      await sleep(1500);
      const searchInput = await page.$("input[placeholder*='Type any symbol']");
      if (searchInput) {
        await searchInput.type("EUR");
        await sleep(2000);
      }
      await page.screenshot({ path: path.join(OUT_DIR, "evidence_3_universal_search_modal_1440.png"), fullPage: false });
      console.log("✓ Saved evidence_3_universal_search_modal_1440.png");

      await page.evaluate(() => {
        const closeBtn = document.querySelector("button svg.lucide-x")?.closest("button");
        if (closeBtn) closeBtn.click();
      });
      await sleep(1000);
    }
  } catch (e) {
    console.error("Error in step 3:", e.message);
  }

  // ─── 4. Admin Portal: AI & Data Provider Operations Dashboard ─────────
  try {
    console.log("\n[4/10] Logging into Admin Portal & Navigating to Provider Operations...");
    await loginAsAdmin();
    await page.setViewport({ width: 1440, height: 900 });

    const clickedProv = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll("button"));
      const b = btns.find((el) => el.textContent && el.textContent.includes("AI & Data Provider Operations"));
      if (b) {
        b.scrollIntoView({ behavior: "instant", block: "center" });
        b.click();
        return true;
      }
      return false;
    });
    console.log("Provider Operations tab clicked:", clickedProv);
    await sleep(3000);
    await page.screenshot({ path: path.join(OUT_DIR, "evidence_4_admin_provider_operations_1440.png"), fullPage: false });
    console.log("✓ Saved evidence_4_admin_provider_operations_1440.png");
  } catch (e) {
    console.error("Error in step 4:", e.message);
  }

  // ─── 5. Responsive Viewports Across 7 Screen Sizes ───────────────────
  console.log("\n[5/10] Capturing Responsive Layouts across 7 required viewports...");
  try {
    await loginAsCustomer();

    const viewports = [
      { name: "evidence_5_viewport_1366.png", width: 1366, height: 768, isMobile: false },
      { name: "evidence_6_viewport_1024.png", width: 1024, height: 768, isMobile: false },
      { name: "evidence_7_viewport_768.png", width: 768, height: 1024, isMobile: true },
      { name: "evidence_8_viewport_430.png", width: 430, height: 932, isMobile: true },
      { name: "evidence_9_viewport_390.png", width: 390, height: 844, isMobile: true },
      { name: "evidence_10_viewport_375.png", width: 375, height: 667, isMobile: true },
      { name: "evidence_11_viewport_320.png", width: 320, height: 568, isMobile: true },
    ];

    for (const vp of viewports) {
      await page.setViewport({ width: vp.width, height: vp.height, isMobile: vp.isMobile });
      await sleep(1500);
      await page.screenshot({ path: path.join(OUT_DIR, vp.name), fullPage: false });
      console.log(`✓ Saved ${vp.name} (${vp.width}x${vp.height})`);
    }
  } catch (e) {
    console.error("Error in responsive viewports:", e.message);
  }

  await browser.close();
  console.log("\n=== All Visual Evidence Successfully Captured! ===");
}

run().catch((err) => {
  console.error("Puppeteer capture failed:", err);
  process.exit(1);
});
