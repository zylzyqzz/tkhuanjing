"""Phase 1.5 feature center, bootstrap versions and onboarding state."""
from alembic import op
import sqlalchemy as sa

revision = "20260721_03"
down_revision = "20260721_02"
branch_labels = None
depends_on = None


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in names:
        op.add_column(table, column)


def upgrade():
    _add_column_if_missing("customers", sa.Column("feature_config_version", sa.Integer(), nullable=False, server_default="1"))
    _add_column_if_missing("customers", sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="1"))
    _add_column_if_missing("customers", sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("devices", sa.Column("feature_config_version", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "feature_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature_code", sa.String(80), nullable=False, unique=True),
        sa.Column("feature_name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_type", sa.String(30), nullable=False, server_default="all"),
        sa.Column("default_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("minimum_client_version", sa.String(40), nullable=False, server_default=""),
        sa.Column("config_schema_json", sa.Text(), nullable=False, server_default="{}"),
        *_timestamps(),
    )
    op.create_index("ix_feature_definitions_code", "feature_definitions", ["feature_code"], unique=True)
    op.create_table(
        "plan_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.String(40), sa.ForeignKey("subscription_plans.code", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limits_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        *_timestamps(),
        sa.UniqueConstraint("plan_id", "feature_id", name="uq_plan_feature"),
    )
    op.create_table(
        "organization_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(80), nullable=False, server_default=""),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", "feature_id", name="uq_organization_feature"),
    )
    op.create_table(
        "role_feature_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("can_read", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_create", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_update", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_manage", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", "role", "feature_id", name="uq_role_feature_permission"),
    )
    op.create_table(
        "device_feature_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(80), sa.ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("device_id", "feature_id", name="uq_device_feature_override"),
    )
    op.create_table(
        "feature_rollouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rollout_type", sa.String(20), nullable=False, server_default="all"),
        sa.Column("percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("organization_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("device_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("minimum_version", sa.String(40), nullable=False, server_default=""),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_timestamps(),
    )
    for table, columns in (
        ("plan_features", ["plan_id", "feature_id"]),
        ("organization_features", ["organization_id", "feature_id"]),
        ("role_feature_permissions", ["organization_id", "role", "feature_id"]),
        ("device_feature_overrides", ["organization_id", "device_id", "feature_id"]),
        ("feature_rollouts", ["feature_id", "status"]),
    ):
        op.create_index(f"ix_{table}_lookup", table, columns)


def downgrade():
    for table in ("feature_rollouts", "device_feature_overrides", "role_feature_permissions", "organization_features", "plan_features", "feature_definitions"):
        op.drop_table(table)
    op.drop_column("devices", "feature_config_version")
    op.drop_column("customers", "onboarding_completed")
    op.drop_column("customers", "onboarding_step")
    op.drop_column("customers", "feature_config_version")
