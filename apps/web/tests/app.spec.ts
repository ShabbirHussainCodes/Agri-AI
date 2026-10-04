import { expect, test } from "@playwright/test";
import { answer, FARM_ID, farm, loginAs, mockApi, newState } from "./helpers";

const SHOTS = "test-results/screens";

test("logged out: login form in Hindi, language toggle switches to English", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "लॉगिन" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/01-login-hi.png`, fullPage: true });
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible(); // remembered on this device
});

test("farm list links to the farm and to onboarding", async ({ page }) => {
  await loginAs(page);
  await mockApi(page, newState());
  await page.goto("/");
  await expect(page.getByText("Ramu ka khet")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/02-farms.png`, fullPage: true });
  await page.getByRole("link", { name: /नया खेत जोड़ें/ }).click();
  await expect(page).toHaveURL(/\/farms\/new$/);
});

test("onboarding: name, manual location, soil button, crop and sowing date, then lands on the farm", async ({ page }) => {
  await loginAs(page);
  const state = newState({ farms: [] });
  await mockApi(page, state);
  await page.goto("/farms/new");
  await page.getByLabel("खेत का नाम").fill("Ramu ka khet");
  await page.getByLabel(/अक्षांश/).fill("22.6");
  await page.getByLabel(/देशांतर/).fill("80.4");
  await page.getByRole("radio", { name: /दोमट/ }).click();
  await page.getByLabel("फसल").selectOption({ label: "गेहूं" });
  await page.getByLabel("बुवाई की तारीख").fill("2026-09-01");
  await page.screenshot({ path: `${SHOTS}/03-onboarding.png`, fullPage: true });
  await page.getByRole("button", { name: "खेत सहेजें" }).click();
  await expect(page).toHaveURL(new RegExp(`/farms/${FARM_ID}$`));

  const post = state.requests.find((r) => r.method === "POST" && r.path === "/farms");
  expect(post?.body).toEqual({ name: "Ramu ka khet", lat: 22.6, lon: 80.4, soil_texture: "loamy" });
  expect(post?.auth).toBe("Bearer test-token");
  const crop = state.requests.find((r) => r.path === `/farms/${FARM_ID}/crops` && r.method === "POST");
  expect(crop?.body).toMatchObject({ sowing_date: "2026-09-01" });
});

test("onboarding rejects a half-typed location before calling the API", async ({ page }) => {
  await loginAs(page);
  const state = newState({ farms: [] });
  await mockApi(page, state);
  await page.goto("/farms/new");
  await page.getByLabel("खेत का नाम").fill("X");
  await page.getByLabel(/अक्षांश/).fill("22.6");
  await page.getByRole("button", { name: "खेत सहेजें" }).click();
  await expect(page.locator("p[role=alert]")).toBeVisible();
  expect(state.requests.some((r) => r.method === "POST" && r.path === "/farms")).toBe(false);
});

test("farm home: asking shows the advice in the chosen language and fills the diary", async ({ page }) => {
  await loginAs(page);
  const state = newState();
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await expect(page.getByRole("heading", { name: "Ramu ka khet" })).toBeVisible();
  await page.getByLabel("AgriAI से पूछिए").fill("क्या आज सिंचाई करूँ?");
  await page.getByRole("button", { name: "पूछें" }).click();
  const card = page.getByTestId("answer");
  await expect(card).toContainText("अभी सिंचाई की ज़रूरत नहीं है।");
  await expect(card).not.toContainText("No irrigation is needed");
  await expect(page.getByRole("list", { name: "खेत की डायरी" })).toContainText("क्या आज सिंचाई करूँ?");
  await page.screenshot({ path: `${SHOTS}/04-answer-hi.png`, fullPage: true });
  await page.getByRole("button", { name: "English" }).click();
  await expect(card).toContainText("No irrigation is needed right now.");
  expect(state.requests.find((r) => r.path.endsWith("/ask"))?.body).toEqual({ question: "क्या आज सिंचाई करूँ?" });
});

test("evidence types stay visibly separate: calculated, label card, documents, reasoning", async ({ page }) => {
  await loginAs(page);
  const rich = answer({
    water_balance: {
      verdict: "irrigate_now", as_of: "2026-10-04", assumptions: ["Constant root depth."], forecast_rain_mm: [],
      depletion_mm: 42.5, raw_mm: 40.0, taw_mm: 80, days_to_raw: null, data_source: "Weather data by Open-Meteo.com (CC BY 4.0)",
    },
    agrochemical_label: [
      { row_id: "r1", molecule: "x", crop: "Wheat", pest: "Aphid", formulation: "Test 10% SC", dose_formulation: 100, dose_formulation_unit: "ml",
        waiting_period_days: 7, label_date: "2026-01-01", source_ref: "CIB&RC p.1", table_version: "t", text: "t", dilution_l_per_ha: 500 },
    ],
    retrieved_evidence: [
      { chunk_id: "c1", doc_title: "Wheat trial", doc_type: "paper", licence: "CC BY", url: "https://example.org/x", quote: "Sow wheat in November.", source_org: "ICAR", published_year: 2020, page: 4 },
    ],
  });
  await mockApi(page, newState({ askBody: rich }));
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByLabel("AgriAI से पूछिए").fill("सिंचाई?");
  await page.getByRole("button", { name: "पूछें" }).click();
  const card = page.getByTestId("answer");
  await expect(card.getByText("AgriAI ने गिना")).toBeVisible();
  await expect(card.getByText("42.5 mm")).toBeVisible();
  await expect(card.getByText("Weather data by Open-Meteo.com (CC BY 4.0)")).toBeVisible();
  await expect(card.getByRole("heading", { name: /दवा का लेबल कार्ड/ })).toBeVisible();
  await expect(card.getByText(/पैकेट पर छपा लेबल ही कानूनी स्रोत/)).toBeVisible();
  await expect(card.getByText("दस्तावेज़ क्या कहते हैं")).toBeVisible();
  await expect(card.getByText("Sow wheat in November.")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/05-answer-evidence.png`, fullPage: true });
});

test("an abstention is shown calmly, with no evidence cards and no label card", async ({ page }) => {
  await loginAs(page);
  const abstain = answer({
    abstained: true, abstained_because: "dose_safety",
    recommendation: "मैं दवा की मात्रा नहीं बता सकता।\n\nI cannot give a pesticide amount.",
    agrochemical_label: [{ row_id: "r1", molecule: "x", crop: "c", pest: "p", formulation: "f", dose_formulation: 1, dose_formulation_unit: "g", waiting_period_days: 1, label_date: "d", source_ref: "s", table_version: "t", text: "t" }],
  });
  await mockApi(page, newState({ askBody: abstain }));
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByLabel("AgriAI से पूछिए").fill("कितनी दवा डालूँ?");
  await page.getByRole("button", { name: "पूछें" }).click();
  const card = page.getByTestId("answer");
  await expect(card.getByText("पक्का जवाब नहीं दे सकता")).toBeVisible();
  await expect(card.getByRole("heading", { name: /दवा का लेबल कार्ड/ })).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/06-abstain.png`, fullPage: true });
});

test("daily limit: the API's own bilingual message is shown, in the chosen language", async ({ page }) => {
  await loginAs(page);
  await mockApi(
    page,
    newState({ askStatus: 429, askBody: { error: { code: "ask_limit_reached", scope: "user", message: "आज के सवाल पूरे हो गए।\n\nYou have used today's questions." } } }),
  );
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByLabel("AgriAI से पूछिए").fill("hello");
  await page.getByRole("button", { name: "पूछें" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("आज के सवाल पूरे हो गए।");
});

test("server unreachable: a clear network message, not a blank screen", async ({ page }) => {
  await loginAs(page);
  await mockApi(page, newState());
  await page.goto(`/farms/${FARM_ID}`);
  await expect(page.getByRole("heading", { name: "Ramu ka khet" })).toBeVisible();
  await page.route("http://api.test/**/ask", (route) => route.abort());
  await page.getByLabel("AgriAI से पूछिए").fill("hello");
  await page.getByRole("button", { name: "पूछें" }).click();
  await expect(page.locator("p[role=alert]")).toContainText("सर्वर तक नहीं पहुँच पाए");
});

test("irrigation log needs a confirmation, then writes today's irrigation with the depth", async ({ page }) => {
  await loginAs(page);
  const state = newState();
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByRole("button", { name: /आज सिंचाई की/ }).click();
  expect(state.requests.some((r) => r.method === "POST" && r.path.includes("/activities"))).toBe(false); // nothing written yet
  await page.getByLabel(/कितने मिमी/).fill("25");
  await page.screenshot({ path: `${SHOTS}/07-log-irrigation.png`, fullPage: true });
  await page.getByRole("button", { name: "दर्ज करें" }).click();
  await expect(page.getByRole("status")).toContainText("सिंचाई दर्ज हो गई");
  const post = state.requests.find((r) => r.path.includes("/activities"));
  expect(post?.body).toMatchObject({ type: "irrigation", details: { depth_mm: 25 } });
  expect((post?.body as { occurred_on: string }).occurred_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await expect(page.getByRole("list", { name: "खेत की डायरी" })).toContainText("25 mm");
});

test("a farm without soil or location shows the banner and can be completed", async ({ page }) => {
  await loginAs(page);
  const state = newState({ farms: [farm({ soil_texture: null, lat: null, lon: null })] });
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await expect(page.getByRole("note")).toContainText("मिट्टी का प्रकार");
  await page.screenshot({ path: `${SHOTS}/08-profile-banner.png`, fullPage: true });
  await page.getByRole("button", { name: "खेत की जानकारी बदलें" }).click();
  await page.getByRole("radio", { name: /चिकनी/ }).click();
  await page.getByLabel(/अक्षांश/).fill("22.6");
  await page.getByLabel(/देशांतर/).fill("80.4");
  await page.getByRole("button", { name: "सहेजें", exact: true }).click();
  await expect(page.getByRole("note")).toHaveCount(0);
  expect(state.requests.find((r) => r.method === "PATCH")?.body).toEqual({ soil_texture: "clayey", lat: 22.6, lon: 80.4 });
});

test("no horizontal scroll at phone width on the farm home", async ({ page }) => {
  await loginAs(page);
  await mockApi(page, newState());
  await page.goto(`/farms/${FARM_ID}`);
  await expect(page.getByRole("heading", { name: "Ramu ka khet" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
