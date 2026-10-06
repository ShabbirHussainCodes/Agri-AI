import type { Page, Route } from "@playwright/test";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization,content-type",
  "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
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

export type ApiState = {
  farms: unknown[];
  farmCrops: unknown[];
  activities: unknown[];
  advisories: unknown[];
  askStatus: number;
  askBody: unknown;
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
    if (path === `/farm-crops/${FARM_CROP_ID}/activities` && req.method() === "POST") {
      const b = body as { type: string; occurred_on: string; details: object };
      state.activities = [{ id: "66666666-6666-4666-8666-666666666666", farm_crop_id: FARM_CROP_ID, source: "user", created_at: new Date().toISOString(), ...b }, ...state.activities];
      return json(201, state.activities[0]);
    }
    return json(404, { error: { code: "not_found", message: "unmocked " + path } });
  });
}
