"""Farmer-facing text for the photo check, written entirely by code (never by a model).

Same convention as app/agent/finalize.py: ONE string per message, Hindi paragraph first, a blank line,
then English, because the app cannot tell which language a farmer reads; the web app shows the half that
matches the chosen language (apps/web/lib/text.ts). A refusal always says what to do next, and the
people to ask are the KVK and the Kisan Call Centre (1800-180-1551).

The Hindi wording has had no native-speaker review (CLAUDE.md section 6).
"""
from app.vision import decision, imaging, quality

_ASK = "कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।"
_ASK_EN = "Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551)."


def _both(hi: str, en: str) -> str:
    return f"{hi}\n\n{en}"


QUALITY_TIPS: dict[str, str] = {
    quality.TOO_SMALL: _both(
        "फोटो बहुत छोटी है। पत्ती के थोड़ा पास जाकर दोबारा फोटो लें।",
        "The photo is too small. Move a little closer to the leaf and take it again.",
    ),
    quality.TOO_BLURRY: _both(
        "फोटो धुंधली है। फोन को स्थिर पकड़ें, कैमरे को पत्ती पर फोकस होने दें और दोबारा फोटो लें।",
        "The photo is blurry. Hold the phone steady, let the camera focus on the leaf, and take it again.",
    ),
    quality.TOO_DARK: _both(
        "फोटो में रोशनी बहुत कम है। दिन की रोशनी में, छाया से हटकर दोबारा फोटो लें।",
        "The photo is too dark. Take it again in daylight, away from the shade.",
    ),
    quality.TOO_BRIGHT: _both(
        "फोटो में रोशनी बहुत तेज़ है। सीधी चमकती धूप से बचकर दोबारा फोटो लें।",
        "The photo is too bright. Take it again without strong glare from direct sun.",
    ),
    quality.NO_VEGETATION: _both(
        "इस फोटो में पौधे की पत्ती नहीं दिख रही। एक पत्ती की पास से साफ़ फोटो लें।",
        "No plant leaf could be seen in this photo. Take a clear close-up of one leaf.",
    ),
}


def quality_message(reasons: tuple[str, ...] | list[str]) -> str:
    """The retake tip for the first failed check (the most useful one); the rest are in the report."""
    for reason in reasons:
        if reason in QUALITY_TIPS:
            return QUALITY_TIPS[reason]
    return _both("फोटो साफ़ नहीं है। दोबारा फोटो लें।", "The photo is not clear enough. Please take it again.")


ABSTAIN_MESSAGES: dict[str, str] = {
    decision.OUT_OF_DISTRIBUTION: _both(
        f"यह फोटो ऐसी नहीं लग रही जिसे AgriAI पहचान सके, इसलिए यह कोई बीमारी नहीं बता रहा। एक पत्ती की साफ़, पास से ली गई फोटो आज़माएँ। {_ASK}",
        f"This does not look like something AgriAI can identify, so it is not naming a disease. You can try a clear close-up of one leaf. {_ASK_EN}",
    ),
    decision.LOW_CONFIDENCE: _both(
        f"AgriAI इस फोटो पर पक्का नहीं है, इसलिए कोई बीमारी नहीं बता रहा। {_ASK}",
        f"AgriAI is not sure about this photo, so it is not naming a disease. {_ASK_EN}",
    ),
    decision.CROP_NOT_SUPPORTED: _both(
        f"AgriAI अभी इस फसल की पत्ती की जाँच नहीं करता, इसलिए कोई बीमारी नहीं बता रहा। {_ASK}",
        f"AgriAI does not check leaves of this crop yet, so it is not naming a disease. {_ASK_EN}",
    ),
    decision.CROP_NOT_VALIDATED: _both(
        f"इस फसल के लिए फोटो-जाँच को खेत की असली फोटो पर अभी परखा नहीं गया है, इसलिए AgriAI कोई बीमारी नहीं बता रहा। {_ASK}",
        f"The photo check has not yet been tested on real field photos of this crop, so AgriAI is not naming a disease. {_ASK_EN}",
    ),
    decision.MODEL_DISAGREEMENT: _both(
        f"AgriAI की दो अलग जाँचें इस फोटो पर एक जैसा जवाब नहीं दे रहीं, इसलिए कोई बीमारी नहीं बता रहा। {_ASK}",
        f"AgriAI's two separate checks do not agree about this photo, so it is not naming a disease. {_ASK_EN}",
    ),
    decision.NOT_A_PLANT_PHOTO: _both(
        f"इस फोटो में पौधा नहीं दिख रहा, इसलिए AgriAI कोई बीमारी नहीं बता रहा। एक पत्ती की पास से साफ़ फोटो लें। {_ASK}",
        f"No plant can be seen in this photo, so AgriAI is not naming a disease. Take a clear close-up of one leaf. {_ASK_EN}",
    ),
    decision.VISION_UNAVAILABLE: _both(
        f"फोटो की दूसरी जाँच अभी नहीं हो पाई, इसलिए AgriAI कोई बीमारी नहीं बता रहा। थोड़ी देर बाद दोबारा कोशिश करें। {_ASK}",
        f"The second check of the photo could not run just now, so AgriAI is not naming a disease. Please try again in a little while. {_ASK_EN}",
    ),
    decision.VISION_NOT_CALIBRATED: _both(
        f"फोटो-जाँच अभी इस्तेमाल के लिए तैयार नहीं है, इसलिए AgriAI कोई बीमारी नहीं बता रहा। {_ASK}",
        f"The photo check is not ready for use yet, so AgriAI is not naming a disease. {_ASK_EN}",
    ),
}

UPLOAD_ERRORS: dict[str, tuple[int, str]] = {
    imaging.REASON_EMPTY: (400, _both("कोई फोटो नहीं मिली। कृपया फोटो चुनें।", "No photo was received. Please choose a photo.")),
    imaging.REASON_TOO_LARGE: (
        413,
        _both("फोटो बहुत बड़ी है (8 MB से कम होनी चाहिए)। कृपया छोटी फोटो भेजें।", "The photo is too large (it must be under 8 MB). Please send a smaller one."),
    ),
    imaging.REASON_UNSUPPORTED: (
        415,
        _both("यह फोटो का प्रकार काम नहीं करता। कृपया JPEG, PNG या WebP फोटो भेजें।", "This kind of file cannot be used. Please send a JPEG, PNG or WebP photo."),
    ),
    imaging.REASON_TOO_MANY_PIXELS: (
        413,
        _both("फोटो का आकार बहुत बड़ा है। कृपया फोन के कैमरे की सामान्य फोटो भेजें।", "The photo's dimensions are too large. Please send a normal phone-camera photo."),
    ),
    imaging.REASON_UNREADABLE: (
        422,
        _both("यह फोटो खुल नहीं पाई। कृपया दूसरी फोटो भेजें।", "This photo could not be opened. Please send another one."),
    ),
}

SCAN_LIMIT_MESSAGE = {
    "user": _both(
        f"आज के लिए आपकी फोटो-जाँच की सीमा पूरी हो गई है। कल फिर कोशिश करें। {_ASK}",
        f"You have used today's photo checks. Please try again tomorrow. {_ASK_EN}",
    ),
    "global": _both(
        f"AgriAI आज बहुत ज़्यादा इस्तेमाल हो चुका है और अभी और फोटो नहीं ले पा रहा। कल फिर कोशिश करें। {_ASK}",
        f"AgriAI has reached its limit for today and cannot take more photos. Please try again tomorrow. {_ASK_EN}",
    ),
}

# Always attached to a diagnosis, so the card cannot be read as a lab result.
DIAGNOSIS_NOTE = _both(
    "यह फोटो से की गई अपने-आप वाली जाँच है, किसी विशेषज्ञ की पुष्टि नहीं। दवा छिड़कने से पहले अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पक्का कर लें।",
    "This is an automatic check from a photo, not an expert's confirmation. Before spraying anything, confirm with your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).",
)


def crop_differs_refusal(farm_crop_en: str) -> str:
    """Shown when the photo looks like another crop than the farm record's. The farm's crop name is the record's own."""
    return _both(
        f"यह फोटो आपके खेत की दर्ज फसल ({farm_crop_en}) की नहीं लग रही, इसलिए AgriAI कोई बीमारी नहीं बता रहा। अगर आप दूसरी फसल भी उगाते हैं, तो पहले उसे खेत में जोड़िए। {_ASK}",
        f"This photo does not look like the crop recorded for your farm ({farm_crop_en}), so AgriAI is not naming a disease. If you also grow another crop, add it to your farm first. {_ASK_EN}",
    )
