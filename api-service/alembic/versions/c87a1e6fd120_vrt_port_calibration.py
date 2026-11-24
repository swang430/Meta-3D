"""保存传导逐端口校准原文和撤销信息。"""
from alembic import op
import sqlalchemy as sa
from app.db.migration_helpers import table_exists

revision = "c87a1e6fd120"
down_revision = "b819beb04188"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("vrt_port_calibrations"):
        op.create_table(
            "vrt_port_calibrations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("evidence_sha256", sa.String(64), nullable=False, unique=True),
            sa.Column("issuer", sa.String(128), nullable=False),
            sa.Column("evidence_b64", sa.Text(), nullable=False),
            sa.Column("report_file", sa.String(255), nullable=False),
            sa.Column("report_number", sa.String(500), nullable=False),
            sa.Column("readings_b64", sa.Text(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("revocation_reason", sa.Text()),
            sa.UniqueConstraint("issuer", "report_number", name="uq_vrt_calibration_issuer_report"),
        )


def downgrade():
    op.drop_table("vrt_port_calibrations")
