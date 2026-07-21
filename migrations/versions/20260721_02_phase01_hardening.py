"""Phase 0/1 hardening: organization codes, tenant-local usernames and device state."""
from alembic import op
import sqlalchemy as sa

revision = "20260721_02"
down_revision = "20260721_01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "organization_code" not in {col["name"] for col in inspector.get_columns("customers")}:
        op.add_column("customers", sa.Column("organization_code", sa.String(40), nullable=False, server_default=""))
    # Backfill legacy rows before applying the global unique index.
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE customers SET organization_code = 'ORG-' || id WHERE organization_code IS NULL OR organization_code = ''"))
    if "ix_customers_organization_code" not in {idx["name"] for idx in inspector.get_indexes("customers")}:
        op.create_index("ix_customers_organization_code", "customers", ["organization_code"], unique=True)
    for name, type_, default in (
        ("online_state", sa.String(20), "offline"),
        ("collector_state", sa.String(20), "unknown"),
        ("cpu_percent", sa.Float(), None),
        ("memory_percent", sa.Float(), None),
        ("network_latency_ms", sa.Float(), None),
        ("upload_mbps", sa.Float(), None),
        ("stream_bitrate_kbps", sa.Float(), None),
        ("dropped_frames", sa.Integer(), None),
        ("clock_skew_seconds", sa.Integer(), "0"),
    ):
        if name not in {col["name"] for col in inspector.get_columns("devices")}:
            op.add_column("devices", sa.Column(name, type_, nullable=True, server_default=default))
    indexes = {idx["name"] for idx in inspector.get_indexes("devices")}
    if "ix_devices_online_state" not in indexes:
        op.create_index("ix_devices_online_state", "devices", ["online_state"])
    if "ix_devices_collector_state" not in indexes:
        op.create_index("ix_devices_collector_state", "devices", ["collector_state"])


def downgrade():
    op.drop_index("ix_devices_collector_state", table_name="devices")
    op.drop_index("ix_devices_online_state", table_name="devices")
    for name in ("clock_skew_seconds", "dropped_frames", "stream_bitrate_kbps", "upload_mbps", "network_latency_ms", "memory_percent", "cpu_percent", "collector_state", "online_state"):
        op.drop_column("devices", name)
    with op.batch_alter_table("organization_members") as batch:
        batch.drop_constraint("uq_org_member_username", type_="unique")
        batch.create_unique_constraint("uq_organization_members_username", ["username"])
    op.drop_index("ix_customers_organization_code", table_name="customers")
    op.drop_column("customers", "organization_code")
