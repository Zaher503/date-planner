"""Alembic environment. The URL comes from app settings, not alembic.ini."""
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine

from app.config import get_settings
from app.db.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# PostGIS owns these
SKIP_TABLES = {"spatial_ref_sys", "topology", "layer"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name in SKIP_TABLES:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


def run_migrations() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=Base.metadata,
            include_object=include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
