# frontend/

Next.js app (live feed, impact dashboard, chat).

## Scaffold in place

```bash
cd frontend
npx create-next-app@latest . --typescript --tailwind --app --eslint --no-src-dir --import-alias "@/*"
```

(Answer `yes` when asked to overwrite this README.)

## Dev

```bash
npm install
npm run dev    # http://localhost:3000
```

The backend CORS is set to allow `http://localhost:3000` (see `backend/main.py`).

## Pages to build

- `/` — live feed of detections (poll or subscribe to `/events` — not yet implemented)
- `/dashboard` — impact charts (calls `/tools/get_user_totals`, `/tools/calculate_climate_impact`)
- `/chat` — Gemini chat (calls `POST /chat`)

## Env

`NEXT_PUBLIC_API_URL` in `.env.local` (copy from root `.env.example`).
