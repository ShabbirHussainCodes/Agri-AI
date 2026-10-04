// Types come from the API's OpenAPI document (npm run gen:types), never written by hand,
// so the browser cannot drift from the contract (ADR-0017).
import type { components } from "./api-types";

type S = components["schemas"];
export type Farm = S["Farm"];
export type FarmCreate = S["FarmCreate"];
export type FarmUpdate = S["FarmUpdate"];
export type Crop = S["Crop"];
export type FarmCrop = S["FarmCrop"];
export type Activity = S["Activity"];
export type ActivityCreate = S["ActivityCreate"];
export type AdvisoryResponse = S["AdvisoryResponse"];
export type AdvisoryRecord = S["AdvisoryRecord"];
export type WaterBalance = S["WaterBalanceResult"];
export type LabelEntry = S["LabelEntry"];
export type EvidenceItem = S["EvidenceItem"];

export type SoilTexture = "sandy" | "loamy" | "clayey";
