from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings):
    settings.ensure_directories()
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    return engine


def build_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def migrate_schema(engine) -> None:
    additions = {
        "experiments": {
            "cancel_requested_at": "DATETIME",
            "retry_of_experiment_id": "VARCHAR(36) REFERENCES experiments(id)",
        },
        "runs": {
            "current_stage": "VARCHAR(64)",
            "stage_started_at": "DATETIME",
            "last_heartbeat_at": "DATETIME",
            "last_activity_at": "DATETIME",
            "cancel_requested_at": "DATETIME",
            "current_attempt": "INTEGER NOT NULL DEFAULT 1",
        },
    }
    with engine.begin() as connection:
        schema = inspect(connection)
        for table_name, columns in additions.items():
            if not schema.has_table(table_name):
                continue
            existing = {column["name"] for column in schema.get_columns(table_name)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {definition}')
                    )
        if schema.has_table("experiments"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_experiments_retry_of_experiment_id "
                    "ON experiments (retry_of_experiment_id)"
                )
            )


def session_dependency(factory: sessionmaker[Session]):
    def dependency() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return dependency
