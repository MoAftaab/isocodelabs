"""Persist the configured GST rate on each quote revision."""
from alembic import op
import sqlalchemy as sa

revision = "0004_gst_snapshot"
down_revision = "0003_rfq_sources"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("quote_revisions")}
    if "gst_rate_percent" not in columns:
        op.add_column(
            "quote_revisions",
            sa.Column("gst_rate_percent", sa.Float(), nullable=False, server_default="0"),
        )


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("quote_revisions")}
    if "gst_rate_percent" in columns:
        op.drop_column("quote_revisions", "gst_rate_percent")
