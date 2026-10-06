/** The body of POST /farms/{id}/ask. The UI language is added only when the switch is on
 *  (NEXT_PUBLIC_SEND_UI_LANGUAGE); without it the answer follows the language of the question. */
export function askBody(question: string, lang: "hi" | "en", sendLanguage: boolean): { question: string; language?: "hi" | "en" } {
  return sendLanguage ? { question, language: lang } : { question };
}
