import type { Page, Route } from "@playwright/test";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization,content-type",
  "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
};

export const FARM_ID = "11111111-1111-4111-8111-111111111111";
export const FARM_CROP_ID = "22222222-2222-4222-8222-222222222222";
export const CROP_ID = "33333333-3333-4333-8333-333333333333";

export const WHEAT = { id: CROP_ID, name_en: "Wheat", name_hi: "गेहूं", default_duration_days: 120 };

export function farm(over: Record<string, unknown> = {}) {
  return {
    id: FARM_ID,
    profile_id: "44444444-4444-4444-8444-444444444444",
    name: "Ramu ka khet",
    lat: 22.6,
    lon: 80.4,
    district: null,
    state: null,
    area_ha: null,
    agro_climatic_zone: null,
    soil_texture: "loamy",
    created_at: "2026-10-01T00:00:00Z",
    ...over,
  };
}

export function farmCrop(sowing = "2026-09-01") {
  return {
    id: FARM_CROP_ID,
    farm_id: FARM_ID,
    crop_id: CROP_ID,
    variety: null,
    sowing_date: sowing,
    expected_harvest: null,
    status: "active",
    created_at: "2026-09-01T00:00:00Z",
  };
}

export function answer(over: Record<string, unknown> = {}) {
  return {
    question: "q",
    recommendation: "अभी सिंचाई की ज़रूरत नहीं है।\n\nNo irrigation is needed right now.",
    model_inference: "Soil still holds water.",
    structured_data: { farm_name: "Ramu ka khet", crop_name: "Wheat", days_since_sowing: 30 },
    live_data: null,
    retrieved_evidence: [],
    water_balance: null,
    agrochemical_label: [],
    confidence: 0.8,
    abstained: false,
    abstained_because: null,
    citations_valid: true,
    ...over,
  };
}

export const SCAN_ID = "77777777-7777-4777-8777-777777777777";

const QUALITY = { passed: true, reasons: [], thresholds_version: "t", sharpness: 210, mean_luma: 110, vegetation_fraction: 0.4, width: 1024, height: 768 };
const VERSIONS = { classifier: "r/m@abc", calibration: "calibration-v1", label_map: "label-map-v1", vision_model: "qwen/qwen3.8-27b" };

function candidate(label: string, nameEn: string, nameHi: string, crop: string, condition: string, probability: number, leading: boolean) {
  return { label, crop, condition, name_en: nameEn, name_hi: nameHi, name_hi_status: "unreviewed", probability, leading, second_opinion_agrees: leading };
}

/** A diagnosed photo: tomato early blight, agreed by both models, with a label card and a quoted document. */
export function scanDiagnosis(over: Record<string, unknown> = {}) {
  return {
    outcome: "diagnosis", abstained_because: null, detail: null, message: "", quality: QUALITY,
    candidates: [
      candidate("Tomato___Early_blight", "Tomato early blight", "टमाटर का अगेती झुलसा", "tomato", "early_blight", 0.9371, true),
      candidate("Tomato___Late_blight", "Tomato late blight", "टमाटर का पछेती झुलसा", "tomato", "late_blight", 0.04, false),
      candidate("Tomato___Septoria_leaf_spot", "Tomato Septoria leaf spot", "टमाटर का सेप्टोरिया पत्ती धब्बा रोग", "tomato", "septoria_leaf_spot", 0.01, false),
    ],
    band: { name: "high", observed_accuracy: 0.91, n: 120, measured_on: "PlantDoc train photos (CC-BY-4.0; web-scraped field photos)" },
    model_saw: { plant_part: "leaf", crop: "tomato", condition: "early_blight", symptoms: "Brown rings on the older leaves." },
    advisory: answer({
      recommendation: "फोटो से लगता है कि यह अगेती झुलसा हो सकता है। दवा का लेबल कार्ड नीचे देखिए।\n\nThe photo suggests early blight. See the label card below.",
      structured_data: { farm_name: "Ramu ka khet", crop_name: "Tomato", days_since_sowing: 30 },
      agrochemical_label: [{ row_id: "t1", molecule: "azoxystrobin", crop: "tomato", pest: "early blight", formulation: "Azoxystrobin 23% SC", dose_formulation: 500, dose_formulation_unit: "ml", dose_ai_g_per_ha: 115, dilution_l_per_ha: 500, waiting_period_days: 3, label_date: "2026-03-31", source_ref: "CIB&RC Major Uses p. 12", table_version: "major-uses-v1", text: "t" }],
      limitations: "इस जवाब में किसी जाँचे हुए दस्तावेज़ का इस्तेमाल नहीं हुआ; यह सिर्फ़ फोटो की स्वचालित जाँच पर आधारित है।\n\nNo verified document was used for this answer; it rests only on the automatic photo check.",
    }),
    note: "यह फोटो से की गई अपने-आप वाली जाँच है, किसी विशेषज्ञ की पुष्टि नहीं।\n\nThis is an automatic check from a photo, not an expert's confirmation.",
    versions: VERSIONS, scan_id: SCAN_ID, image_path: `${FARM_ID}/${SCAN_ID}.jpg`, created_at: "2026-10-10T08:00:00Z",
    ...over,
  };
}

export function scanAbstained(over: Record<string, unknown> = {}) {
  return {
    outcome: "abstained", abstained_because: "model_disagreement", detail: "crop_differs",
    message: "AgriAI की दो अलग जाँचें इस फोटो पर एक जैसा जवाब नहीं दे रहीं, इसलिए कोई बीमारी नहीं बता रहा।\n\nAgriAI's two separate checks do not agree about this photo, so it is not naming a disease.",
    quality: QUALITY, candidates: [], band: null, model_saw: null, advisory: null, note: "", versions: VERSIONS,
    scan_id: SCAN_ID, image_path: null, created_at: "2026-10-10T08:00:00Z", ...over,
  };
}

export function scanRejected() {
  return {
    outcome: "rejected_quality", abstained_because: "quality_rejected", detail: "too_blurry",
    message: "फोटो धुंधली है। फोन को स्थिर पकड़ें और दोबारा फोटो लें।\n\nThe photo is blurry. Hold the phone steady and take it again.",
    quality: { ...QUALITY, passed: false, reasons: ["too_blurry"], sharpness: 3 }, candidates: [], band: null, model_saw: null, advisory: null,
    note: "", versions: VERSIONS, scan_id: null, image_path: null, created_at: null,
  };
}

export type Part = { name: string; filename?: string; contentType?: string; data: Buffer };

/** Splits a multipart/form-data body into its parts (just enough for the tests). */
export function parseMultipart(body: Buffer, contentType: string): Part[] {
  const boundary = /boundary=(.+)$/.exec(contentType)?.[1];
  if (!boundary) return [];
  const delimiter = Buffer.from(`--${boundary}`);
  const parts: Part[] = [];
  let at = body.indexOf(delimiter);
  while (at !== -1) {
    const next = body.indexOf(delimiter, at + delimiter.length);
    if (next === -1) break;
    const raw = body.subarray(at + delimiter.length + 2, next - 2); // drop the CRLF after the boundary and before the next
    const split = raw.indexOf("\r\n\r\n");
    const head = raw.subarray(0, split).toString("utf8");
    parts.push({
      name: /name="([^"]+)"/.exec(head)?.[1] ?? "",
      filename: /filename="([^"]*)"/.exec(head)?.[1],
      contentType: /Content-Type: (.+)/i.exec(head)?.[1]?.trim(),
      data: raw.subarray(split + 4),
    });
    at = next;
  }
  return parts;
}

/** Width and height from a JPEG's start-of-frame marker. */
export function jpegSize(data: Buffer): { width: number; height: number } | null {
  let i = 2;
  while (i + 9 < data.length) {
    if (data[i] !== 0xff) return null;
    const marker = data[i + 1];
    if (marker >= 0xc0 && marker <= 0xc3) return { height: data.readUInt16BE(i + 5), width: data.readUInt16BE(i + 7) };
    i += 2 + data.readUInt16BE(i + 2);
  }
  return null;
}

export type ApiState = {
  farms: unknown[];
  farmCrops: unknown[];
  activities: unknown[];
  advisories: unknown[];
  askStatus: number;
  askBody: unknown;
  scans: unknown[];
  scanStatus: number;
  scanBody: unknown;
  uploads: Part[][];
  requests: { method: string; path: string; body: unknown; auth: string | null }[];
};

export function newState(over: Partial<ApiState> = {}): ApiState {
  return {
    farms: [farm()],
    farmCrops: [farmCrop()],
    activities: [],
    advisories: [],
    askStatus: 200,
    askBody: answer(),
    scans: [],
    scanStatus: 200,
    scanBody: scanDiagnosis(),
    uploads: [],
    requests: [],
    ...over,
  };
}

/** A logged-in browser: supabase-js reads its session from localStorage and, while the token is
 *  unexpired, makes no network call. The key is sb-<first label of the host>-auth-token. */
export async function loginAs(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem(
      "sb-127-auth-token",
      JSON.stringify({
        access_token: "test-token",
        refresh_token: "r",
        token_type: "bearer",
        expires_in: 3600,
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        user: { id: "44444444-4444-4444-8444-444444444444", aud: "authenticated", email: "farmer@example.com", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" },
      }),
    );
  });
}

export async function mockApi(page: Page, state: ApiState) {
  await page.route("http://api.test/**", async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const path = url.pathname;
    let body: unknown = null;
    try {
      body = req.postDataJSON();
    } catch {
      /* no body */
    }
    state.requests.push({ method: req.method(), path, body, auth: await req.headerValue("authorization") });
    const json = (status: number, data: unknown) =>
      route.fulfill({ status, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify(data) });

    if (path === "/crops") return json(200, [WHEAT]);
    if (path === "/farms" && req.method() === "GET") return json(200, state.farms);
    if (path === "/farms" && req.method() === "POST") {
      const f = farm({ ...(body as object) });
      state.farms = [f];
      return json(201, f);
    }
    if (path === `/farms/${FARM_ID}` && req.method() === "GET") return json(200, state.farms[0]);
    if (path === `/farms/${FARM_ID}` && req.method() === "PATCH") {
      state.farms = [{ ...(state.farms[0] as object), ...(body as object) }];
      return json(200, state.farms[0]);
    }
    if (path === `/farms/${FARM_ID}/crops` && req.method() === "GET") return json(200, state.farmCrops);
    if (path === `/farms/${FARM_ID}/crops` && req.method() === "POST") return json(201, farmCrop());
    if (path === `/farms/${FARM_ID}/timeline`) return json(200, state.activities);
    if (path === `/farms/${FARM_ID}/advisories`) return json(200, state.advisories);
    if (path === `/farms/${FARM_ID}/ask`) {
      if (state.askStatus === 200) {
        state.advisories = [
          { id: "55555555-5555-4555-8555-555555555555", farm_id: FARM_ID, question: (body as { question: string }).question, response: state.askBody, abstained: false, created_at: new Date().toISOString() },
          ...state.advisories,
        ];
      }
      return json(state.askStatus, state.askBody);
    }
    if (path === `/farms/${FARM_ID}/scans` && req.method() === "GET") return json(200, state.scans);
    if (path === `/farms/${FARM_ID}/scans` && req.method() === "POST") {
      const buf = req.postDataBuffer();
      if (buf) state.uploads.push(parseMultipart(buf, (await req.headerValue("content-type")) ?? ""));
      if (state.scanStatus === 200) {
        const saved = state.scanBody as { scan_id: string | null; outcome: string };
        if (saved.scan_id) {
          state.scans = [{ id: saved.scan_id, farm_id: FARM_ID, image_path: null, outcome: saved.outcome, abstained_because: null, response: state.scanBody, farmer_feedback: null, created_at: new Date().toISOString() }, ...state.scans];
        }
      }
      return json(state.scanStatus, state.scanBody);
    }
    if (path === `/scans/${SCAN_ID}/feedback` && req.method() === "POST") return json(200, { id: SCAN_ID, farmer_feedback: body });
    if (path === `/scans/${SCAN_ID}` && req.method() === "DELETE") {
      state.scans = [];
      return route.fulfill({ status: 204, headers: CORS });
    }
    if (path === `/farm-crops/${FARM_CROP_ID}/activities` && req.method() === "POST") {
      const b = body as { type: string; occurred_on: string; details: object };
      state.activities = [{ id: "66666666-6666-4666-8666-666666666666", farm_crop_id: FARM_CROP_ID, source: "user", created_at: new Date().toISOString(), ...b }, ...state.activities];
      return json(201, state.activities[0]);
    }
    return json(404, { error: { code: "not_found", message: "unmocked " + path } });
  });
}
