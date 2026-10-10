"""Farmer-facing irrigation messages written by CODE (ADR-0015).

Used when the model's own text may not be shown: the water balance could not
be computed (`cannot_assess`), or the model's wording disagreed with the
computed verdict or used a number the evidence does not contain. The numbers
come straight from `WaterBalanceResult`, so the message is as trustworthy as
the math.

Bilingual, Hindi first then English, like the abstention messages in
app/agent/finalize.py: the app has no reliable language detection.
All amounts are in mm. The words "apply", "spray" and the Hindi dose words are
avoided on purpose, so the interim dose guard (CLAUDE.md rule 1) never
mistakes an irrigation message for a pesticide dose; tests/test_irrigation_guard.py
runs the guard over every message.

The Hindi was written without a native-speaker review (CLAUDE.md section 6 asks
for real human QA per language): have it read before a real farmer sees it.
"""
from app.agronomy import crop_water, water_balance
from app.agronomy.water_balance import WaterBalanceResult

# Reason codes owned by the tool (app/agent/tools/irrigation.py). Repeated here
# as plain strings so this module does not import the tool (which needs the
# database layer); tests/test_irrigation_guard.py keeps the two in step.
NO_LOCATION = "no_location"
NO_ACTIVE_CROP = "no_active_crop"
QUESTION_CROP_DIFFERS = "question_crop_differs"
WEATHER_UNAVAILABLE = "weather_unavailable"
# Set by the agent loop when the irrigation tool itself fails (a broken reference
# table, an unexpected exception): code knows nothing was computed, so the model
# must not improvise irrigation advice in its place.
IRRIGATION_UNAVAILABLE = "irrigation_unavailable"

_HELP_HI = "ज़्यादा जानकारी के लिए कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।"
_HELP_EN = "For more help, ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."

_ESTIMATE_HI = "यह मौसम के आँकड़ों और एक तय फ़ॉर्मूले से निकाला गया अनुमान है, आपके खेत की सीधी जाँच नहीं।"
_ESTIMATE_EN = "This is an estimate from weather data and a standard calculation, not a direct check of your field."

_WEATHER_HI = "मौसम का पूरा डेटा अभी नहीं मिल पाया, इसलिए सिंचाई का हिसाब नहीं लग सका। थोड़ी देर बाद फिर पूछें।"
_WEATHER_EN = "The weather data could not be fully retrieved, so irrigation could not be calculated. Please ask again a little later."

_UNVERIFIED_HI = "इस फसल या मिट्टी की ज़रूरी जानकारी अभी जाँची नहीं गई है, इसलिए AgriAI सिंचाई की सलाह नहीं दे रहा।"
_UNVERIFIED_EN = "The reference figures for this crop or soil have not been checked yet, so AgriAI is not giving irrigation advice."

# reason -> (Hindi, English)
_CANNOT: dict[str, tuple[str, str]] = {
    NO_LOCATION: (
        "आपके खेत की GPS लोकेशन दर्ज नहीं है, इसलिए मौसम के आधार पर सिंचाई का हिसाब नहीं लग सकता। खेत की जानकारी में लोकेशन जोड़ें।",
        "Your farm's location is not saved, so the weather-based irrigation calculation cannot be done. Add the location to your farm details.",
    ),
    NO_ACTIVE_CROP: (
        "खेत में कोई चालू फसल दर्ज नहीं है, इसलिए सिंचाई का हिसाब नहीं लग सकता। पहले फसल और बुवाई की तारीख दर्ज करें।",
        "No active crop is recorded on this farm, so irrigation cannot be calculated. Record the crop and its sowing date first.",
    ),
    QUESTION_CROP_DIFFERS: (
        "आपने जिस फसल के बारे में पूछा है वह खेत में दर्ज चालू फसल से अलग है। AgriAI अभी सिर्फ़ खेत की दर्ज फसल का हिसाब लगाता है।",
        "The crop you asked about is different from the active crop recorded on this farm. AgriAI can only calculate for the recorded crop.",
    ),
    crop_water.SOIL_MISSING: (
        "मिट्टी का प्रकार (रेतीली, दोमट या चिकनी) दर्ज नहीं है। उसे खेत की जानकारी में जोड़ें, तभी सिंचाई का हिसाब लग सकेगा।",
        "Your soil type (sandy, loamy or clayey) is not recorded. Add it to your farm details so irrigation can be calculated.",
    ),
    crop_water.CROP_NOT_SUPPORTED: (
        "इस फसल के लिए AgriAI अभी सिंचाई का हिसाब नहीं लगाता।",
        "AgriAI does not calculate irrigation for this crop yet.",
    ),
    crop_water.CROP_UNVERIFIED: (_UNVERIFIED_HI, _UNVERIFIED_EN),
    crop_water.SOIL_UNVERIFIED: (_UNVERIFIED_HI, _UNVERIFIED_EN),
    water_balance.NOT_SOWN_YET: (
        "इस फसल की बुवाई की तारीख आज से आगे की दर्ज है, इसलिए अभी सिंचाई का हिसाब नहीं लग सकता।",
        "The sowing date recorded for this crop is in the future, so irrigation cannot be calculated yet.",
    ),
    water_balance.PAST_SEASON_LENGTH: (
        "फसल की दर्ज बुवाई-तारीख के हिसाब से उसका मौसम पूरा हो चुका है, इसलिए AgriAI सिंचाई का हिसाब नहीं लगा रहा। बुवाई की तारीख जाँच लें।",
        "By the recorded sowing date the crop's season is over, so AgriAI is not calculating irrigation. Please check the sowing date.",
    ),
    water_balance.NO_WEATHER_DATA: (_WEATHER_HI, _WEATHER_EN),
    water_balance.WEATHER_GAP: (_WEATHER_HI, _WEATHER_EN),
    WEATHER_UNAVAILABLE: (_WEATHER_HI, _WEATHER_EN),
    IRRIGATION_UNAVAILABLE: (
        "सिंचाई का हिसाब अभी उपलब्ध नहीं है। थोड़ी देर बाद फिर कोशिश करें।",
        "The irrigation calculation is not available right now. Please try again later.",
    ),
    water_balance.NO_ANCHOR_IN_WINDOW: (
        "पिछले करीब तीन महीनों की मौसम जानकारी से यह तय नहीं हो सकता कि मिट्टी में कितना पानी बचा है। अपनी आख़िरी सिंचाई की तारीख दर्ज करें (मात्रा न पता हो तो सिर्फ़ तारीख), फिर पूछें।",
        "It cannot be worked out how much water is left in the soil from the last three months of weather alone. Record the date of your last irrigation (the date alone is fine if you do not know the amount), then ask again.",
    ),
}
_CANNOT_DEFAULT = (
    "इस समय सिंचाई का हिसाब नहीं लग सका।",
    "Irrigation could not be calculated right now.",
)

KNOWN_REASONS = frozenset(_CANNOT)


def _fmt(value: float) -> str:
    """50.0 -> '50', 45.3 -> '45.3'."""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _days_hi_en(n: int) -> tuple[str, str]:
    return f"{n} दिन", f"{n} day" + ("" if n == 1 else "s")


def irrigation_message(wb: WaterBalanceResult) -> str:
    """The code-authored answer for any result, computed or not."""
    if wb.verdict == "cannot_assess":
        hi, en = _CANNOT.get(wb.reason or "", _CANNOT_DEFAULT)
        return f"{hi}\n{_HELP_HI}\n\n{en}\n{_HELP_EN}"

    assert wb.depletion_mm is not None and wb.raw_mm is not None  # set whenever a verdict exists
    d, r = _fmt(wb.depletion_mm), _fmt(wb.raw_mm)
    if wb.verdict == "irrigate_now":
        hi = (
            f"अभी सिंचाई का समय है। मिट्टी में पानी की कमी {d} मिमी हो चुकी है, "
            f"जो फसल के लिए सुरक्षित सीमा ({r} मिमी) तक पहुँच गई है।"
        )
        en = (
            f"It is time to irrigate. The soil is short of {d} mm of water, "
            f"which has reached the {r} mm limit the crop can manage without stress."
        )
    else:
        hi = f"अभी सिंचाई की ज़रूरत नहीं है। मिट्टी में पानी की कमी {d} मिमी है, जबकि सुरक्षित सीमा {r} मिमी है।"
        en = f"Irrigation is not needed yet. The soil is short of {d} mm of water; the limit is {r} mm."
        if wb.days_to_raw == 0:
            hi += " आज के अंत तक यह सीमा तक पहुँचने का अनुमान है, इसलिए सिंचाई की तैयारी रखें।"
            en += " It is expected to reach the limit by the end of today, so be ready to irrigate."
        elif wb.days_to_raw is not None:
            n_hi, n_en = _days_hi_en(wb.days_to_raw)
            hi += f" अनुमान है कि लगभग {n_hi} में यह सीमा तक पहुँच जाएगी।"
            en += f" It is expected to reach the limit in about {n_en}."
        elif wb.forecast_et0_mm:
            n_hi, n_en = _days_hi_en(len(wb.forecast_et0_mm))
            hi += f" अगले {n_hi} में सीमा तक पहुँचने का अनुमान नहीं है।"
            en += f" It is not expected to reach the limit in the next {n_en}."
    return f"{hi}\n{_ESTIMATE_HI}\n\n{en}\n{_ESTIMATE_EN}"
