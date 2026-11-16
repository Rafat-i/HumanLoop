"""Initial schema from an immutable migration-local model snapshot."""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def metadata():
    spec = importlib.util.spec_from_file_location(
        "humanloop_initial_schema", Path(__file__).parents[1] / "initial_schema.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Base.metadata


def upgrade():
    metadata().create_all(bind=op.get_bind(), checkfirst=False)


def downgrade():
    metadata().drop_all(bind=op.get_bind(), checkfirst=False)
