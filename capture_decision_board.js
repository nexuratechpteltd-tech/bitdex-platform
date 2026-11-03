const puppeteer = require("puppeteer");
const path = require("path");
const { execSync } = require("child_process");

(async () => {
  console.log("Launching Puppeteer for Decision Board capture...");
  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer"]
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const out = execSync("PYTHONPATH=/opt/tauric-platform-staging/backend /opt/tauric-platform-staging/backend/.venv/bin/python3 /tmp/get_session.py test.customer@bitdex.ltd", { encoding: "utf-8" });
  const sess = JSON.parse(out.trim());

  await page.goto("http://127.0.0.1:33900/", { waitUntil: "domcontentloaded" });
  await page.evaluate((s) => {
    localStorage.setItem("bitdex_token", s.token);
    localStorage.setItem("tauric_session_token", s.token);
    localStorage.setItem("tauric_user", JSON.stringify(s.user));
    localStorage.setItem("tauric_session_user", JSON.stringify(s.user));
  }, sess);
  await page.goto("http://127.0.0.1:33900/", { waitUntil: "networkidle2" });

  console.log("Waiting for signals and Technical Analysis button to appear...");
  await page.waitForFunction(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    return btns.some(el => el.textContent && el.textContent.includes("Technical Analysis"));
  }, { timeout: 15000 });

  const clicked = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const b = btns.find(el => el.textContent && el.textContent.includes("Technical Analysis"));
    if (b) {
      b.scrollIntoView({ behavior: "instant", block: "center" });
      b.click();
      return true;
    }
    return false;
  });
  console.log("Clicked Technical Analysis:", clicked);

  // Wait for 4-engine AI synthesis to complete and render the decision board
  await new Promise(r => setTimeout(r, 8500));

  await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_2_four_engine_decision_board_1440.png", fullPage: false });
  console.log("Saved evidence_2_four_engine_decision_board_1440.png");
  await browser.close();
})();
