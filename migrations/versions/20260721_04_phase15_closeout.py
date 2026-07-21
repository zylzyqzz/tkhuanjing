"""Phase 1.5 production closeout indexes and client configuration epoch."""

from alembic import op
import sqlalchemy as sa


revision = "20260721_04"
down_revision = "20260721_03"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_devices_tenant_heartbeat", "devices", ["customer_id", "last_heartbeat_at"]),
    ("ix_devices_tenant_runtime", "devices", ["customer_id", "collector_state", "studio_state", "app_version"]),
    ("ix_bindings_tenant_active", "device_room_bindings", ["organization_id", "status", "binding_type", "device_id"]),
    ("ix_bindings_tenant_targets", "device_room_bindings", ["organization_id", "room_id", "account_id", "anchor_id"]),
)


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for name, table, columns in INDEXES:
        existing = {item["name"] for item in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)
    settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.Text))
    connection = op.get_bind()
    exists = connection.execute(sa.select(settings.c.key).where(settings.c.key == "feature_config_epoch")).first()
    if not exists:
        op.bulk_insert(settings, [{"key": "feature_config_epoch", "value": "1"}])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for name, table, _columns in reversed(INDEXES):
        existing = {item["name"] for item in inspector.get_indexes(table)}
        if name in existing:
            op.drop_index(name, table_name=table)
    settings = sa.table("settings", sa.column("key", sa.String), sa.column("value", sa.Text))
    op.get_bind().execute(sa.delete(settings).where(settings.c.key == "feature_config_epoch"))
