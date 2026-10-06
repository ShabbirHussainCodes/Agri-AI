# Fill checklist: demo set (Wheat + loamy soil, optional Tomato)

Companion to `README.md` in this folder. **No value is given here on purpose.** Every number is read by a
person from the FAO-56 document itself and typed into `crop-water-v1.json`, with the row you used written
in `sources`.

Source: Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998), *Crop evapotranspiration: guidelines for
computing crop water requirements*, FAO Irrigation and Drainage Paper No. 56.

**Confidence note.** The table numbers (11, 12, 19, 22) and column names below are from memory and from
the earlier README, not from a document read in this session (FAO hosts were not reachable). Open the PDF,
confirm each table number and title on the page, and fix this file if one is wrong.

## Why this set
- **Wheat** is the crop of the test farm and the most common rabi crop. With **loamy** soil the existing
  test farm gets a complete irrigation answer.
- **Tomato** (optional) is the only crop with a curated document in the corpus (`crops_covered`), so a demo
  can show a calculated card and a document card for the same crop.
- Rows left `unverified` stay fail-closed: sandy and clayey soils, maize, and every crop not listed keep
  answering `cannot_assess`. Nothing else has to be filled for the demo.

## A. Crop rows (one block per crop; JSON fields in `crops[]`)

| JSON field | FAO-56 table | Row to look for | Column | Unit | Traps |
|---|---|---|---|---|---|
| `kc_ini`, `kc_mid`, `kc_end` | Table 12, single (time-averaged) crop coefficients | Wheat: the **winter wheat** row for non-frozen soils if the table splits it, else the closest winter/spring row; say which in `notes`. Tomato: the Solanum-family group, row "Tomato" | `Kc ini`, `Kc mid`, `Kc end` | dimensionless | Read the table footnotes. For some crops `Kc end` differs by how the crop is harvested (fresh vs dry); pick the one that matches Indian practice for that crop and write it in `notes`. Table 12 `Kc ini` is an approximation; the document gives wetting-based values elsewhere. v1 uses the table value and does not adjust `kc_mid` / `kc_end` for climate: write that in `notes`. |
| `stage_days.initial/development/mid/late` | Table 11, lengths of crop development stages | Same crop; **choose the planting date and region closest to the farm** (for rabi wheat, a November sowing in a warm region) | `L ini`, `L dev`, `L mid`, `L late` | days | The table lists several rows per crop (region, planting date). Do **not** average rows. If none is close to the farm, ask a KVK or agronomist. Put the exact row in `stage_length_basis`. The four values are days from sowing, as the engine expects. |
| `root_depth_m` | Table 22, maximum effective rooting depth and depletion fraction | Same crop (wheat may be split by winter / spring) | `Maximum root depth` | m | The table gives a **range**. Policy (README, ADR-0015): take the **lower end**, so the alert comes earlier, not later. Write "lower end of range a-b" in `notes`. |
| `p` | Table 22 | Same row as the root depth | `Depletion fraction p` (for ETc about 5 mm/day) | fraction, 0 to 1 | v1 does not correct p for other ETc rates. Write that in `notes`. |

`sources` for each crop needs these four keys, with free text naming the table, the row and the date you
read it: `kc`, `stage_days`, `root_depth_m`, `p`. Also set `status` to `"verified"`, `verified_by` (your
name) and `verified_on` (`YYYY-MM-DD`).

## B. Soil row (`soils[]`, texture `loamy`; repeat for sandy and clayey later if wanted)

| JSON field | FAO-56 table | Row to look for | Column | Unit | Traps |
|---|---|---|---|---|---|
| `fao56_class` | Table 19, typical soil water characteristics for different soil types | The USDA texture class you judge to match the farmer's word. For `domat` (loamy) the natural candidate is the row named **Loam**; for `retili` and `chikni / kali` the match is a judgement (several rows could fit): decide with a KVK or agronomist and write the class you chose | Soil type | text | Mapping a farmer's word to a texture class is itself an agronomic judgement. Record it. |
| `theta_fc` | Table 19 | the chosen row | Field capacity, `θFC` | m3/m3 (volumetric) | The table gives ranges. |
| `theta_wp` | Table 19 | the chosen row | Wilting point, `θWP` | m3/m3 | The table gives ranges. |

The README policy says "lower end of the available-water range". Because the table gives separate ranges
for `θFC` and `θWP`, make the rule explicit and repeatable: choose `theta_fc` and `theta_wp` inside their
ranges so that `theta_fc - theta_wp` equals the **low end of the table's `θFC − θWP` column**, and write the
pair and the rule in `notes`. Check that both values stay inside their own ranges; if they do not, say so in
`notes` rather than silently moving a value. `sources` key for a soil: `theta`.

## C. After typing the numbers

1. `cd apps/api && pytest tests/test_crop_water.py`. It loads the shipped file and rejects a verified row
   with a missing value, an out-of-range value, `kc_mid` below `kc_ini` / `kc_end`, or `theta_fc` at or below
   `theta_wp`.
2. Sanity check (ADR-0012), with the mean ET0 of the farm and season from Open-Meteo's
   `et0_fao_evapotranspiration`:
   `python -m app.agronomy.sanity_report --et0 <mm/day>`
   It prints season length, mean Kc, season ETc, and TAW / RAW per soil. Compare season ETc and TAW with a
   published figure for the same crop and region **that you choose and cite in `notes`**. This repository
   ships no acceptable range on purpose.
3. If a result looks wrong, the row is wrong. Do not nudge a value: write what you changed and why.
4. The API reads the file once per process, and the deployed image **bakes `data/` in**. After the file
   changes, rebuild and redeploy: `python deploy/hf-space/make_bundle.py <folder>` then the same
   `gcloud run deploy ...` command as the first deploy (`docs/deployment/deployment.md`).
5. Live check on the test farm (loamy, wheat): ask "Should I irrigate my wheat today?". It should now return
   a "calculated by AgriAI" card instead of "could not calculate". Check by hand, from the numbers in the
   card's "how this was worked out", that the depletion and the limit follow from the table values you typed.
