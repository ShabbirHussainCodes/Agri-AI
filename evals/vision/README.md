# evals/vision: the Phase 7 photo-check evaluation

**Written on 2026-10-10, before any image was classified.** Everything under "Protocol" is the rule the
numbers are judged by; it is not edited after the first result. If a result makes the rule look wrong, the
result is reported as it is and a *new* dated rule is added below the old one, with the reason.

CLAUDE.md rule 4: accuracy is a **measured output**, never a promise. The headline number is the
**cross-domain** one (field photos the model was not trained on), never the lab number printed on the model's
card (98.9 % on PlantVillage leaves). The lab number was not reproduced here and is not quoted as a result.

## What is being measured

The system under test is `rodynaemad/plant-disease-dinov2-small` (DINOv2-small backbone, frozen, with a linear
head over the 38 PlantVillage classes; int8 ONNX; licence CC-BY-SA-4.0), plus the code around it
(`apps/api/app/vision/`). Candidate order was fixed in advance (ADR-0018): this model first; a second
candidate (`onnx-community/mobilenet_v2_1.0_224-plant-disease-identification-ONNX`) is measured **only if**
this one qualifies no crop under the rule below.

## Data (all public, no login, none of it farmer data; kept out of Git in `_data/`)

| set | source | licence | role |
|---|---|---|---|
| PlantDoc `train` (2,342 photos, 27 classes with images) | github.com/pratikkayal/PlantDoc-Dataset | CC-BY-4.0 | **calibration** (in-label-space, field photos) |
| PlantDoc `test` (236 photos, 27 classes) | same | CC-BY-4.0 | **test** (in-label-space, field photos): the headline |
| rice leaves, Bangladesh field photos, 773 | HF `Project-AgML/rice_leaf_disease_classification_bd` | CC-BY-4.0 | OOD-plant (a crop the classifier has no class for): split 50/50 by a seeded shuffle into calibration and test |
| beans leaves, Uganda field photos | HF `AI-Lab-Makerere/beans` | MIT | OOD-plant: `validation` = calibration, `test` = test |
| Imagenette (10 object classes: no plants) | HF `leandrodevai/imagenette-320px-resplit` | Apache-2.0 | OOD-non-plant: `validation` = calibration, `test` = test |

PlantDoc is web-scraped photos of mixed quality, which is the point: it is what a farmer's phone is closer to
than a leaf on a white sheet. It is **not** a sample of Indian smallholder photos and says nothing about wheat,
rice, millets, cotton or pulses, for which this classifier has no class.

Exact-duplicate files (same SHA-256) that appear in both PlantDoc `train` and `test` are removed from `test`
and counted in the report. PlantDoc folder names are mapped to the model's classes in `vlabels.py`; two
mappings are approximate and flagged there (`Bell_pepper leaf spot` -> bacterial spot, `Corn leaf blight` ->
northern leaf blight).

## Protocol (the rule the numbers are judged by)

**P1. Splits.** Calibration data is used to choose the temperature, the out-of-distribution score, its
threshold, the confidence bands and the per-crop decision. Test data is used for nothing but the report.

**P2. Temperature.** Fitted on the PlantDoc-train photos by minimising negative log-likelihood, grid 0.5 to 5.0
in steps of 0.05.

**P3. The OOD score** is the one with the highest mean AUROC on calibration, over the candidates `msp`,
`max_logit`, `energy`, `feature_cosine` (centroids = mean unit feature vector per class of the PlantDoc-train
photos), where AUROC is computed for ID (PlantDoc train) against each OOD calibration set and averaged over
the three OOD sets (rice, beans, objects).

**P4. The threshold** is the one that gives the largest coverage (share of PlantDoc-train photos accepted)
subject to BOTH: selective top-1 accuracy of the accepted PlantDoc-train photos >= 0.80, and false-accept rate on
the pooled OOD calibration photos <= 0.10. If no threshold meets both, the status is reported as `target not met`
and the threshold with false-accept <= 0.10 and the best selective accuracy is used.

**P5. `min_probability` = 0.5** (fixed in advance: less than a coin flip is never presented).

**P6. Bands:** `high` calibrated top-1 probability >= 0.90, `medium` >= 0.70, `low` otherwise (still >= 0.5). Each
band reports the accuracy actually observed on accepted calibration photos and how many there were.

**P7. A crop is enabled for diagnosis only if** (a) AgriAI has the crop (`crop_scope.KNOWN_CROPS`), (b) at least
25 calibration photos of that crop were accepted at the chosen threshold, and (c) their top-1 accuracy is >= 0.80.
Otherwise the crop is disabled and the reason is written next to it. The test photos are reported per crop but
are **not** used to enable anything.

**P8. Reported on test**, each with a bootstrap 95 % interval (1,000 resamples of photos, seed 7):
top-1 and top-3 accuracy over all mapped PlantDoc-test photos with no abstention (the cross-domain accuracy),
micro and macro-by-class, and by crop; expected calibration error (15 equal-width bins) before and after the
temperature; the AUROC of every OOD score; at the chosen threshold, coverage and selective accuracy on PlantDoc
test, and the false-accept rate on each OOD test set; reliability of the bands.

**P9. The quality gate** is calibrated on PlantDoc train: thresholds are set so at most 5 % of those real field
photos are rejected, and the report gives the false-reject rate on PlantDoc test, the detection rate on
synthetic degradations of PlantDoc-test copies (Gaussian blur radius 3 and 6, darkened to 15 %, washed out, shrunk
to 120 px) and the share of non-plant photos that the gate stops.

**P10. The full pipeline** (classifier, then the vision-language model, then the agreement rule) is run on a small
stratified subset because the vision model's free tier allows a few dozen photos a day: the number of photos
and the tokens spent are reported with the result. It measures how often the second model agrees and how often the
pipeline abstains, and includes photos with printed text meant as an instruction. It does not measure a new
accuracy: agreement is not accuracy.

## Addenda (dated, made before the first photo was classified)

**A1, 2026-10-10.** Imagenette has about 1,960 photos per split. The pooled false-accept rate of P4 would have been
about 80 % easy object photos, so 400 per split are drawn by a seeded shuffle (seed 7), next to about 390 rice and about
130 bean photos in the calibration sets. Nothing had been classified when this was decided.

**A2, 2026-10-10 (written after candidate 1's calibration, before any PlantDoc TEST photo was scored).** Candidate 1,
the model's published head, failed the protocol on the calibration data: top-1 accuracy on PlantDoc train 36.8 % with no
abstention, OOD AUROC 0.52 to 0.63 for all four scores (barely better than a coin), temperature 3.55 (over-confident),
P4's target not met, **no crop qualified** under P7. That result stays in the report as measured. Because a photo check
that refuses everything is not a product, a third candidate is measured under the SAME rules P1 to P9, with these
additions, all fixed now:

- **Candidate 3** = the same frozen DINOv2 backbone (same ONNX file, `features` output) with a **new linear head
  trained on PlantDoc-train photos** (`vhead.py`). PlantDoc train is split per class by a seeded shuffle (seed 7) into
  70 % *head-train* and 30 % *calibration*; classes with fewer than 20 head-train photos get no class in the new head
  (they can never be named). The L2 strength is chosen by 5-fold cross-validated log-loss on head-train over
  {1e-4, 1e-3, 1e-2, 1e-1, 1}. The test split is not touched. P2 to P7 run on the 30 % calibration photos (and the OOD
  calibration sets); the feature-cosine centroids are built from head-train photos.
- **Near-duplicate check (new):** any PlantDoc test photo whose feature cosine to some train photo is >= 0.98 is
  flagged, and the test accuracy is reported with and without those photos, because web-scraped sets contain resized
  copies that exact hashing cannot see.
- **Candidate 2** (MobileNetV2) stays unmeasured: it needs a download the owner did not approve, and a CNN fine-tuned
  on augmented lab photos is not expected to cure a domain shift. Recorded, not hidden.
- The published-head baseline (candidate 1) and candidate 3 are reported side by side on the same test photos. The
  system ships with candidate 3 only if it qualifies a crop by P7; otherwise it ships uncalibrated for every crop.
- This changes ADR-0018's "fine-tuning on PlantDoc is post-hackathon" option: it is done here, in the smallest form
  (a linear head, ~600 KB), because candidate 1 qualified nothing. What it measures is accuracy on **PlantDoc-like web
  photos**; it is not a measurement on Indian smallholder phone photos.

## Running

From `apps/api`, with the API venv (the app's settings read `apps/api/.env`, even though no key is used): `../../.venv/bin/python ../../evals/vision/<script>.py`. Order: `vfetch.py` -> `vrun.py --degraded` -> `vquality.py` -> `vcalibrate.py` (candidate 1) -> `vhead.py` -> `vcalibrate.py --head` (candidate 3) -> `vreport.py` -> `vpipeline.py --live`. Copy candidate 1's `calibration-v1.json` to `_runs/calibration-candidate1.json` before the second `vcalibrate.py`, so the report can show both. `pip install -r evals/requirements-vision.txt` once for the parquet reader.

## Files

| file | job |
|---|---|
| `vfetch.py` | downloads the datasets and the model (asks nothing, but is only run after the owner agreed), records SHA-256 of everything in `data_manifest.json` |
| `vdata.py` | loads each set into `(path, class, split)` rows |
| `vlabels.py` | PlantDoc folder -> model class map |
| `vmetrics.py` | pure functions: ECE, AUROC, selective accuracy, bootstrap, reliability |
| `vrun.py` | runs the classifier once over every photo and caches logits and features in `_runs/` (no network, no quota) |
| `vhead.py` | A2: trains candidate 3's linear head on PlantDoc-train (70/30 split, cross-validated L2), writes `data/vision/head-v1.json` |
| `vcalibrate.py` | applies P2 to P7 (`--head` for candidate 3), writes `data/vision/calibration-v1.json` |
| `vreport.py` | applies P8 and P9, writes `evals/results/vision-<date>.md` |
| `vpipeline.py` | P10, spends Groq quota (`--live` required): the vision model against ground truth, the whole pipeline, rice photos |
| `vinjection.py` | P10 follow-up, spends Groq quota (`--live`): a printed instruction on photos that reach the answer step. Its first run had one such photo; the second was rate-limited (see the report) |

Unit tests of the pure parts: `pytest evals/tests/test_vision_metrics.py`.
