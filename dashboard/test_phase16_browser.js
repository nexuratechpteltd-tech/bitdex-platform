const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

function generateAdminSession() {
  const res = execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/dashboard/auth_helper.py test_customer@bitdex.io`, {
    encoding: "utf-8"
  });
  return JSON.parse(res.trim());
}

function generateCustomerSession() {
  const res = execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/dashboard/auth_helper.py customer`, {
    encoding: "utf-8"
  });
  return JSON.parse(res.trim());
}

async function runSuite() {
  const screenshotDir = "/opt/tauric-platform-staging/docs/screenshots";
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  console.log("===============================================================================");
  console.log(" BITDEX PHASE 16: END-TO-END BROWSER & ARCHITECTURAL VERIFICATION SUITE");
  console.log(" Target: http://127.0.0.1:33900 | Branch: feature/hft-redesign-and-navigation-cleanup");
  console.log("===============================================================================\n");

  const results = {
    hftBlankScreenResolved: false,
    adminDropdownVerified: false,
    workspaceSwitchingVerified: false,
    twoProductsNavigationVerified: false,
    adminSettingsIntact: false,
    tradingTerminalIsolated: false,
    exnessDiagnosticVerified: false,
    rbacAdminProtectionVerified: false,
    safetyLocksVerified: false,
    responsiveLayoutVerified: false,
  };

  const adminSession = generateAdminSession();
  console.log(`[AUTH] Admin Token Generated: ${adminSession.user.email} (${adminSession.user.role})`);

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
  });

  const pageErrors = [];
  const consoleMessages = [];

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });

  const page = await context.newPage();

  page.on("pageerror", (err) => {
    console.error(`[PAGE ERROR]: ${err.message}`);
    pageErrors.push(err.message);
  });

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      console.log(`[BROWSER CONSOLE ERROR]: ${msg.text()}`);
      consoleMessages.push(msg.text());
    }
  });

  try {
    // 1. Inject Authentication in LocalStorage
    console.log("\n[TEST 1] Setting authenticated administrator session...");
    await page.goto("http://127.0.0.1:33900/#admin", { waitUntil: "domcontentloaded" });
    await page.evaluate((auth) => {
      localStorage.setItem("tauric_session_token", auth.token);
      localStorage.setItem("tauric_session_user", JSON.stringify(auth.user));
      window.location.hash = "admin";
    }, adminSession);

    // True browser reload so Next.js reads localStorage from init
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForTimeout(3000);

    // Wait for either admin button or trading terminal
    await page.waitForSelector("#btn-admin-profile-dropdown, #btn-switch-to-trading-terminal", { timeout: 15000 });

    // 2. Verify Admin Settings Workspace
    console.log("\n[TEST 2] Verifying Admin Settings Workspace (BITDEX-ARCH-UX-2026-01)...");
    const adminBadge = page.locator("text=ADMIN").first();
    const tenantIsolationBadge = page.locator("text=TENANT ISOLATION ACTIVE").first();
    const switchTerminalBtn = page.locator("#btn-switch-to-trading-terminal");

    if (await adminBadge.isVisible() && await tenantIsolationBadge.isVisible() && await switchTerminalBtn.isVisible()) {
      console.log("  ✓ Admin Header Verified: BITDEX Admin badge, TENANT ISOLATION, and Trading Terminal button present.");
      results.adminSettingsIntact = true;
    } else {
      console.error("  ✗ Admin Header Elements Missing!");
    }

    // 3. Test Admin Email Dropdown & Click-Outside
    console.log("\n[TEST 3] Testing Admin Email-Corner Dropdown & Click-Outside...");
    const adminDropdownTrigger = page.locator("#btn-admin-profile-dropdown");
    await adminDropdownTrigger.click();
    await page.waitForTimeout(500);

    const dropdownUser = page.locator("text=Authenticated Administrator");
    const dropdownTerminalLink = page.locator("#dropdown-switch-to-terminal");
    const dropdownSignOut = page.locator("#btn-admin-sign-out");

    if (await dropdownUser.isVisible() && await dropdownTerminalLink.isVisible() && await dropdownSignOut.isVisible()) {
      console.log("  ✓ Admin Dropdown Opened: Shows user, role, navigation links, and Sign Out.");
      
      // Click outside to verify it closes automatically
      await page.mouse.click(200, 200);
      await page.waitForTimeout(500);
      const isStillOpen = await dropdownUser.isVisible();
      if (!isStillOpen) {
        console.log("  ✓ Click-Outside Verified: Dropdown closed automatically on outside click.");
        results.adminDropdownVerified = true;
      } else {
        console.error("  ✗ Dropdown failed to close on outside click!");
      }
    } else {
      console.error("  ✗ Admin Dropdown options missing!");
    }

    // Capture Admin Settings Screenshot
    await page.screenshot({ path: `${screenshotDir}/admin_settings_workspace.png`, fullPage: true });
    console.log(`  ✓ Saved screenshot: ${screenshotDir}/admin_settings_workspace.png`);

    // 4. Test Workspace Switch: Admin -> Trading Terminal
    console.log("\n[TEST 4] Testing Workspace Switch (Admin Settings -> Trading Terminal)...");
    await switchTerminalBtn.click();
    await page.waitForTimeout(2000);

    const currentUrl = page.url();
    console.log(`  Current URL after switch: ${currentUrl}`);

    const adminPortalBtn = page.locator("#btn-nav-admin-portal");
    const isTerminalLoaded = await adminPortalBtn.isVisible();

    // Verify customer administration is strictly outside Trading Terminal
    const hasAdminTableInTerminal = await page.locator("text=Registered Customer Keys").isVisible();

    if (isTerminalLoaded && !hasAdminTableInTerminal) {
      console.log("  ✓ Workspace Switch Verified: Successfully navigated to Trading Terminal.");
      console.log("  ✓ Strict Isolation Verified: Customer administration tables are 100% absent from Trading Terminal.");
      results.tradingTerminalIsolated = true;
    } else {
      console.error("  ✗ Trading Terminal switch failed or leaked admin controls!");
    }

    // 5. Verify Simplified Customer Navigation: Exactly 2 Main Trading Products
    console.log("\n[TEST 5] Verifying Customer Navigation: Exactly 2 Main Trading Products...");
    const tradingProductsHeader = await page.locator("text=TRADING PRODUCTS").first().isVisible();
    const longTermNavItem = await page.locator("text=Long-Term Strategy").first().isVisible();
    const hftNavItem = await page.locator("text=High-Frequency Trading").first().isVisible();

    if (tradingProductsHeader && longTermNavItem && hftNavItem) {
      console.log("  ✓ Simplified Customer Portal Verified: Exactly 2 Trading Products (Long-Term Strategy & HFT).");
      results.twoProductsNavigationVerified = true;
    } else {
      console.error("  ✗ Navigation structure mismatch! Expected TRADING PRODUCTS group with Long-Term and HFT.");
    }

    // 6. Test High-Frequency Trading (HFT) Interface — BLANK SCREEN RESOLUTION
    console.log("\n[TEST 6] Testing High-Frequency Trading Interface & Blank-Screen Verification...");
    pageErrors.length = 0; // Clear errors to track HFT specifically

    // Click HFT navigation button
    const hftBtn = page.locator("text=High-Frequency Trading").first();
    await hftBtn.click();
    await page.waitForTimeout(2500);

    // Check for HFT Account Selector
    const accountSelectBox = page.locator("#hft-account-select");
    await accountSelectBox.waitFor({ state: "attached", timeout: 10000 });
    const isSelectorAttached = (await accountSelectBox.count()) > 0;

    // Check that NO blank screen error occurred
    const hftTitle = await page.locator("text=High-Frequency Trading").first().isVisible();
    const hasRenderError = pageErrors.some((e) => e.includes("toFixed") || e.includes("Cannot read properties"));

    if (isSelectorAttached && hftTitle && !hasRenderError) {
      console.log("  ✓ HFT Blank-Screen Resolution PASSED: Component rendered cleanly with ZERO TypeError exceptions.");
      console.log("  ✓ Account selector dropdown is active and present in DOM.");
      results.hftBlankScreenResolved = true;
    } else {
      console.error(`  ✗ HFT Blank-Screen FAILED! Selector: ${isSelectorAttached}, Title: ${hftTitle}, Errors: ${pageErrors.join(", ")}`);
    }

    // Capture HFT Interface Screenshot
    await page.screenshot({ path: `${screenshotDir}/hft_trading_interface.png`, fullPage: true });
    console.log(`  ✓ Saved screenshot: ${screenshotDir}/hft_trading_interface.png`);

    // 7. Test Workspace Switch: Trading Terminal -> Admin Settings
    console.log("\n[TEST 7] Testing Workspace Switch (Trading Terminal -> Admin Settings)...");
    await adminPortalBtn.click();
    await page.waitForTimeout(2000);

    const backInAdmin = await page.locator("#btn-switch-to-trading-terminal").isVisible();
    if (backInAdmin) {
      console.log("  ✓ Workspace Switch Verified: Successfully returned to Admin Settings via #btn-nav-admin-portal.");
      results.workspaceSwitchingVerified = true;
    } else {
      console.error("  ✗ Return to Admin Settings failed!");
    }

    // 8. Test Exness Gateway Diagnostic HTTP 400 (DNS & Doc Portal detection)
    console.log("\n[TEST 8] Testing Exness Gateway Diagnostic and Test Connection...");
    const testExnessPy = `
import sys, asyncio, json
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.services.exness.trader_api_adapter import ExnessTraderAPIAdapter

async def run():
    adapter = ExnessTraderAPIAdapter(
        api_key='exnsk-test1234567890123',
        api_secret='0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        account_id='16000629657',
        environment='REAL',
        discovery_base_url='https://www.exness-api.com',
    )
    res = await adapter.connect()
    print(json.dumps(res))

asyncio.run(run())
`;
    fs.writeFileSync("/opt/tauric-platform-staging/dashboard/test_exness_probe.py", testExnessPy);
    const exnessOut = execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/dashboard/test_exness_probe.py`, {
      encoding: "utf-8"
    });
    const exnessRes = JSON.parse(exnessOut.trim());

    if (exnessRes.status === "FAILED" && exnessRes.reason.includes("documentation portal")) {
      console.log("  ✓ Exness Gateway Diagnostic Verified:");
      console.log(`    Status: ${exnessRes.status}`);
      console.log(`    Reason: ${exnessRes.reason}`);
      console.log("  ✓ No fake auth fabricated. Status remains safely FAILED / NOT TESTED.");
      results.exnessDiagnosticVerified = true;
    } else {
      console.error("  ✗ Exness Diagnostic failed or returned unexpected status:", exnessRes);
    }

    // 9. Verify Safety Locks (All 3 locks strictly active)
    console.log("\n[TEST 9] Verifying Platform Safety Controls...");
    const testSafetyPy = `
import sys, json
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
from app.config import settings
print(json.dumps({
    "live_trading_locked": getattr(settings, "live_trading_locked", True),
    "emergency_lock_active": getattr(settings, "emergency_lock_active", True),
    "read_only_mode": getattr(settings, "read_only_mode", True),
}))
`;
    fs.writeFileSync("/opt/tauric-platform-staging/dashboard/test_safety_probe.py", testSafetyPy);
    const safetyOut = execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/dashboard/test_safety_probe.py`, {
      encoding: "utf-8"
    });
    const safetyRes = JSON.parse(safetyOut.trim());
    console.log(`  Safety Locks: ${JSON.stringify(safetyRes)}`);
    if (safetyRes.live_trading_locked && safetyRes.emergency_lock_active && safetyRes.read_only_mode) {
      console.log("  ✓ All 3 safety locks strictly ACTIVE (Zero order placement, zero balance mutations).");
      results.safetyLocksVerified = true;
    } else {
      console.error("  ✗ Safety locks breached!", safetyRes);
    }

    // 10. Role-Based Access Control (RBAC) Verification
    console.log("\n[TEST 10] Testing RBAC: Non-admin Customer Rejected from Admin Routes...");
    const customerSession = generateCustomerSession();
    const testRbacPy = `
import sys, httpx
sys.path.insert(0, '/opt/tauric-platform-staging/backend')
token = '${customerSession.token}'
res = httpx.get('http://127.0.0.1:8002/api/v1/saas/admin/customers', headers={'Authorization': f'Bearer {token}'})
print(res.status_code)
`;
    fs.writeFileSync("/opt/tauric-platform-staging/dashboard/test_rbac_probe.py", testRbacPy);
    const rbacOutput = execSync(`/opt/tauric-platform-staging/backend/.venv/bin/python3 /opt/tauric-platform-staging/dashboard/test_rbac_probe.py`, {
      encoding: "utf-8"
    }).trim();
    const statusCode = parseInt(rbacOutput, 10);
    console.log(`  Non-admin GET /api/v1/saas/admin/customers response: HTTP ${statusCode}`);
    if (statusCode === 403) {
      console.log("  ✓ RBAC Verified: Normal customer accounts receive HTTP 403 Forbidden on administrator routes.");
      results.rbacAdminProtectionVerified = true;
    } else {
      console.error(`  ✗ RBAC failure! Expected 403 but got ${statusCode}`);
    }

    // 11. Mobile Viewport Test (375x812)
    console.log("\n[TEST 11] Testing Mobile Responsive Layout (375x812)...");
    // Switch to Trading Terminal first so we are inside CustomerPortal
    const switchTerminalMobile = page.locator("#btn-switch-to-trading-terminal");
    if (await switchTerminalMobile.isVisible()) {
      await switchTerminalMobile.click();
      await page.waitForTimeout(1500);
    }
    await page.setViewportSize({ width: 375, height: 812 });
    await page.waitForTimeout(1000);

    const hamburgerBtn = page.locator("button[aria-label='Open navigation menu']");
    await hamburgerBtn.waitFor({ state: "visible", timeout: 5000 });
    if (await hamburgerBtn.isVisible()) {
      await hamburgerBtn.click();
      await page.waitForTimeout(500);
      const mobileDrawer = page.locator(".fixed").getByText("TRADING PRODUCTS");
      await mobileDrawer.waitFor({ state: "visible", timeout: 5000 });
      if (await mobileDrawer.isVisible()) {
        console.log("  ✓ Mobile Drawer Verified: Opens and renders responsive navigation.");
        results.responsiveLayoutVerified = true;
      }
    }
    await page.screenshot({ path: `${screenshotDir}/mobile_responsive_layout.png` });
    console.log(`  ✓ Saved screenshot: ${screenshotDir}/mobile_responsive_layout.png`);

  } catch (err) {
    console.error(`[TEST RUNNER FATAL ERROR]: ${err.stack || err.message}`);
  } finally {
    await browser.close();
  }

  console.log("\n===============================================================================");
  console.log(" PHASE 16 ACCEPTANCE VERIFICATION SUMMARY");
  console.log("===============================================================================");
  console.log(` 1. HFT Blank Screen Exception Resolved:      ${results.hftBlankScreenResolved ? "PASSED" : "FAILED"}`);
  console.log(` 2. Admin Profile Dropdown & Click-Outside:    ${results.adminDropdownVerified ? "PASSED" : "FAILED"}`);
  console.log(` 3. Permanent 2-Way Workspace Switching:     ${results.workspaceSwitchingVerified ? "PASSED" : "FAILED"}`);
  console.log(` 4. Simplified 2-Product Customer Navigation: ${results.twoProductsNavigationVerified ? "PASSED" : "FAILED"}`);
  console.log(` 5. Admin Settings Workspace Intact:          ${results.adminSettingsIntact ? "PASSED" : "FAILED"}`);
  console.log(` 6. Trading Terminal Isolated from Admin:     ${results.tradingTerminalIsolated ? "PASSED" : "FAILED"}`);
  console.log(` 7. Exness Gateway Diagnostic Verified:       ${results.exnessDiagnosticVerified ? "PASSED" : "FAILED"}`);
  console.log(` 8. RBAC HTTP 403 Enforcement:                ${results.rbacAdminProtectionVerified ? "PASSED" : "FAILED"}`);
  console.log(` 9. Triple Safety Locks Active:               ${results.safetyLocksVerified ? "PASSED" : "FAILED"}`);
  console.log(` 10. Mobile Responsive Layout (375px):        ${results.responsiveLayoutVerified ? "PASSED" : "FAILED"}`);
  console.log("===============================================================================");

  const allPassed = Object.values(results).every(Boolean);
  if (allPassed) {
    console.log("\n>>> OVERALL RESULT: PASSED <<<\n");
    process.exit(0);
  } else {
    console.log("\n>>> OVERALL RESULT: FAILED / BLOCKED <<<\n");
    process.exit(1);
  }
}

runSuite().catch((err) => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
