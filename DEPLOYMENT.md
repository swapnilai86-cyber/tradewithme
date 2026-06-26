# Deployment Guide
1. Copy `.env.example` to `.env` and fill secrets.
2. Ensure Docker and Docker Compose are installed.
3. Run `docker-compose up --build -d`
4. Apply migrations: `docker-compose exec backend python -m backend.database.init_db`
5. Seed Admin: `docker-compose exec backend python -m backend.database.seed`
