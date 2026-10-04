"""A report to help a human sanity-check the crop/soil table (ADR-0012, ADR-0015).

Reading numbers out of FAO-56 is not enough: a transcription slip or a wrong row
(sweet corn for maize) still produces a table that loads and passes the range
checks. What exposes it is what the numbers IMPLY: a season's water use, a
soil's available water. This prints those, for every VERIFIED row, so the
reviewer can set them against a published figure for the same crop and region.

It prints derived numbers and the formula behind them. It does not say whether
they are right: no acceptable range is shipped, because inventing one would be
exactly the unsourced number this table exists to avoid.

    cd apps/api
    python -m app.agronomy.sanity_report --et0 <mean ET0 in mm/day for the sowing season>
    python -m app.agronomy.sanity_report --et0 4.5 --table /path/to/other-table.json

`--et0` has no default on purpose. Take it from the weather of the farm and
season you are checking (Open-Meteo's `et0_fao_evapotranspiration`, averaged);
a made-up typical value would make the output look more authoritative than it is.
"""
import argparse
import sys
from pathlib import Path

from app.agronomy import crop_water
from app.agronomy.crop_water import CropParams, CropWaterTable
from app.agronomy.water_balance import kc_and_stage, taw_mm


def season_kc_sum(crop: CropParams) -> float:
    """Sum of the daily Kc over the whole season (day 0 to the last day)."""
    total = 0.0
    for day in range(crop.stage_days.total):
        kc_stage = kc_and_stage(crop, day)
        assert kc_stage is not None  # every day inside the season has a Kc
        total += kc_stage[0]
    return total


def season_etc_mm(crop: CropParams, et0_mm_per_day: float) -> float:
    """Season water use if every day had the same ET0 and the soil never limited it:
    sum over days of Kc x ET0."""
    return season_kc_sum(crop) * et0_mm_per_day


def build_report(table: CropWaterTable, et0_mm_per_day: float) -> str:
    lines = [
        f"Table {table.table_version} ({table.primary_source})",
        f"Season ETc below = sum of daily Kc x {et0_mm_per_day:g} mm/day ET0, no water stress.",
        "Compare it with a published seasonal water requirement for the same crop and region.",
        "",
    ]
    crops: list[CropParams] = []
    for row in table.crops:
        if row.status != "verified":
            lines.append(f"{row.name_en}: UNVERIFIED, skipped")
            continue
        crop = row.to_params()
        crops.append(crop)
        s = crop.stage_days
        kc_sum = season_kc_sum(crop)
        lines += [
            f"{crop.name}: season {s.total} days (initial {s.initial}, development {s.development}, mid {s.mid}, late {s.late}); "
            f"stage lengths basis: {row.stage_length_basis}",
            f"  Kc {crop.kc_ini:g} -> {crop.kc_mid:g} -> {crop.kc_end:g}; mean Kc over the season {kc_sum / s.total:.2f}",
            f"  season ETc at {et0_mm_per_day:g} mm/day: {kc_sum * et0_mm_per_day:.0f} mm",
            f"  root depth {crop.root_depth_m:g} m, depletion fraction p {crop.p:g}",
        ]

    soils = [(row, row.to_params()) for row in table.soils if row.status == "verified"]
    lines.append("")
    for row in table.soils:
        if row.status != "verified":
            lines.append(f"{row.texture} soil: UNVERIFIED, skipped")
    for row, soil in soils:
        lines.append(
            f"{soil.texture} soil (FAO-56 class: {row.fao56_class}): theta_fc {soil.theta_fc:g}, "
            f"theta_wp {soil.theta_wp:g}, available water {1000 * (soil.theta_fc - soil.theta_wp):.0f} mm per metre"
        )
        for crop in crops:
            taw = taw_mm(soil, crop)
            lines.append(f"  {crop.name}: TAW {taw:.0f} mm, RAW {crop.p * taw:.0f} mm")

    if not crops and not soils:
        lines.append("No verified rows yet: nothing to report. See data/crop_water/README.md.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--et0", type=float, required=True, help="mean daily ET0 in mm/day for the season being checked")
    ap.add_argument("--table", type=Path, help="table file (default: data/crop_water/crop-water-v1.json)")
    args = ap.parse_args(argv)
    if args.et0 <= 0:
        ap.error("--et0 must be positive")
    sys.stdout.write(build_report(crop_water.load_table(args.table), args.et0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
