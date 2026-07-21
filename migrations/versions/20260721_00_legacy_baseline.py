"""Adopt the legacy V1 schema without deleting existing data."""
from alembic import op
from sqlalchemy import MetaData
from server.database import Base
from server import models  # noqa: F401

revision = "20260721_00"
down_revision = None
branch_labels = None
depends_on = None
ENTERPRISE_TABLES = {
    "organization_members", "organization_member_sessions", "live_accounts",
    "anchor_profiles", "device_room_bindings", "device_heartbeats_v2",
    "feature_definitions", "plan_features", "organization_features",
    "role_feature_permissions", "device_feature_overrides", "feature_rollouts",
}

def upgrade():
    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in ENTERPRISE_TABLES:
            table.to_metadata(legacy)
    legacy.create_all(bind=op.get_bind(), checkfirst=True)

def downgrade():
    pass  # Baseline tables may predate Alembic and must never be deleted here.
