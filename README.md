# SkillSwap — Student Skill Sharing API

FastAPI + PostgreSQL backend where students find mentors, book mentoring sessions and leave reviews.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit DATABASE_URL and JWT_SECRET_KEY
uvicorn app.main:app --reload
```

- Create the database first: `createdb skillswap` (or use a Supabase connection string in `DATABASE_URL`).
- Tables are created automatically on startup, and a default admin is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
- Swagger UI: http://127.0.0.1:8000/docs — log in, copy `access_token`, click **Authorize** and paste it.
- Postman: import `postman/SkillSwap.postman_collection.json` and run it with the Collection Runner (tokens/IDs are saved automatically).

## Project structure

```
app/
  main.py        app, routers, startup (create tables + default admin), IntegrityError -> 409
  config.py      settings from .env
  database.py    SQLAlchemy engine/session + get_db dependency
  models.py      User, Skill, MentoringSession, Review (+ Role/Level/Status enums)
  schemas.py     Pydantic request/response models and validation
  security.py    bcrypt hashing, JWT, get_current_user, require_roles (RBAC)
  routers/       auth, users, skills, sessions, reviews, admin
postman/         Postman collection (53 requests with tests)
```

## Roles

| Role    | How they get it            | Can do |
|---------|----------------------------|--------|
| student | register with `role=student` | book/cancel sessions, write/edit own reviews |
| mentor  | register with `role=mentor`  | create/update/delete own skills, complete/cancel own sessions |
| admin   | seeded from `.env`           | manage users (role, activate/deactivate, delete), see all sessions, stats, delete any skill/review |

## Endpoints

| Method | Path | Access | Notes |
|---|---|---|---|
| POST | /auth/register | public | 201, 409 duplicate email |
| POST | /auth/login | public | returns JWT, 401 bad credentials, 403 deactivated |
| GET / PUT | /users/me | logged in | view / update own profile |
| GET | /users/mentors | public | search: `skill`, `category`, `min_rating`, `skip`, `limit` |
| GET | /users/mentors/{id} | public | profile with skills + average rating |
| POST | /skills | mentor | 409 if mentor already has that title |
| GET | /skills | public | search: `q`, `category`, `level`, `mentor_id`, `skip`, `limit` |
| GET | /skills/{id} | public | 404 if missing |
| PUT / DELETE | /skills/{id} | owner mentor / admin | 403 if not owner; 400 if deleting with upcoming sessions |
| POST | /sessions | student | 422 past date, 409 mentor time clash |
| GET | /sessions | logged in | history; filters `status`, `from_date`, `to_date` (admin sees all) |
| GET | /sessions/{id} | participant / admin | |
| PATCH | /sessions/{id}/cancel | participant / admin | 400 if not booked or already started |
| PATCH | /sessions/{id}/complete | mentor / admin | 400 if not booked |
| POST | /reviews | student | only own completed sessions; 409 if already reviewed |
| GET | /reviews | public | filters `mentor_id`, `min_rating` |
| GET / PUT / DELETE | /reviews/{id} | author (admin can delete) | |
| GET | /admin/users | admin | filters `role`, `is_active`, `q` |
| GET | /admin/users/{id} | admin | |
| PATCH | /admin/users/{id}/role, /status | admin | cannot change self |
| DELETE | /admin/users/{id}, /admin/sessions/{id} | admin | 204 |
| GET | /admin/stats | admin | counts by role/status |

## Requirements checklist

1. **FastAPI REST API** — `app/routers/*`
2. **CRUD** — users, skills, sessions, reviews (create/read/update/delete)
3. **PostgreSQL** — `DATABASE_URL` (local or Supabase)
4. **DB integration** — SQLAlchemy ORM (`database.py`, `models.py`)
5. **Pydantic validation** — `schemas.py` (lengths, email, enums, rating 1–5, duration 30–180, future date, password strength)
6. **JWT auth** — `/auth/register`, `/auth/login`, `security.py`
7. **Password hashing** — bcrypt
8. **Authorization** — owner checks (own skills, own sessions, own reviews)
9. **RBAC (3 roles)** — student, mentor, admin via `require_roles(...)`
10. **Protected routes** — `Depends(get_current_user)`
11. **Path & query params** — `/skills/{id}`, `?q=&category=&level=` etc.
12. **Status codes** — 200, 201, 204, 400, 401, 403, 404, 409, 422
13. **Exception handling** — `HTTPException` everywhere + global `IntegrityError` → 409
14. **Environment variables** — `.env` / `.env.example`
15. **Swagger** — `/docs`
16. **Postman** — `postman/SkillSwap.postman_collection.json`
