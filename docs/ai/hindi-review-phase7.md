# Hindi review, Phase 7: photo check (2026-10-10)

Yeh woh Hindi hai jo Phase 7 ne joda: bimari ke naam, API ke messages (jo **code** likhta hai, model nahi), aur app ke labels. **Kisi native Hindi reader ne ab tak nahi padha** (CLAUDE.md section 6). Har item ke aage `Faisla:` mein likho: `theek` ya `badlo: <tumhara Hindi>`.

Kya dekhna hai: (1) kisan ko ek baar padhne mein samajh aaye, (2) koi galat ya ajeeb shabd na ho (khaaskar bimari/keede ke naam: galat naam = galat dawa), (3) matlab English jaisa ho.

## A. Bimari ke naam (38; ye app mein English ke saath dikhte hain)

Hindi naam galat ho to kisan ek bimari ko doosri samajh sakta hai. Do naam (`अगेती झुलसा`, `पछेती झुलसा`) wahi hain jo verified pesticide label rows ke aliases mein pehle se hain. Baaki mere likhe hain. Abhi sirf maize ka photo diagnosis chalu hai, isliye pehle maize ke naam (#7 to #10) dekho.

| # | English | Hindi (abhi) | Faisla |
|---:|---|---|---|
| 0 | Apple scab | सेब का स्कैब रोग | |
| 1 | Apple black rot | सेब का ब्लैक रॉट | |
| 2 | Apple cedar rust | सेब का सीडर रतुआ | |
| 3 | Healthy apple leaf | स्वस्थ सेब की पत्ती | |
| 4 | Healthy blueberry leaf | स्वस्थ ब्लूबेरी की पत्ती | |
| 5 | Cherry powdery mildew | चेरी का चूर्णिल आसिता रोग | |
| 6 | Healthy cherry leaf | स्वस्थ चेरी की पत्ती | |
| 7 | Maize gray leaf spot | मक्का का धूसर पत्ती धब्बा रोग | |
| 8 | Maize common rust | मक्का का सामान्य रतुआ | |
| 9 | Maize northern leaf blight | मक्का का उत्तरी पर्ण झुलसा | |
| 10 | Healthy maize leaf | स्वस्थ मक्का की पत्ती | |
| 11 | Grape black rot | अंगूर का ब्लैक रॉट | |
| 12 | Grape esca (black measles) | अंगूर का एस्का (ब्लैक मीज़ल्स) | |
| 13 | Grape leaf blight | अंगूर का पर्ण झुलसा | |
| 14 | Healthy grape leaf | स्वस्थ अंगूर की पत्ती | |
| 15 | Citrus greening (HLB) | नींबू वर्गीय फलों का ग्रीनिंग रोग (HLB) | |
| 16 | Peach bacterial spot | आड़ू का जीवाणु धब्बा रोग | |
| 17 | Healthy peach leaf | स्वस्थ आड़ू की पत्ती | |
| 18 | Bell pepper bacterial spot | शिमला मिर्च का जीवाणु धब्बा रोग | |
| 19 | Healthy bell pepper leaf | स्वस्थ शिमला मिर्च की पत्ती | |
| 20 | Potato early blight | आलू का अगेती झुलसा | |
| 21 | Potato late blight | आलू का पछेती झुलसा | |
| 22 | Healthy potato leaf | स्वस्थ आलू की पत्ती | |
| 23 | Healthy raspberry leaf | स्वस्थ रसभरी की पत्ती | |
| 24 | Healthy soybean leaf | स्वस्थ सोयाबीन की पत्ती | |
| 25 | Squash powdery mildew | कद्दू वर्गीय फसल का चूर्णिल आसिता रोग | |
| 26 | Strawberry leaf scorch | स्ट्रॉबेरी का पर्ण झुलसा | |
| 27 | Healthy strawberry leaf | स्वस्थ स्ट्रॉबेरी की पत्ती | |
| 28 | Tomato bacterial spot | टमाटर का जीवाणु धब्बा रोग | |
| 29 | Tomato early blight | टमाटर का अगेती झुलसा | |
| 30 | Tomato late blight | टमाटर का पछेती झुलसा | |
| 31 | Tomato leaf mold | टमाटर का पर्ण फफूंद (लीफ मोल्ड) | |
| 32 | Tomato Septoria leaf spot | टमाटर का सेप्टोरिया पत्ती धब्बा रोग | |
| 33 | Tomato spider mites | टमाटर में मकड़ी कीट (स्पाइडर माइट) | |
| 34 | Tomato target spot | टमाटर का टारगेट स्पॉट रोग | |
| 35 | Tomato yellow leaf curl virus | टमाटर का पीला पत्ती मरोड़ विषाणु | |
| 36 | Tomato mosaic virus | टमाटर का मोज़ेक विषाणु रोग | |
| 37 | Healthy tomato leaf | स्वस्थ टमाटर की पत्ती | |

## B. API ke messages (`apps/api/app/vision/messages.py`)

### 1. Photo quality: too_small

**Hindi:**

> फोटो बहुत छोटी है। पत्ती के थोड़ा पास जाकर दोबारा फोटो लें।

**English:**

> The photo is too small. Move a little closer to the leaf and take it again.

**Faisla:**

### 2. Photo quality: too_blurry

**Hindi:**

> फोटो धुंधली है। फोन को स्थिर पकड़ें, कैमरे को पत्ती पर फोकस होने दें और दोबारा फोटो लें।

**English:**

> The photo is blurry. Hold the phone steady, let the camera focus on the leaf, and take it again.

**Faisla:**

### 3. Photo quality: too_dark

**Hindi:**

> फोटो में रोशनी बहुत कम है। दिन की रोशनी में, छाया से हटकर दोबारा फोटो लें।

**English:**

> The photo is too dark. Take it again in daylight, away from the shade.

**Faisla:**

### 4. Photo quality: too_bright

**Hindi:**

> फोटो में रोशनी बहुत तेज़ है। सीधी चमकती धूप से बचकर दोबारा फोटो लें।

**English:**

> The photo is too bright. Take it again without strong glare from direct sun.

**Faisla:**

### 5. Photo quality: no_vegetation

**Hindi:**

> इस फोटो में पौधे की पत्ती नहीं दिख रही। एक पत्ती की पास से साफ़ फोटो लें।

**English:**

> No plant leaf could be seen in this photo. Take a clear close-up of one leaf.

**Faisla:**

### 6. Bimari nahi batayi: out_of_distribution

**Hindi:**

> यह फोटो ऐसी नहीं लग रही जिसे AgriAI पहचान सके, इसलिए यह कोई बीमारी नहीं बता रहा। एक पत्ती की साफ़, पास से ली गई फोटो आज़माएँ। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> This does not look like something AgriAI can identify, so it is not naming a disease. You can try a clear close-up of one leaf. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 7. Bimari nahi batayi: low_confidence

**Hindi:**

> AgriAI इस फोटो पर पक्का नहीं है, इसलिए कोई बीमारी नहीं बता रहा। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> AgriAI is not sure about this photo, so it is not naming a disease. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 8. Bimari nahi batayi: crop_not_supported

**Hindi:**

> AgriAI अभी इस फसल की पत्ती की जाँच नहीं करता, इसलिए कोई बीमारी नहीं बता रहा। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> AgriAI does not check leaves of this crop yet, so it is not naming a disease. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 9. Bimari nahi batayi: crop_not_validated

**Hindi:**

> इस फसल के लिए फोटो-जाँच को खेत की असली फोटो पर अभी परखा नहीं गया है, इसलिए AgriAI कोई बीमारी नहीं बता रहा। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> The photo check has not yet been tested on real field photos of this crop, so AgriAI is not naming a disease. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 10. Bimari nahi batayi: model_disagreement

**Hindi:**

> AgriAI की दो अलग जाँचें इस फोटो पर एक जैसा जवाब नहीं दे रहीं, इसलिए कोई बीमारी नहीं बता रहा। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> AgriAI's two separate checks do not agree about this photo, so it is not naming a disease. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 11. Bimari nahi batayi: not_a_plant_photo

**Hindi:**

> इस फोटो में पौधा नहीं दिख रहा, इसलिए AgriAI कोई बीमारी नहीं बता रहा। एक पत्ती की पास से साफ़ फोटो लें। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> No plant can be seen in this photo, so AgriAI is not naming a disease. Take a clear close-up of one leaf. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 12. Bimari nahi batayi: vision_unavailable

**Hindi:**

> फोटो की दूसरी जाँच अभी नहीं हो पाई, इसलिए AgriAI कोई बीमारी नहीं बता रहा। थोड़ी देर बाद दोबारा कोशिश करें। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> The second check of the photo could not run just now, so AgriAI is not naming a disease. Please try again in a little while. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 13. Bimari nahi batayi: vision_not_calibrated

**Hindi:**

> फोटो-जाँच अभी इस्तेमाल के लिए तैयार नहीं है, इसलिए AgriAI कोई बीमारी नहीं बता रहा। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> The photo check is not ready for use yet, so AgriAI is not naming a disease. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 14. Photo doosri fasal ki (namuna: farm mein Rice)

**Hindi:**

> यह फोटो आपके खेत की दर्ज फसल (Rice) की नहीं लग रही, इसलिए AgriAI कोई बीमारी नहीं बता रहा। अगर आप दूसरी फसल भी उगाते हैं, तो पहले उसे खेत में जोड़िए। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> This photo does not look like the crop recorded for your farm (Rice), so AgriAI is not naming a disease. If you also grow another crop, add it to your farm first. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 15. Upload error: empty_upload

**Hindi:**

> कोई फोटो नहीं मिली। कृपया फोटो चुनें।

**English:**

> No photo was received. Please choose a photo.

**Faisla:**

### 16. Upload error: file_too_large

**Hindi:**

> फोटो बहुत बड़ी है (8 MB से कम होनी चाहिए)। कृपया छोटी फोटो भेजें।

**English:**

> The photo is too large (it must be under 8 MB). Please send a smaller one.

**Faisla:**

### 17. Upload error: unsupported_image_type

**Hindi:**

> यह फोटो का प्रकार काम नहीं करता। कृपया JPEG, PNG या WebP फोटो भेजें।

**English:**

> This kind of file cannot be used. Please send a JPEG, PNG or WebP photo.

**Faisla:**

### 18. Upload error: image_too_large

**Hindi:**

> फोटो का आकार बहुत बड़ा है। कृपया फोन के कैमरे की सामान्य फोटो भेजें।

**English:**

> The photo's dimensions are too large. Please send a normal phone-camera photo.

**Faisla:**

### 19. Upload error: unreadable_image

**Hindi:**

> यह फोटो खुल नहीं पाई। कृपया दूसरी फोटो भेजें।

**English:**

> This photo could not be opened. Please send another one.

**Faisla:**

### 20. Roz ki seema: user

**Hindi:**

> आज के लिए आपकी फोटो-जाँच की सीमा पूरी हो गई है। कल फिर कोशिश करें। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> You have used today's photo checks. Please try again tomorrow. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 21. Roz ki seema: global

**Hindi:**

> AgriAI आज बहुत ज़्यादा इस्तेमाल हो चुका है और अभी और फोटो नहीं ले पा रहा। कल फिर कोशिश करें। कृपया अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> AgriAI has reached its limit for today and cannot take more photos. Please try again tomorrow. Please ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 22. Har diagnosis ke saath note

**Hindi:**

> यह फोटो से की गई अपने-आप वाली जाँच है, किसी विशेषज्ञ की पुष्टि नहीं। दवा छिड़कने से पहले अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पक्का कर लें।

**English:**

> This is an automatic check from a photo, not an expert's confirmation. Before spraying anything, confirm with your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

### 23. Koi dastavez use nahi hua

**Hindi:**

> इस जवाब में किसी जाँचे हुए दस्तावेज़ का इस्तेमाल नहीं हुआ; यह सिर्फ़ फोटो की स्वचालित जाँच पर आधारित है। इलाज के लिए अपने कृषि विज्ञान केंद्र (KVK) या किसान कॉल सेंटर (1800-180-1551) से पूछें।

**English:**

> No verified document was used for this answer; it rests only on the automatic photo check. For treatment, ask your Krishi Vigyan Kendra (KVK) or the Kisan Call Centre (1800-180-1551).

**Faisla:**

## C. App ke labels (`apps/web/lib/messages.ts`, `scan*`, `band*`, `takePhoto`, ...)

| key | Hindi (abhi) | English | Faisla |
|---|---|---|---|
| `scanTitle` | 📷 फोटो से जाँच | 📷 Check a photo | |
| `takePhoto` | 📷 फोटो लें | 📷 Take a photo | |
| `choosePhoto` | 🖼️ गैलरी से चुनें | 🖼️ Choose from gallery | |
| `checkPhoto` | फोटो जाँचें | Check this photo | |
| `checking` | AgriAI फोटो देख रहा है… | AgriAI is looking at the photo… | |
| `anotherPhoto` | दूसरी फोटो | Another photo | |
| `photoAlt` | आपकी भेजी फोटो | Your photo | |
| `scanFailed` | फोटो की जाँच अभी नहीं हो पाई। थोड़ी देर बाद फिर कोशिश कीजिए। | The photo could not be checked right now. Please try again in a little while. | |
| `scanRetakeTitle` | दोबारा फोटो लीजिए | Please take the photo again | |
| `scanNoNameTitle` | AgriAI बीमारी नहीं बता रहा | AgriAI is not naming a disease | |
| `scanLikelyTitle` | फोटो से अनुमान | Estimate from the photo | |
| `scanSecondCheck` | दूसरी, अलग जाँच भी यही कहती है | A second, separate check says the same | |
| `scanOthers` | और भी हो सकता है | It could also be | |
| `scanConfidence` | सबूत कितना मज़बूत | How strong the evidence is | |
| `bandHigh` | ऊँचा | High | |
| `bandMedium` | मध्यम | Medium | |
| `bandLow` | कम | Low | |
| `scanSawTitle` | फोटो में AI ने क्या देखा | What the AI saw in the photo | |
| `scanFeedbackAsk` | क्या यह अनुमान सही लगा? | Did this estimate look right? | |
| `scanFeedbackYes` | हाँ, सही | Yes, right | |
| `scanFeedbackNo` | नहीं, गलत | No, wrong | |
| `scanFeedbackThanks` | धन्यवाद, आपकी राय दर्ज हो गई। | Thank you, your answer is saved. | |
| `scanDelete` | यह जाँच और फोटो हटाएँ | Delete this check and photo | |
| `scanDeleteSure` | पक्का हटाएँ? | Delete for sure? | |
| `scanLabel` | फोटो की जाँच | Photo check | |
| `scanOutcomeDiagnosis` | अनुमान मिला | Estimate given | |
| `scanOutcomeAbstained` | बीमारी नहीं बताई | No disease named | |
| `scanHelp` | पत्ती की एक साफ़, पास से ली गई फोटो लें। AgriAI फोटो से अनुमान लगाता है, पक्का निदान नहीं देता। | Take one clear, close photo of a leaf. AgriAI estimates from the photo; it does not give a certain diagnosis. | |
| `bandMeasured` | हमारे परीक्षण में, इस स्तर के जवाब {n} फोटो में से {pct}% बार सही निकले ({source})। आपकी फोटो पर यह अलग हो सकता है। | In our tests, answers at this level were right {pct}% of the time on {n} photos ({source}). On your photo it may differ. | |
