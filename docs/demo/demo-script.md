# Demo script (web v0)

About five minutes, on a phone-width browser. Say what is true: the research corpus is not
AgriAI-verified advice (ADR-0012), and the crop/soil and CIB&RC tables are unverified until a human
fills them, so the irrigation and pesticide parts show their honest "cannot" states unless the data
was filled before the demo. Claim wording: CLAUDE.md section 9.

1. **A persistent farm record.** Log in, open the farm. Point at the diary: past questions and activities
   are kept per farm, which is the first differentiator.
2. **Soil in the farmer's words.** Edit farm details: retili / domat / chikni buttons, GPS location.
3. **Ask a documented question** (for example about wheat sowing from the corpus). Show the answer card:
   advice first, then "what the documents say" with the quote, source and page, marked as not verified
   advice. This is the second differentiator: source-attributed evidence kept apart from the model's
   reasoning (collapsed).
4. **Ask "should I irrigate today?"** With the crop table filled: the "calculated by AgriAI" card (depletion,
   safe limit, Open-Meteo credit). Without it: the calm "could not calculate" answer. Say which one you are
   showing.
5. **Log "I irrigated today"** (it asks for confirmation first; nothing is written before), then ask again.
6. **Ask for a pesticide amount.** Expect an abstention that points to the pack label and the Kisan Call
   Centre (1800-180-1551), or a label card if the CIB&RC table was filled. The model never wrote a number.
7. **Switch to English** and show the same answer in the other language.
8. **If asked about limits:** daily caps exist because of the free LLM tier (10 per user, 35 total); Hindi is
   unreviewed; no voice, photo or offline yet.

Before presenting: wake the Space (open `/health/db`), confirm the keep-alive ran, and run one question
the morning of (Groq free-tier budget is about 40 questions a day for everyone).
