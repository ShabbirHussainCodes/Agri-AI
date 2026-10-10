# Frontend Architecture

> Next.js (App Router) as a **PWA**. UI only — no AI logic, no business logic. Built for one shared low-end Android phone on intermittent data.

## Principles

- **Mobile-first, low cognitive load.** Important information and clear recommendations first; warnings, confidence, and sources visible but not overwhelming.
- **Voice is a primary interface, not a bonus.** Capture with `MediaRecorder` (not the browser `SpeechRecognition` API), send to the backend, and **always show the editable transcript** so a 20–30% WER world becomes a two-tap correction.
- **Show evidence types distinctly.** "What a document says" must look different from "what the model thinks"; abstention is a clear, unembarrassed state.
- **The farm timeline is the home surface**, not a chat box. Chat lives inside the timeline. This is what makes the persistent-state differentiation visible.
- **Not a developer dashboard.** No wall of KPI cards; every surfaced number must change a real decision.

## PWA specifics

- Installable, with an offline shell (service worker) so the app opens without data and queues actions.
- **Web Push (VAPID)** for reminders/alerts — free, no registration, works on Android Chrome.
- Client-side image resize before upload (protects storage/egress and speeds uploads).
- **No `localStorage` for anything that must persist reliably** across devices — that lives server-side; local storage only for lightweight per-device conveniences.

## Auth

Supabase Auth on the client manages the session; the JWT is attached to backend calls and verified server-side. The frontend never holds the service-role key.

## i18n

Hindi + English only for MVP. Language is a profile setting and a per-request hint; the UI strings live in a simple message catalogue so a third language can be added later without refactoring.

## Structure (`apps/web/`)

```
app/            routes (App Router): / (login or farm list), /farms/new, /farms/[id] (diary + ask)
components/     Shell, AuthForm, SoilPicker, LocationField, AskBox, AnswerCard (evidence cards),
                ScanBox (camera / gallery, shrinks the photo, uploads), ScanCard (top-3, band, what the AI saw,
                refusals), Diary, LogIrrigation, ProfilePanel, ui primitives
lib/            api client, generated API types, i18n catalogue (hi/en), auth context
public/         icons (a service worker does not exist yet)
tests/          Playwright e2e against a stubbed API
```

**Status (ADR-0017, 2026-10-05):** v0 is built: login, onboarding, farm diary, ask with evidence-typed
answers, "I irrigated today", profile edit. Mostly client components calling FastAPI directly with the
Supabase JWT; types generated from `openapi.json`. **Phase 7 (ADR-0018):** photo check: a camera button (`capture="environment"`) and a gallery button, the photo shrunk to 1280 px and re-encoded as JPEG on the phone (EXIF is dropped by the canvas), the result as separate cards (the agreed estimate with top-3 and a *band*, never a percentage; what the AI saw; the advice, label card and documents; the "automatic check, not an expert" note), a calm card for every refusal, feedback and delete, and scans in the farm diary with a signed-URL thumbnail. **Not built:** voice, mandi, push, offline
shell/service worker (the PWA principles above are the target, not the current state). Whether the
manifest makes a phone offer "install" is not verified.
