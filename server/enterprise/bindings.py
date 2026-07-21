from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models_enterprise import DeviceRoomBinding


def get_active_primary_binding(
    db: Session,
    device_id: str,
    organization_id: int | None = None,
    *,
    for_update: bool = False,
) -> DeviceRoomBinding | None:
    """Return the actual active primary binding; never infer it by sorting."""
    stmt = select(DeviceRoomBinding).where(
        DeviceRoomBinding.device_id == device_id,
        DeviceRoomBinding.status == "active",
        DeviceRoomBinding.binding_type == "primary",
    )
    if organization_id is not None:
        stmt = stmt.where(DeviceRoomBinding.organization_id == organization_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)
