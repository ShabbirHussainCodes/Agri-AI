"""The crop-table sanity report (app/agronomy/sanity_report.py). Pure tests.

The synthetic crop has Kc 0.4 -> 1.2 -> 0.6 and stages 10 / 20 / 30 / 10 days.
The expected season sums were worked out by hand:
    initial      10 days x 0.4                          =  4.0
    development  20 days, Kc 0.4 + 0.04k for k = 0..19  =  20 x 0.4 + 0.04 x 190 = 15.6
    mid          30 days x 1.2                          = 36.0
    late         10 days, Kc 1.2 - 0.06j for j = 0..9   =  10 x 1.2 - 0.06 x 45  =  9.3
    sum of Kc = 64.9 ; mean Kc = 64.9 / 70 ; at ET0 5 mm/day: 324.5 mm
"""
import json

import pytest

from app.agronomy import sanity_report as sr
from app.agronomy.crop_water import CropWaterTable, CropParams, StageDays, load_table

from .test_crop_water import GOOD_CROP, GOOD_SOIL, UNVERIFIED_SOIL

CROP = CropParams(
    name="Testcrop", kc_ini=0.4, kc_mid=1.2, kc_end=0.6,
    stage_days=StageDays(initial=10, development=20, mid=30, late=10), root_depth_m=0.5, p=0.5,
)


def table(crops=None, soils=None) -> CropWaterTable:
    return CropWaterTable.model_validate({
        "table_version": "test", "method": "test", "primary_source": "test source",
        "crops": [GOOD_CROP] if crops is None else crops,
        "soils": [GOOD_SOIL, UNVERIFIED_SOIL] if soils is None else soils,
    })


def test_season_sums_match_the_hand_computation():
    assert sr.season_kc_sum(CROP) == pytest.approx(64.9)
    assert sr.season_etc_mm(CROP, 5.0) == pytest.approx(324.5)


def test_report_for_verified_rows_shows_derived_numbers():
    text = sr.build_report(table(), 4.0)
    assert "Testcrop: season 70 days (initial 10, development 20, mid 30, late 10)" in text
    assert "mean Kc over the season 0.93" in text  # 64.9 / 70
    assert "season ETc at 4 mm/day: 260 mm" in text  # 64.9 x 4 = 259.6
    assert "loamy soil" in text and "available water 200 mm per metre" in text
    assert "Testcrop: TAW 100 mm, RAW 50 mm" in text  # 1000 x 0.2 x 0.5 ; x p 0.5
    assert "sandy soil: UNVERIFIED, skipped" in text


def test_unverified_rows_are_skipped_not_reported():
    text = sr.build_report(table(crops=[{"name_en": "Wheat", "status": "unverified"}]), 5.0)
    assert "Wheat: UNVERIFIED, skipped" in text and "Wheat: season" not in text


def test_nothing_verified_says_so():
    text = sr.build_report(table(crops=[{"name_en": "Wheat", "status": "unverified"}], soils=[UNVERIFIED_SOIL]), 4.0)
    assert "No verified rows yet" in text


def test_the_report_asserts_no_acceptable_range():
    text = sr.build_report(table(), 5.0).lower()
    assert not any(word in text for word in ("acceptable", "plausible", "normal range", "looks right"))


def test_the_shipped_table_can_be_reported_whatever_its_state():
    assert "Table crop-water-v1" in sr.build_report(load_table(), 4.0)


def test_cli_needs_et0_and_rejects_a_non_positive_one(tmp_path, capsys):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({
        "table_version": "t", "method": "t", "primary_source": "t",
        "crops": [GOOD_CROP], "soils": [GOOD_SOIL],
    }), encoding="utf-8")
    with pytest.raises(SystemExit):
        sr.main(["--table", str(path)])  # --et0 missing
    with pytest.raises(SystemExit):
        sr.main(["--table", str(path), "--et0", "0"])
    assert sr.main(["--table", str(path), "--et0", "5"]) == 0
    assert "season ETc at 5 mm/day" in capsys.readouterr().out
