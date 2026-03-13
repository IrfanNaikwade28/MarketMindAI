# Autonomous Multi-Agent AI Council for Social Media Strategy

A full-stack hackathon project that simulates a complete AI marketing team. Six specialized AI agents debate social media strategy in real time, reach a consensus, generate platform-specific content, and publish to **Bluesky** automatically.

## What It Does

You provide a brand name, campaign goal, and a brief. The AI Council then:

1. **Trend Agent** — scans current trends and proposes a content angle
2. **Brand Agent** — reviews the proposal for brand alignment and refines it
3. **Risk Agent** — evaluates legal, reputational, and platform-policy risks
4. **Engagement Agent** — predicts virality and engagement potential
5. **CMO Agent** — makes the final approve/reject decision
6. **Mentor Agent** — reviews debate quality and gives feedback

If the debate is approved, the system generates platform-specific content for Instagram, Twitter, TikTok, YouTube, LinkedIn, and Facebook — then **publishes a post to Bluesky** via the AT Protocol.

The entire debate streams live to the browser over WebSockets.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.11, SQLAlchemy 2, aiosqlite |
| AI | Groq API — `meta-llama/llama-4-scout-17b-16e-instruct` |
| Database | SQLite (file: `backend/ai_council.db`) |
| Task Queue | Celery + Redis (optional — degrades gracefully to asyncio) |
| Real-time | WebSockets (native FastAPI) |
| Publishing | Bluesky via `atproto` Python client |
| Frontend | React 18, Vite 5, TailwindCSS 3, React Query 5, Recharts |
| Routing | React Router 6 |

---

## Project Structure

```
.
├── backend/
│   ├── main.py                        # FastAPI entry point
│   ├── requirements.txt
│   ├── .env                           # secrets (not committed)
│   ├── ai_council.db                  # SQLite database (auto-created)
│   └── app/
│       ├── agents/                    # 6 AI agents (trend, brand, risk, engagement, cmo, mentor)
│       ├── api/routes/                # REST endpoints + WebSocket
│       ├── config/                    # Settings (pydantic-settings)
│       ├── database/                  # SQLAlchemy engine + session
│       ├── models/                    # 6 ORM models (campaign, debate, agent_log, ...)
│       ├── orchestrator/              # Debate engine + persistence layer
│       ├── services/                  # Content generator + Bluesky publisher
│       ├── utils/                     # Groq client wrapper
│       └── workers/                   # Celery tasks
└── frontend/
    ├── index.html
    ├── vite.config.js                 # Proxies /api/v1 → localhost:8000
    └── src/
        ├── pages/                     # Dashboard, CampaignBuilder, DebateRoom, ...
        ├── hooks/                     # useApi (React Query), useDebateSocket (WebSocket)
        └── services/api.js            # Axios base client
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Groq API key](https://console.groq.com)
- A [Bluesky](https://bsky.app) account

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
APP_NAME="AI Council"
APP_ENV=development
SECRET_KEY=change-me-in-production

DATABASE_URL=sqlite+aiosqlite:///./ai_council.db

GROQ_API_KEY=gsk_...your_key_here...
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_PASSWORD=your-app-password

REDIS_URL=redis://localhost:6379/0
ALLOWED_ORIGINS=http://localhost:5173
```

Start the backend:

```bash
uvicorn main:app --reload --port 8000
```

The database and all tables are created automatically on first run.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Usage

1. Click **New Campaign** in the sidebar
2. Fill in Brand Name, Campaign Goal, Target Audience, and a brief
3. Toggle **"Immediately start AI Council debate"** (on by default)
4. Click **Create & Run Debate**
5. Watch the 6 agents debate live in the **Debate Room**
6. If the CMO approves, content is generated and a post is published to Bluesky

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/campaigns` | Create a campaign |
| `GET` | `/api/v1/campaigns` | List campaigns |
| `GET` | `/api/v1/campaigns/{id}` | Get campaign detail |
| `PATCH` | `/api/v1/campaigns/{id}` | Update campaign |
| `POST` | `/api/v1/campaigns/{id}/run` | Trigger debate via background task |
| `GET` | `/api/v1/debates` | List debate sessions |
| `GET` | `/api/v1/debates/{id}` | Get debate detail |
| `GET` | `/api/v1/debates/{id}/logs` | Get all agent logs |
| `POST` | `/api/v1/debates/{id}/retry` | Retry a failed/vetoed debate |
| `WS` | `/api/v1/debates/{campaign_id}/stream` | Live debate WebSocket stream |
| `GET` | `/api/v1/content` | List generated content posts |
| `GET` | `/api/v1/analytics/overview` | Analytics overview |
| `GET` | `/health` | Health check |

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Debate Flow

```
User creates campaign
        │
        ▼
  [Trend Agent]  →  proposes content angle based on current trends
        │
        ▼
  [Brand Agent]  →  refines angle for brand alignment
        │
        ▼
  [Risk Agent]   →  checks for legal / platform / reputational risks
        │           (veto only if risk_score >= 0.85)
        ▼
[Engagement Agent] → predicts virality and audience response
        │
        ▼
  [CMO Agent]    →  approve / approve_modified / reject
        │
        ▼
  [Mentor Agent] →  reviews debate quality, provides coaching
        │
        ▼ (if approved)
 Content Generator → creates posts for all 6 platforms
        │
        ▼
  Bluesky Publish  → posts to bsky.social via atproto
```

---

## Notes

- Redis and Celery are optional. If Redis is not running, debates fall back to `asyncio.create_task` automatically.
- Only Bluesky publishing is real. Content is generated for all platforms as part of the AI simulation, but only Bluesky uses the live `atproto` API.
- The SQLite DB is recreated from scratch on every fresh start (no migrations needed for dev).
