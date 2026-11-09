"""Add ordered routing operations per part."""
from alembic import op
import sqlalchemy as sa

revision = "0002_routing_operations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("routing_operations"):
        op.create_table(
            "routing_operations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("parts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("operation_name", sa.String(length=120), nullable=False),
            sa.Column("machine_rate_key", sa.String(length=120), nullable=False),
            sa.Column("cycle_time_min", sa.Float(), nullable=False),
            sa.UniqueConstraint("part_id", "sequence_no", name="uq_part_route_sequence"),
        )
        op.create_index("ix_routing_operations_part_id", "routing_operations", ["part_id"])


def downgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table("routing_operations"):
        op.drop_index("ix_routing_operations_part_id", table_name="routing_operations")
        op.drop_table("routing_operations")
