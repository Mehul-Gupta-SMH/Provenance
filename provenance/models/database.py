from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from provenance.config import get_settings


def _get_engine():
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _get_engine()


def create_db_and_tables() -> None:
    """Create all tables. Used in dev/testing only — Alembic owns schema in production."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
