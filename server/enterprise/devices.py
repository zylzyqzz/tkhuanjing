from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..models import Device, LiveRoom
from ..models_enterprise import AnchorProfile, DeviceRoomBinding, LiveAccount
from .common import api_error


SORT_FIELDS = {
    "device_id": Device.device_id,
    "display_name": Device.display_name,
    "agent_version": Device.app_version,
    "last_heartbeat_at": Device.last_heartbeat_at,
    "studio_state": Device.studio_state,
    "collector_state": Device.collector_state,
    "cpu_percent": Device.cpu_percent,
    "memory_percent": Device.memory_percent,
    "network_latency_ms": Device.network_latency_ms,
    "upload_mbps": Device.upload_mbps,
}


def _online_expression(now: datetime):
    online_cutoff = (now - timedelta(seconds=60)).isoformat()
    unstable_cutoff = (now - timedelta(seconds=180)).isoformat()
    return case(
        (Device.last_heartbeat_at >= online_cutoff, "online"),
        (Device.last_heartbeat_at >= unstable_cutoff, "unstable"),
        else_="offline",
    )


def _abnormal_reasons(device: Device, online_state: str) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if online_state == "offline":
        reasons.append({"code": "DEVICE_OFFLINE", "level": "critical", "message": "设备心跳已中断"})
    elif online_state == "unstable":
        reasons.append({"code": "HEARTBEAT_UNSTABLE", "level": "warning", "message": "设备心跳不稳定"})
    if device.collector_state not in {"healthy", "ok"}:
        reasons.append({"code": "COLLECTOR_UNHEALTHY", "level": "warning", "message": "数据采集状态异常"})
    if device.studio_state not in {"running"}:
        reasons.append({"code": "LIVE_SOFTWARE_NOT_RUNNING", "level": "info", "message": "直播软件未运行"})
    if device.network_latency_ms is not None and device.network_latency_ms > 150:
        reasons.append({"code": "NETWORK_LATENCY_HIGH", "level": "warning", "message": "网络延迟偏高"})
    if device.upload_mbps is not None and device.upload_mbps < 8:
        reasons.append({"code": "UPLOAD_BANDWIDTH_LOW", "level": "warning", "message": "上传带宽偏低"})
    if device.cpu_percent is not None and device.cpu_percent > 85:
        reasons.append({"code": "CPU_LOAD_HIGH", "level": "warning", "message": "CPU 负载偏高"})
    if device.memory_percent is not None and device.memory_percent > 85:
        reasons.append({"code": "MEMORY_LOAD_HIGH", "level": "warning", "message": "内存负载偏高"})
    if device.dropped_frames is not None and device.dropped_frames > 0:
        reasons.append({"code": "DROPPED_FRAMES", "level": "warning", "message": "检测到丢帧"})
    return reasons


def realtime_device_page(
    db: Session,
    organization_id: int,
    *,
    room_id: int | None = None,
    account_id: int | None = None,
    anchor_id: int | None = None,
    online_state: str = "",
    collector_state: str = "",
    studio_state: str = "",
    agent_version: str = "",
    keyword: str = "",
    sort: str = "abnormal",
    order: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    if limit < 1 or limit > 200 or offset < 0:
        raise api_error("VALIDATION_ERROR", "分页参数无效")
    if order not in {"asc", "desc"}:
        raise api_error("VALIDATION_ERROR", "排序方向无效", {"order": order})
    if sort != "abnormal" and sort not in SORT_FIELDS and sort != "online_state":
        raise api_error("VALIDATION_ERROR", "排序字段无效", {"sort": sort})
    if online_state and online_state not in {"online", "unstable", "offline"}:
        raise api_error("VALIDATION_ERROR", "在线状态无效", {"online_state": online_state})

    binding = aliased(DeviceRoomBinding, name="active_binding")
    room = aliased(LiveRoom, name="bound_room")
    account = aliased(LiveAccount, name="bound_account")
    anchor = aliased(AnchorProfile, name="bound_anchor")
    now = datetime.now(timezone.utc)
    online_expr = _online_expression(now)
    stmt = (
        select(Device, binding, room, account, anchor, online_expr.label("computed_online_state"))
        .outerjoin(
            binding,
            and_(
                binding.device_id == Device.device_id,
                binding.organization_id == organization_id,
                binding.status == "active",
                binding.binding_type == "primary",
            ),
        )
        .outerjoin(room, room.id == binding.room_id)
        .outerjoin(account, account.id == binding.account_id)
        .outerjoin(anchor, anchor.id == binding.anchor_id)
        .where(Device.customer_id == organization_id)
    )
    if room_id is not None:
        stmt = stmt.where(binding.room_id == room_id)
    if account_id is not None:
        stmt = stmt.where(binding.account_id == account_id)
    if anchor_id is not None:
        stmt = stmt.where(binding.anchor_id == anchor_id)
    if online_state:
        stmt = stmt.where(online_expr == online_state)
    if collector_state:
        stmt = stmt.where(Device.collector_state == collector_state)
    if studio_state:
        stmt = stmt.where(Device.studio_state == studio_state)
    if agent_version:
        stmt = stmt.where(Device.app_version == agent_version)
    if keyword.strip():
        needle = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Device.device_id.ilike(needle),
                Device.display_name.ilike(needle),
                Device.store_name.ilike(needle),
                Device.location.ilike(needle),
                room.name.ilike(needle),
                account.display_name.ilike(needle),
                anchor.display_name.ilike(needle),
                cast(binding.id, String).ilike(needle),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    direction = "desc" if order == "desc" else "asc"
    if sort == "abnormal":
        abnormal_rank = case(
            (online_expr == "offline", 0),
            (online_expr == "unstable", 1),
            (Device.collector_state.notin_(["healthy", "ok"]), 2),
            (Device.studio_state != "running", 3),
            else_=4,
        )
        stmt = stmt.order_by(abnormal_rank.asc(), Device.last_heartbeat_at.desc(), Device.device_id.asc())
    else:
        column = online_expr if sort == "online_state" else SORT_FIELDS[sort]
        stmt = stmt.order_by(getattr(column, direction)().nullslast(), Device.device_id.asc())

    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    items = []
    for device, binding_row, room_row, account_row, anchor_row, computed_online_state in rows:
        binding_data = None
        if binding_row:
            binding_data = {
                "id": binding_row.id,
                "organization_id": binding_row.organization_id,
                "device_id": binding_row.device_id,
                "room_id": binding_row.room_id,
                "account_id": binding_row.account_id,
                "anchor_id": binding_row.anchor_id,
                "binding_type": binding_row.binding_type,
                "status": binding_row.status,
                "bound_by_user_id": binding_row.bound_by_user_id,
                "bound_at": binding_row.bound_at,
                "unbound_at": binding_row.unbound_at,
                "reason": binding_row.reason,
                "version": binding_row.version,
            }
        items.append(
            {
                "device_id": device.device_id,
                "display_name": device.display_name or device.device_id,
                "online": computed_online_state == "online",
                "online_state": computed_online_state,
                "agent_version": device.app_version,
                "last_heartbeat_at": device.last_heartbeat_at,
                "studio_state": device.studio_state,
                "collector_state": device.collector_state,
                "cpu_percent": device.cpu_percent,
                "memory_percent": device.memory_percent,
                "network_latency_ms": device.network_latency_ms,
                "upload_mbps": device.upload_mbps,
                "stream_bitrate_kbps": device.stream_bitrate_kbps,
                "dropped_frames": device.dropped_frames,
                "binding": binding_data,
                "room": {"id": room_row.id, "name": room_row.name, "region": room_row.region} if room_row else None,
                "account": {"id": account_row.id, "display_name": account_row.display_name, "platform": account_row.platform} if account_row else None,
                "anchor": {"id": anchor_row.id, "display_name": anchor_row.display_name} if anchor_row else None,
                "abnormal_reasons": _abnormal_reasons(device, computed_online_state),
                "live_software": {"name": "TikTok LIVE Studio", "running": device.studio_state == "running"},
                "collection": {"status": device.collector_state},
                "metrics": {
                    "cpu_percent": device.cpu_percent,
                    "memory_percent": device.memory_percent,
                    "network_latency_ms": device.network_latency_ms,
                    "upload_mbps": device.upload_mbps,
                    "stream_bitrate_kbps": device.stream_bitrate_kbps,
                    "dropped_frames": device.dropped_frames,
                },
            }
        )
    return {"items": items, "pagination": {"limit": limit, "offset": offset, "total": total}}
