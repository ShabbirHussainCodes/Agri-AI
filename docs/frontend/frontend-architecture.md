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
app/            routes (App Router)
components/      UI components (timeline, ask, scan, onboarding, evidence card)
public/          manifest, service worker, icons
```
