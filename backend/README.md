# OmniBot V3 Backend

FastAPI backend foundation for OmniBot V3, an AI Sales Operating System for Instagram fashion sellers.

Sprint 1 focuses on architecture only:

- FastAPI project structure
- SQL migrations
- Pydantic schemas
- Route skeletons
- Service skeletons
- Repository layer
- Configuration management
- Supabase client abstraction

No business logic, AI logic, payments, followups, Instagram integration, or frontend is implemented in this sprint.

## Local Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` and fill in values before connecting to Supabase.
