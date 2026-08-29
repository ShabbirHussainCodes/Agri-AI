# External Integrations

> All external calls go through typed, cached clients in `app/integrations/`. Attribution obligations are honoured. Verify anything marked ⚠️ before it hardens.

| Integration | Access | Status / rules |
|---|---|---|
| **Open-Meteo** (forecast + historical + soil + ET₀) | No key. 10,000 calls/day, 5,000/hr, 600/min. Data CC-BY-4.0 | ✅ Core. Native soil moisture (5 layers), soil temp (4 depths), FAO-56 ET₀ — real irrigation inputs. Commercial use needs a paid plan. Attribute Open-Meteo. |
| **data.gov.in mandi prices** | Own free API key. GODL-India | ✅ Modular/secondary. Live-verified resource. Register your OWN key; don't reuse demo keys. GODL attribution required. |
| **SoilGrids (ISRIC)** | Public REST, 250 m grids | ⚠️ Licence + rate limits not confirmed from a fetched page — check `docs.isric.org` before shipping. |
| **Soil Health Card** | — | ❌ No public API. Modelled as **farmer-entered** N/P/K/pH on the farm profile. |
| **Nominatim (OSM)** | No key. ≤1 req/sec, valid User-Agent, caching mandatory, autocomplete forbidden | ✅ Geocode **once** at farm registration, store lat/lon, never geocode again. ODbL attribution. |
| **Bhuvan / NRSC** | Token (daily expiry) | Optional — Indian village-level geocoding; operational tax from the daily token. |
| **IMD official** | Key + IP whitelist + login | Skip as a data backbone (unusable from free serverless); cite as credibility only. |
| **Agmarknet scraping** | — | Skip (403/bot-blocked). Use the data.gov.in API for the same data, legitimately licensed. |
| **eNAM** | — | Skip (no public developer API found). |
| **Bhashini** (ASR/TTS/MT) | ULCA registration, ≤5 keys | Optional, **PoC-only licence** — fine for a demo, not production. Keep behind the provider interface; AI4Bharat MIT models are the production path. |
| **WhatsApp Cloud API** | Meta test WABA + test number | Optional, demo only. Real users need business verification — say so honestly in docs. |
| **Telegram Bot API** | Free | Optional — proves the notification-adapter abstraction at zero cost. |

## Client rules

- Typed request/response models; explicit timeouts; graceful degradation on failure (cached value or honest "unavailable").
- Cache: weather per (lat, lon, hour); geocode results permanently; mandi via scheduled ingest into `mandi_prices`.
- Never send secrets to the frontend; all keyed calls are server-side.
- Attribution strings for CC-BY (Open-Meteo) and GODL (data.gov.in) are rendered where the data is shown.
