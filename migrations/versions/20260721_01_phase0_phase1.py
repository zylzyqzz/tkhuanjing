"""Phase 0 organization foundation and Phase 1 device binding."""
from alembic import op
import sqlalchemy as sa

revision = "20260721_01"
down_revision = "20260721_00"
branch_labels = None
depends_on = None

def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]

def prepare_organization_members():
    """Preserve the pre-Alembic membership table before adopting Phase 0."""
    inspector = sa.inspect(op.get_bind())
    if "organization_members" not in inspector.get_table_names():
        return False
    columns = {item["name"] for item in inspector.get_columns("organization_members")}
    expected = {"username", "password_hash", "permissions_json", "active", "created_at", "updated_at"}
    if expected <= columns:
        return True
    legacy_name = "organization_members_legacy_phase01"
    if legacy_name in inspector.get_table_names():
        raise RuntimeError(f"cannot preserve legacy organization_members: {legacy_name} already exists")
    op.rename_table("organization_members", legacy_name)
    return False

def upgrade():
    if not prepare_organization_members():
        op.create_table("organization_members",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="CASCADE"),nullable=False),sa.Column("username",sa.String(80),nullable=False),sa.Column("password_hash",sa.Text(),nullable=False),sa.Column("display_name",sa.String(80),nullable=False,server_default=""),sa.Column("phone",sa.String(30),nullable=False,server_default=""),sa.Column("role",sa.String(30),nullable=False,server_default="viewer"),sa.Column("permissions_json",sa.Text(),nullable=False,server_default="[]"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),*timestamps(),sa.UniqueConstraint("organization_id","username",name="uq_org_member_username"))
    if "ix_org_members_org" not in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("organization_members")}:
        op.create_index("ix_org_members_org","organization_members",["organization_id"])
    op.create_table("organization_member_sessions",sa.Column("token_hash",sa.String(64),primary_key=True),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="CASCADE"),nullable=False),sa.Column("member_id",sa.Integer(),sa.ForeignKey("organization_members.id",ondelete="CASCADE"),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("revoked",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("live_accounts",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="CASCADE"),nullable=False),sa.Column("room_id",sa.Integer(),sa.ForeignKey("live_rooms.id",ondelete="SET NULL")),sa.Column("platform",sa.String(30),nullable=False,server_default="tiktok"),sa.Column("display_name",sa.String(120),nullable=False),sa.Column("platform_account_ref",sa.String(160),nullable=False,server_default=""),sa.Column("target_region_id",sa.String(80),nullable=False,server_default="us-los-angeles"),sa.Column("status",sa.String(20),nullable=False,server_default="active"),sa.Column("notes",sa.Text(),nullable=False,server_default=""),*timestamps())
    op.create_index("ix_live_accounts_org","live_accounts",["organization_id"])
    op.create_table("anchor_profiles",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="CASCADE"),nullable=False),sa.Column("display_name",sa.String(120),nullable=False),sa.Column("employee_ref",sa.String(80),nullable=False,server_default=""),sa.Column("status",sa.String(20),nullable=False,server_default="active"),sa.Column("labels_json",sa.Text(),nullable=False,server_default="[]"),sa.Column("notes",sa.Text(),nullable=False,server_default=""),*timestamps())
    op.create_index("ix_anchor_profiles_org","anchor_profiles",["organization_id"])
    op.create_table("device_room_bindings",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="CASCADE"),nullable=False),sa.Column("device_id",sa.String(80),sa.ForeignKey("devices.device_id",ondelete="CASCADE"),nullable=False),sa.Column("room_id",sa.Integer(),sa.ForeignKey("live_rooms.id",ondelete="CASCADE"),nullable=False),sa.Column("account_id",sa.Integer(),sa.ForeignKey("live_accounts.id",ondelete="SET NULL")),sa.Column("anchor_id",sa.Integer(),sa.ForeignKey("anchor_profiles.id",ondelete="SET NULL")),sa.Column("binding_type",sa.String(20),nullable=False,server_default="primary"),sa.Column("status",sa.String(20),nullable=False,server_default="active"),sa.Column("bound_by_user_id",sa.Integer(),sa.ForeignKey("organization_members.id",ondelete="RESTRICT"),nullable=False),sa.Column("bound_at",sa.DateTime(timezone=True),nullable=False),sa.Column("unbound_at",sa.DateTime(timezone=True)),sa.Column("reason",sa.Text(),nullable=False,server_default=""),sa.Column("version",sa.Integer(),nullable=False,server_default="1"))
    op.create_index("ix_bindings_org","device_room_bindings",["organization_id"])
    op.create_index("uq_active_primary_device","device_room_bindings",["device_id"],unique=True,sqlite_where=sa.text("status='active' AND binding_type='primary'"),postgresql_where=sa.text("status='active' AND binding_type='primary'"))
    op.create_index("uq_active_primary_room","device_room_bindings",["room_id"],unique=True,sqlite_where=sa.text("status='active' AND binding_type='primary'"),postgresql_where=sa.text("status='active' AND binding_type='primary'"))
    op.create_table("device_heartbeats_v2",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organization_id",sa.Integer(),sa.ForeignKey("customers.id",ondelete="CASCADE"),nullable=False),sa.Column("device_id",sa.String(80),sa.ForeignKey("devices.device_id",ondelete="CASCADE"),nullable=False),sa.Column("binding_id",sa.Integer(),sa.ForeignKey("device_room_bindings.id",ondelete="SET NULL")),sa.Column("agent_version",sa.String(40),nullable=False,server_default=""),sa.Column("sent_at",sa.DateTime(timezone=True),nullable=False),sa.Column("received_at",sa.DateTime(timezone=True),nullable=False),sa.Column("uptime_seconds",sa.Integer(),nullable=False,server_default="0"),sa.Column("device_status",sa.String(20),nullable=False,server_default="online"),sa.Column("live_software_json",sa.Text(),nullable=False,server_default="{}"),sa.Column("collection_json",sa.Text(),nullable=False,server_default="{}"),sa.Column("cpu_percent",sa.Float()),sa.Column("memory_percent",sa.Float()),sa.Column("network_latency_ms",sa.Float()),sa.Column("upload_mbps",sa.Float()),sa.Column("stream_bitrate_kbps",sa.Float()),sa.Column("dropped_frames",sa.Integer()),sa.Column("last_success_at",sa.DateTime(timezone=True)),sa.UniqueConstraint("device_id","sent_at",name="uq_device_heartbeat_sent_at"))
    op.create_index("ix_heartbeats_org","device_heartbeats_v2",["organization_id"])
    op.create_index("ix_heartbeats_device_received","device_heartbeats_v2",["device_id","received_at"])

def downgrade():
    op.drop_table("device_heartbeats_v2")
    op.drop_table("device_room_bindings")
    op.drop_table("anchor_profiles")
    op.drop_table("live_accounts")
    op.drop_table("organization_member_sessions")
    op.drop_table("organization_members")
