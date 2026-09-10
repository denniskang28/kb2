from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from kb2_runtime.config import Settings


settings = Settings.from_env()
url = URL.create(
    "postgresql+psycopg",
    username=settings.database_user,
    password=settings.database_password(),
    host=settings.database_host,
    port=settings.database_port,
    database=settings.database_name,
)


def run_migrations_online() -> None:
    connectable = create_engine(url, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
