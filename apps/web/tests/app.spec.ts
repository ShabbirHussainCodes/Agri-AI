import { expect, test } from "@playwright/test";
import { askBody } from "../lib/askBody";
import { deflateSync } from "node:zlib";
import { answer, farm, farmCrop, FARM_ID, jpegSize, loginAs, mockApi, newState, scanAbstained, scanDiagnosis, SCAN_ID, scanRejected } from "./helpers";

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
  expect(state.requests.find((r) => r.path.endsWith("/ask"))?.body).toEqual({ question: "क्या आज सिंचाई करूँ?", language: "hi" });
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

test.describe("days since sowing counts calendar days on the phone's date", () => {
  test.use({ timezoneId: "Asia/Kolkata" });

  // The saved advisory from the first live run was created at 2026-10-04 20:24:51 UTC = 01:54 IST on
  // 5 Oct. A timestamp difference said 35 days for a 30 Aug sowing; the calendar says 36.
  test("01:54 IST on 5 Oct is day 36 for a 30 Aug sowing", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-10-04T20:24:51Z") });
    await loginAs(page);
    await mockApi(page, newState({ farmCrops: [farmCrop("2026-08-30")] }));
    await page.goto(`/farms/${FARM_ID}`);
    await expect(page.getByText("बुवाई को 36 दिन हुए")).toBeVisible();
  });

  test("sowing day itself is day 0", async ({ page }) => {
    await page.clock.install({ time: new Date("2026-10-04T20:24:51Z") });
    await loginAs(page);
    await mockApi(page, newState({ farmCrops: [farmCrop("2026-10-05")] }));
    await page.goto(`/farms/${FARM_ID}`);
    await expect(page.getByText("बुवाई को 0 दिन हुए")).toBeVisible();
  });
});

test("the answer card names the crop in the chosen language, also for an answer saved earlier", async ({ page }) => {
  await loginAs(page);
  const saved = {
    id: "77777777-7777-4777-8777-777777777777", farm_id: FARM_ID, question: "पुराना सवाल",
    response: answer(), abstained: false, created_at: "2026-10-04T20:24:51Z",
  };
  await mockApi(page, newState({ advisories: [saved] }));
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByRole("button", { name: "जवाब देखें" }).click();
  const card = page.getByTestId("answer");
  await expect(card).toContainText("गेहूं · बुवाई को 30 दिन हुए");
  await expect(card).not.toContainText("Wheat");
  await page.getByRole("button", { name: "English" }).click();
  await expect(card).toContainText("Wheat · Sown 30 days ago");
});

const NOTE = "इस जवाब में किसी जाँचे हुए दस्तावेज़ का इस्तेमाल नहीं हुआ। यह सिर्फ़ आपके खेत के रिकॉर्ड पर आधारित है।\n\nNo verified document was used for this answer. It rests only on your farm's record.";

test("a limitation note from the API is shown as its own card, in the chosen language", async ({ page }) => {
  await loginAs(page);
  await mockApi(page, newState({ askBody: answer({ limitations: NOTE }) }));
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByLabel("AgriAI से पूछिए").fill("गेहूं की बुवाई कब करनी चाहिए?");
  await page.getByRole("button", { name: "पूछें" }).click();
  const card = page.getByTestId("answer");
  await expect(card.getByRole("heading", { name: /इस जवाब की सीमा/ })).toBeVisible();
  await expect(card).toContainText("किसी जाँचे हुए दस्तावेज़ का इस्तेमाल नहीं हुआ");
  await expect(card).not.toContainText("No verified document");
  await page.screenshot({ path: "test-results/screens/09-limitations.png", fullPage: true });
  await page.getByRole("button", { name: "English" }).click();
  await expect(card).toContainText("No verified document was used for this answer");
  await expect(card).not.toContainText("जाँचे हुए दस्तावेज़");
});

test("no limitation card when the field is empty, absent (an answer saved earlier) or the answer abstains", async ({ page }) => {
  await loginAs(page);
  const withoutField: Record<string, unknown> = answer();
  delete withoutField.limitations; // saved before the field existed
  const records = [
    ["11111111-0000-4000-8000-000000000001", answer({ limitations: "" })],
    ["11111111-0000-4000-8000-000000000002", withoutField],
    ["11111111-0000-4000-8000-000000000003", answer({ limitations: NOTE, abstained: true })],
  ].map(([id, response], i) => ({
    id, farm_id: FARM_ID, question: `सवाल ${i + 1}`, response, abstained: false, created_at: `2026-10-0${i + 1}T10:00:00Z`,
  }));
  await mockApi(page, newState({ advisories: records }));
  await page.goto(`/farms/${FARM_ID}`);
  for (const q of ["सवाल 1", "सवाल 2", "सवाल 3"]) {
    await page.getByText(q, { exact: true }).locator("xpath=ancestor::section").getByRole("button", { name: "जवाब देखें" }).click();
  }
  await expect(page.getByTestId("answer")).toHaveCount(3);
  await expect(page.getByRole("heading", { name: /इस जवाब की सीमा/ })).toHaveCount(0);
});

test("the UI language travels with the question, and follows the language toggle", async ({ page }) => {
  await loginAs(page);
  const state = newState();
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await page.getByRole("button", { name: "English" }).click();
  await page.getByLabel("Ask AgriAI").fill("When should I irrigate?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByTestId("answer")).toBeVisible();
  expect(state.requests.find((r) => r.path.endsWith("/ask"))?.body).toEqual({ question: "When should I irrigate?", language: "en" });
});

test("without the switch the body is just the question", () => {
  expect(askBody("q", "hi", false)).toEqual({ question: "q" });
  expect(askBody("q", "hi", true)).toEqual({ question: "q", language: "hi" });
});


// ----------------------------------------------------------------------------------------------------------
// Phase 7: the photo check (ADR-0018)

/** A real PNG of the given size (a gradient, so it compresses): big enough that the client must shrink it. */
function png(width: number, height: number): Buffer {
  const crc = (buf: Buffer) => {
    let c = ~0;
    for (const byte of buf) {
      c ^= byte;
      for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
    return ~c >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const out = Buffer.alloc(8 + data.length + 4);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc(body), 8 + data.length);
    return out;
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const rows = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y++) {
    rows[y * (width * 3 + 1)] = 0;
    for (let x = 0; x < width; x++) {
      const o = y * (width * 3 + 1) + 1 + x * 3;
      rows[o] = 40 + (x % 120);
      rows[o + 1] = 110 + (y % 100);
      rows[o + 2] = 40;
    }
  }
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

async function choosePhoto(page: import("@playwright/test").Page, file = png(2400, 1800)) {
  await page.getByTestId("scan-gallery").setInputFiles({ name: "leaf.png", mimeType: "image/png", buffer: file });
  await page.getByRole("button", { name: "फोटो जाँचें" }).click();
}

test("photo check: the photo is shrunk and re-encoded on the phone, sent with the UI language, and the result keeps its parts apart", async ({ page }) => {
  await loginAs(page);
  const state = newState();
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await choosePhoto(page);

  const card = page.getByTestId("scan-result");
  await expect(card).toContainText("टमाटर का अगेती झुलसा");
  // the upload
  const [upload] = state.uploads;
  const image = upload.find((p) => p.name === "image")!;
  expect(image.contentType).toBe("image/jpeg");
  const size = jpegSize(image.data)!;
  expect(Math.max(size.width, size.height)).toBeLessThanOrEqual(1280);
  expect(Math.max(size.width, size.height)).toBeGreaterThan(1000); // shrunk, not destroyed
  expect(image.data.length).toBeLessThan(png(2400, 1800).length);
  expect(upload.find((p) => p.name === "language")?.data.toString()).toBe("hi");
  expect(state.requests.find((r) => r.path.endsWith("/scans") && r.method === "POST")?.auth).toBe("Bearer test-token");

  // the result: the agreed estimate, the second check, a BAND (not a percentage), the alternatives
  await expect(card.getByText("दूसरी, अलग जाँच भी यही कहती है")).toBeVisible();
  await expect(card.getByText("ऊँचा", { exact: true })).toBeVisible();
  await expect(card.getByText(/120 फोटो में से 91% बार सही निकले/)).toBeVisible();
  await expect(card.getByText(/और भी हो सकता है: .*पछेती झुलसा/)).toBeVisible();
  const text = await card.innerText();
  expect(text).not.toMatch(/93[.,]?7|94\s?%|0\.93/); // the classifier's own probability is never shown as "confidence"
  // what the AI saw / what the label says / the recommendation are separate cards
  await expect(card.getByText("फोटो में AI ने क्या देखा")).toBeVisible();
  await expect(card.getByText("Brown rings on the older leaves.")).toBeVisible();
  await expect(card.getByRole("heading", { name: /दवा का लेबल कार्ड/ })).toBeVisible();
  await expect(card.getByText("फोटो से लगता है कि यह अगेती झुलसा हो सकता है।")).toBeVisible();
  await expect(card.getByText(/किसी विशेषज्ञ की पुष्टि नहीं/)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/07-scan-diagnosis.png`, fullPage: true });

  // the language toggle switches the whole card
  await page.getByRole("button", { name: "English" }).click();
  await expect(card).toContainText("Tomato early blight");
  await expect(card.getByText(/not an expert's confirmation/)).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("photo check: a refused photo is a calm card with no candidates, no label card and no feedback buttons", async ({ page }) => {
  await loginAs(page);
  await mockApi(page, newState({ scanBody: scanAbstained() }));
  await page.goto(`/farms/${FARM_ID}`);
  await choosePhoto(page, png(800, 600));
  const card = page.getByTestId("scan-result");
  await expect(card.getByText("AgriAI बीमारी नहीं बता रहा")).toBeVisible();
  await expect(card.getByText(/दो अलग जाँचें इस फोटो पर एक जैसा जवाब नहीं दे रहीं/)).toBeVisible();
  await expect(card.getByRole("heading", { name: /दवा का लेबल कार्ड/ })).toHaveCount(0);
  await expect(card.getByText("और भी हो सकता है")).toHaveCount(0);
  await expect(card.getByText("क्या यह अनुमान सही लगा?")).toHaveCount(0);
  await page.screenshot({ path: `${SHOTS}/08-scan-abstained.png`, fullPage: true });
});

test("photo check: a blurry photo says take it again, and nothing is added to the diary", async ({ page }) => {
  await loginAs(page);
  const state = newState({ scanBody: scanRejected() });
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await choosePhoto(page, png(800, 600));
  const card = page.getByTestId("scan-result");
  await expect(card.getByText("दोबारा फोटो लीजिए")).toBeVisible();
  await expect(card.getByText("फोन को स्थिर पकड़ें")).toBeVisible();
  await expect(page.getByRole("list", { name: "खेत की डायरी" })).toHaveCount(0);
  await page.getByRole("button", { name: "दूसरी फोटो" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("button", { name: "📷 Take a photo" })).toBeVisible();
});

test("photo check: the daily limit and a rejected file show the API's own bilingual message; a dead server shows a network message", async ({ page }) => {
  await loginAs(page);
  const state = newState({
    scanStatus: 429,
    scanBody: { error: { code: "scan_limit_reached", scope: "user", message: "आज के लिए आपकी फोटो-जाँच की सीमा पूरी हो गई है।\n\nYou have used today's photo checks." } },
  });
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await choosePhoto(page, png(300, 300));
  await expect(page.locator("p[role=alert]")).toHaveText("आज के लिए आपकी फोटो-जाँच की सीमा पूरी हो गई है।");

  state.scanStatus = 415;
  state.scanBody = { error: { code: "unsupported_image_type", message: "यह फोटो का प्रकार काम नहीं करता।\n\nThis kind of file cannot be used." } };
  await page.getByRole("button", { name: "फोटो जाँचें" }).click();
  await expect(page.locator("p[role=alert]")).toHaveText("यह फोटो का प्रकार काम नहीं करता।");

  await page.route("http://api.test/**/scans", (route) => (route.request().method() === "POST" ? route.abort() : route.fallback()));
  await page.getByRole("button", { name: "फोटो जाँचें" }).click();
  await expect(page.locator("p[role=alert]")).toContainText("सर्वर तक नहीं पहुँच पाए");
});

test("photo check: feedback is sent once, deleting removes the check, and the diary shows a saved check", async ({ page }) => {
  await loginAs(page);
  const state = newState();
  await mockApi(page, state);
  await page.goto(`/farms/${FARM_ID}`);
  await choosePhoto(page, png(800, 600));
  const card = page.getByTestId("scan-result");
  await expect(card).toContainText("टमाटर का अगेती झुलसा");

  // the check is in the diary, newest first
  const diary = page.getByRole("list", { name: "खेत की डायरी" });
  await expect(diary).toContainText("फोटो की जाँच");

  await card.getByRole("button", { name: "नहीं, गलत" }).click();
  await expect(card.getByText("धन्यवाद, आपकी राय दर्ज हो गई।")).toBeVisible();
  expect(state.requests.find((r) => r.path === `/scans/${SCAN_ID}/feedback`)?.body).toEqual({ agrees: false });
  await expect(card.getByRole("button", { name: "नहीं, गलत" })).toHaveCount(0);

  await card.getByRole("button", { name: "यह जाँच और फोटो हटाएँ" }).click();
  await expect(card.getByText("पक्का हटाएँ?")).toBeVisible();
  await card.getByRole("button", { name: "दर्ज करें" }).click(); // "Delete for sure?" confirms with the generic confirm label
  await expect(card).toHaveCount(0);
  expect(state.requests.some((r) => r.method === "DELETE" && r.path === `/scans/${SCAN_ID}`)).toBe(true);
  await expect(page.getByRole("list", { name: "खेत की डायरी" })).toHaveCount(0);
});

test("photo check: a saved check opens from the diary after a reload, in the chosen language", async ({ page }) => {
  await loginAs(page);
  const saved = scanDiagnosis();
  await mockApi(
    page,
    newState({ scans: [{ id: SCAN_ID, farm_id: FARM_ID, image_path: `${FARM_ID}/${SCAN_ID}.jpg`, outcome: "diagnosis", abstained_because: null, response: saved, farmer_feedback: { agrees: true }, created_at: "2026-10-10T08:00:00Z" }] }),
  );
  await page.goto(`/farms/${FARM_ID}`);
  const diary = page.getByRole("list", { name: "खेत की डायरी" });
  await expect(diary).toContainText("फोटो की जाँच");
  await expect(diary).toContainText("टमाटर का अगेती झुलसा");
  await diary.getByRole("button", { name: "जवाब देखें" }).click();
  const card = diary.getByTestId("scan-result");
  await expect(card.getByText("दूसरी, अलग जाँच भी यही कहती है")).toBeVisible();
  await expect(card.getByText("धन्यवाद, आपकी राय दर्ज हो गई।")).toBeVisible(); // feedback already given
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("list", { name: "Farm diary" })).toContainText("Tomato early blight");
});

test("a scan saved by an older build (fields missing) still opens without crashing", async ({ page }) => {
  await loginAs(page);
  const old = { outcome: "abstained", abstained_because: "low_confidence", message: "AgriAI इस फोटो पर पक्का नहीं है।\n\nAgriAI is not sure.", quality: { passed: true, reasons: [] }, versions: {} };
  await mockApi(page, newState({ scans: [{ id: SCAN_ID, farm_id: FARM_ID, image_path: null, outcome: "abstained", abstained_because: "low_confidence", response: old, farmer_feedback: null, created_at: "2026-10-09T08:00:00Z" }] }));
  await page.goto(`/farms/${FARM_ID}`);
  const diary = page.getByRole("list", { name: "खेत की डायरी" });
  await diary.getByRole("button", { name: "जवाब देखें" }).click();
  await expect(diary.getByText("AgriAI इस फोटो पर पक्का नहीं है।")).toBeVisible();
});
