const DEVANAGARI = /[ऀ-ॿ]/;

/** The backend writes its own messages as a Hindi paragraph, a blank line, then an
 *  English paragraph (one string, because it cannot know the farmer's language).
 *  If the text has exactly that shape, show the half the farmer chose; anything
 *  else (the model's own answer, a single paragraph) is shown whole. */
export function pickLanguage(text: string, lang: "hi" | "en"): string {
  const parts = text.split(/\n\s*\n/);
  if (parts.length === 2 && DEVANAGARI.test(parts[0]) && !DEVANAGARI.test(parts[1])) {
    return (lang === "hi" ? parts[0] : parts[1]).trim();
  }
  return text;
}
