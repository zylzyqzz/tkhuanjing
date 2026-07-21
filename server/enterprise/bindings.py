from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Customer, Device, LiveRoom
from ..models_enterprise import AnchorProfile, DeviceRoomBinding, LiveAccount
from .common import api_error


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


def create_binding_transaction(
    db: Session,
    *,
    device_id: str,
    organization_id: int,
    member_id: int,
    room_id: int,
    account_id: int | None,
    anchor_id: int | None,
    binding_type: str,
    reason: str,
) -> tuple[DeviceRoomBinding, bool]:
    """Create or replace a binding while locking every conflicting resource."""
    lock = {"nowait": True} if db.bind is not None and db.bind.dialect.name == "postgresql" else {}
    device = db.scalar(select(Device).where(Device.device_id == device_id).with_for_update(**lock))
    if not device or device.status != "active" or device.customer_id not in {None, organization_id}:
        raise api_error("TENANT_RESOURCE_NOT_FOUND", "设备不存在、已停用或属于其他企业")

    current = db.scalar(
        select(DeviceRoomBinding).where(
            DeviceRoomBinding.device_id == device_id,
            DeviceRoomBinding.status == "active",
            DeviceRoomBinding.binding_type == "primary",
        ).with_for_update(**lock)
    )
    room = db.scalar(
        select(LiveRoom).where(
            LiveRoom.id == room_id,
            LiveRoom.customer_id == organization_id,
            LiveRoom.status == "active",
        ).with_for_update(**lock)
    )
    if not room:
        raise api_error("TENANT_RESOURCE_NOT_FOUND", "直播间不存在、已停用或属于其他企业")
    room_binding = db.scalar(
        select(DeviceRoomBinding).where(
            DeviceRoomBinding.room_id == room_id,
            DeviceRoomBinding.status == "active",
            DeviceRoomBinding.binding_type == "primary",
        ).with_for_update(**lock)
    )
    if binding_type == "primary" and room_binding and room_binding.device_id != device_id:
        raise api_error("BINDING_CONFLICT", "该直播间已有主设备", {"room_id": room_id})

    account = None
    if account_id is not None:
        account = db.scalar(select(LiveAccount).where(LiveAccount.id == account_id, LiveAccount.organization_id == organization_id).with_for_update(**lock))
        if not account:
            raise api_error("TENANT_RESOURCE_NOT_FOUND", "开播账号不存在或属于其他企业")
        if account.status != "active":
            raise api_error("ACCOUNT_INACTIVE", "开播账号已停用", {"account_id": account_id})
        if account.room_id not in {None, room_id}:
            raise api_error("ACCOUNT_ROOM_MISMATCH", "开播账号不属于目标直播间", {"account_id": account_id, "room_id": room_id})

    anchor = None
    if anchor_id is not None:
        anchor = db.scalar(select(AnchorProfile).where(AnchorProfile.id == anchor_id, AnchorProfile.organization_id == organization_id).with_for_update(**lock))
        if not anchor:
            raise api_error("TENANT_RESOURCE_NOT_FOUND", "主播不存在或属于其他企业")
        if anchor.status != "active":
            raise api_error("ANCHOR_INACTIVE", "主播已停用", {"anchor_id": anchor_id})

    if current and current.room_id == room_id and current.account_id == account_id and current.anchor_id == anchor_id and current.binding_type == binding_type:
        return current, True

    if binding_type == "primary" and current:
        current.status = "ended"
        current.unbound_at = datetime.now(timezone.utc)
        current.reason = reason or "换绑"

    version = (db.scalar(select(DeviceRoomBinding.version).where(DeviceRoomBinding.device_id == device_id).order_by(DeviceRoomBinding.version.desc()).limit(1)) or 0) + 1
    row = DeviceRoomBinding(
        organization_id=organization_id,
        device_id=device_id,
        room_id=room_id,
        account_id=account.id if account else None,
        anchor_id=anchor.id if anchor else None,
        binding_type=binding_type,
        bound_by_user_id=member_id,
        reason=reason,
        version=version,
    )
    db.add(row)
    if binding_type == "primary":
        organization = db.get(Customer, organization_id)
        device.customer_id = organization_id
        device.room_id = room_id
        device.customer_name = organization.name if organization else ""
        device.room_name = room.name
    db.flush()
    return row, False


def end_primary_binding_transaction(db: Session, *, device_id: str, organization_id: int, reason: str) -> DeviceRoomBinding:
    lock = {"nowait": True} if db.bind is not None and db.bind.dialect.name == "postgresql" else {}
    device = db.scalar(select(Device).where(Device.device_id == device_id, Device.customer_id == organization_id, Device.status == "active").with_for_update(**lock))
    if not device:
        raise api_error("TENANT_RESOURCE_NOT_FOUND", "设备不存在、已停用或属于其他企业")
    row = db.scalar(
        select(DeviceRoomBinding).where(
            DeviceRoomBinding.device_id == device_id,
            DeviceRoomBinding.organization_id == organization_id,
            DeviceRoomBinding.status == "active",
            DeviceRoomBinding.binding_type == "primary",
        ).with_for_update(**lock)
    )
    if not row:
        raise api_error("TENANT_RESOURCE_NOT_FOUND", "当前没有有效主绑定")
    row.status = "ended"
    row.unbound_at = datetime.now(timezone.utc)
    row.reason = reason
    device.room_id = None
    device.room_name = ""
    db.flush()
    return row
