---
paths:
  - "apps/web/**"
---

# Next.js frontend

Applies only to `apps/web`. Shared KISS/YAGNI and ownership stay in `AGENTS.md` and the always-on rules.

- TypeScript throughout. Prefer the App Router file that already exists over a new folder tree.
- Default to Server Components. Add `"use client"` only for hooks, browser APIs, or event handlers.
- Fetch with `fetch` and local component state first. Do not add Redux, Zustand, React Query, SWR, or a cache library for a single request.
- Handle loading, success, and error on the screen that makes the request. The diagnostics page already shows this pattern.
- Keep API URLs on `NEXT_PUBLIC_API_BASE_URL`. The browser cannot use Compose DNS names (`http://api:8000`).
- Do not invent a UI kit, provider stack, or design-system folder until a current screen needs shared pieces used in more than one place.
- Do not put FastAPI, SQLAlchemy, or Celery logic in the web app.
