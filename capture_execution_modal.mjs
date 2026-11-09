import puppeteer from "/opt/tauric-platform/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";
import { execSync } from "child_process";

const credsOutput = execSync(`PYTHONPATH=/opt/tauric-platform-staging/backend /opt/tauric-platform-staging/backend/.venv/bin/python3 -c '
import sqlite3, jwt, time, json
from app.services.auth_manager import JWT_SECRET_KEY, JWT_ALGORITHM
token = jwt.encode({"sub": "USR-402F7BFE6D", "exp": int(time.time() + 86400)}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
print(json.dumps({"token": token}))
'`).toString();

const token = JSON.parse(credsOutput).token;

const browser = await puppeteer.launch({
  executablePath: "/root/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1440,1100"]
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1100 });
await page.setExtraHTTPHeaders({
  "X-Forwarded-Host": "bitdex.ltd",
  "X-Forwarded-Proto": "https"
});

await page.goto("http://127.0.0.1:33900/#trading", { waitUntil: "domcontentloaded", timeout: 30000 });

await page.evaluate((jwtToken) => {
  localStorage.setItem("tauric_session_token", jwtToken);
  localStorage.setItem("bitdex_token", jwtToken);
  localStorage.setItem("tauric_token", jwtToken);
  localStorage.setItem("sheltr_token", jwtToken);
  localStorage.setItem("tauric_session_user", JSON.stringify({
    user_id: "USR-402F7BFE6D",
    email: "test_customer@bitdex.io",
    role: "CUSTOMER",
    username: "designkrao"
  }));
}, token);

await page.goto("http://127.0.0.1:33900/#trading", { waitUntil: "networkidle2", timeout: 30000 });
await new Promise(r => setTimeout(r, 3000));

// Wait for signals to load, then click Technical Analysis on first card
console.log("Looking for signal card...");
await page.evaluate(() => {
  const cards = Array.from(document.querySelectorAll("button"));
  const taBtn = cards.find(b => b.textContent && b.textContent.includes("Technical Analysis"));
  if (taBtn) {
    taBtn.click();
    console.log("Clicked Technical Analysis button");
  }
});

await new Promise(r => setTimeout(r, 2000));

// Inside the modal, find and click "Execute Trade" or trigger the action
console.log("Looking for Execute Trade button...");
const clickedExecute = await page.evaluate(() => {
  const btns = Array.from(document.querySelectorAll("button"));
  const execBtn = btns.find(b => b.textContent && b.textContent.trim() === "Execute Trade");
  if (execBtn) {
    execBtn.click();
    return true;
  }
  return false;
});
console.log("Clicked Execute Trade:", clickedExecute);

await new Promise(r => setTimeout(r, 2000));

// Inspect dropdown options
const dropdownOptions = await page.evaluate(() => {
  const sel = document.querySelector("#execution-exchange-profile-select");
  if (!sel) return ["Select element not found"];
  return Array.from(sel.options).map(o => o.text);
});
console.log("Dropdown options in execution modal:", dropdownOptions);

// Take screenshot of modal
await page.screenshot({ path: "/opt/tauric-platform-staging/evidence_screenshots/evidence_execution_modal_dropdown_live.png" });
console.log("Saved evidence_execution_modal_dropdown_live.png");

await browser.close();
console.log("Done!");
