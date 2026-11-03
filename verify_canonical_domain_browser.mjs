import puppeteer from "/opt/tauric-platform/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js";

const browser = await puppeteer.launch({
  executablePath: "/root/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--window-size=1440,950"]
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 950 });

const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
const status404Urls = [];

page.on("console", msg => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", err => pageErrors.push(err.message));
page.on("requestfailed", req => {
  failedRequests.push(`${req.method()} ${req.url()} -> ${req.failure()?.errorText}`);
});
page.on("response", resp => {
  if (resp.status() >= 400) {
    status404Urls.push(`${resp.status()} ${resp.url()}`);
  }
});

console.log("1. Navigating to canonical root https://sheltr.agency/ ...");
const respRoot = await page.goto("https://sheltr.agency/", { waitUntil: "networkidle2", timeout: 45000 });
await new Promise(r => setTimeout(r, 2500));

const rootStatus = respRoot.status();
const rootFinalUrl = page.url();
const rootTitle = await page.title();

console.log("2. Opening Universal API Connections modal on https://sheltr.agency/ ...");
const openedModal = await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll("button"));
  const apiBtn = buttons.find(b => /API Connections|Connections|Manage APIs|BITGET|Master/i.test(b.innerText));
  if (apiBtn) {
    apiBtn.click();
    return apiBtn.innerText.trim();
  }
  return null;
});
await new Promise(r => setTimeout(r, 1500));

const addFormAudit = await page.evaluate(() => {
  const formInputs = Array.from(document.querySelectorAll("input")).filter(el => {
    const ph = (el.placeholder || "").toLowerCase();
    return ph.includes("bitget api 1") || ph.includes("api key") || ph.includes("secret") || ph.includes("passphrase");
  });
  const modalEl = formInputs[0]?.closest("div.fixed") || document.body;
  const text = modalEl.innerText;
  const selectsInAddForm = formInputs[0]?.closest("div.rounded-xl")?.querySelectorAll("select").length ?? -1;
  return {
    inputCount: formInputs.length,
    placeholders: formInputs.map(i => i.placeholder),
    selectsInAddForm,
    hasOldWizardText: /Select Asset Market Category|Select Crypto Provider|Intended API Permissions/i.test(text),
    hasMasterProfile: text.includes("Master") && text.includes("bg_b••••••••4881"),
    hasPassphrasePresent: text.includes("Present (Encrypted)")
  };
});

console.log("3. Opening Permissions & Capabilities modal for Master profile...");
const openedCaps = await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll("button"));
  const capBtn = buttons.find(b => /Permissions & Capabilities/i.test(b.innerText));
  if (capBtn) {
    capBtn.click();
    return true;
  }
  return false;
});
await new Promise(r => setTimeout(r, 1200));

const capsAudit = await page.evaluate(() => {
  const bodyText = document.body.innerText;
  return {
    hasCapabilitiesTitle: bodyText.includes("Permissions & Capabilities"),
    hasProfileId: bodyText.includes("prof_bitget_demo_a2bb3478"),
    hasPublicMarketVerified: bodyText.includes("Public market data") && bodyText.includes("VERIFIED"),
    hasPrivateAuthFailed: bodyText.includes("Private account authentication") && bodyText.includes("FAILED"),
    hasLiveOrderBlocked: bodyText.includes("Live order placement") && bodyText.includes("BLOCKED_BY_SAFETY_LOCK"),
    hasEnvMismatchCode: bodyText.includes("40099") && bodyText.includes("ENVIRONMENT_MISMATCH")
  };
});

console.log("4. Verifying https://sheltr.agency/trading/ redirect in browser...");
const page2 = await browser.newPage();
const respTrading = await page2.goto("https://sheltr.agency/trading/", { waitUntil: "networkidle2", timeout: 45000 });
const tradingFinalUrl = page2.url();
const tradingStatus = respTrading.status();

await browser.close();

const summary = {
  rootStatus,
  rootFinalUrl,
  rootTitle,
  openedModal,
  addFormAudit,
  openedCaps,
  capsAudit,
  tradingRedirect: {
    requestedUrl: "https://sheltr.agency/trading/",
    finalUrl: tradingFinalUrl,
    finalStatus: tradingStatus
  },
  status404Urls,
  consoleErrors,
  pageErrors,
  failedRequests
};

console.log(JSON.stringify(summary, null, 2));
if (
  rootStatus !== 200 ||
  rootFinalUrl !== "https://sheltr.agency/" ||
  addFormAudit.inputCount !== 4 ||
  addFormAudit.selectsInAddForm !== 0 ||
  addFormAudit.hasOldWizardText ||
  !addFormAudit.hasMasterProfile ||
  !capsAudit.hasCapabilitiesTitle ||
  !capsAudit.hasLiveOrderBlocked ||
  tradingFinalUrl !== "https://sheltr.agency/"
) {
  process.exit(1);
}
