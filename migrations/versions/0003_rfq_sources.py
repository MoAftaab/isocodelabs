"""Store uploaded RFQ source documents and attach multiple parts."""
from alembic import op
import sqlalchemy as sa


revision = "0003_rfq_sources"
down_revision = "0002_routing_operations"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("rfq_sources"):
        op.create_table(
            "rfq_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("file_id", sa.String(length=100), nullable=False, unique=True),
            sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=True),
            sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("media_type", sa.String(length=120), nullable=False, server_default="application/octet-stream"),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("extraction_method", sa.String(length=40), nullable=True),
            sa.Column("extraction_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_rfq_sources_file_id", "rfq_sources", ["file_id"])
        op.create_index("ix_rfq_sources_rfq_id", "rfq_sources", ["rfq_id"])
        op.create_index("ix_rfq_sources_uploaded_by", "rfq_sources", ["uploaded_by"])


def downgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("rfq_sources"):
        op.drop_index("ix_rfq_sources_uploaded_by", table_name="rfq_sources")
        op.drop_index("ix_rfq_sources_rfq_id", table_name="rfq_sources")
        op.drop_index("ix_rfq_sources_file_id", table_name="rfq_sources")
        op.drop_table("rfq_sources")
