import os
import alembic.config
import alembic.command

def run_migrations():
    """
    Run alembic migrations programmatically.
    Requires alembic.ini to be present in the working directory.
    """
    alembic_cfg = alembic.config.Config("alembic.ini")
    alembic.command.upgrade(alembic_cfg, "head")

if __name__ == "__main__":
    run_migrations()
    print("Database migrations applied successfully.")
