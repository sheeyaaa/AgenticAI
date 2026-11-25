# TCgen frontend

Next.js dashboard for the PRD-to-Selenium agent pipeline. The overview, PRD
sample list, run submission, monitoring events, and model settings use the
FastAPI backend. Provider credentials remain server-side; enter environment
variable references in Model Configuration, never raw API keys.

## Run locally

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Run the API from the repository root in another terminal:

```powershell
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

The default API URL is `http://localhost:8000`. Set
`NEXT_PUBLIC_API_BASE_URL` in `.env.local` if the API runs elsewhere. Set
`CORS_ORIGINS` on the API server to include the frontend origin. The local API
defaults allow ports 3000 and 3001 on `localhost` and `127.0.0.1`, since Next.js
may select port 3001 when port 3000 is already occupied.

## Checks

```powershell
npm run lint
npm run typecheck
npm run build
```

The dashboard uses real backend responses and shows loading, empty, and error
states when the API is unavailable. Analytics and fabricated execution data
are intentionally omitted.
