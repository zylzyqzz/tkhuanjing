from __future__ import annotations

import argparse
import os

from argon2 import PasswordHasher
from sqlalchemy import select

from .database import SessionLocal
from .models import Admin


def reset_admin_password(username: str, password: str) -> None:
    if len(password) < 8:
        raise ValueError("管理员密码至少需要 8 个字符")
    with SessionLocal() as db:
        row = db.scalar(select(Admin).where(Admin.username == username))
        if not row:
            row = Admin(username=username, password_hash="")
            db.add(row)
        row.password_hash = PasswordHasher().hash(password)
        row.active = True
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="TK 管理后台维护工具")
    sub = parser.add_subparsers(dest="command", required=True)
    reset = sub.add_parser("reset-password")
    reset.add_argument("username")
    reset.add_argument("--password-env", default="TK_BOOTSTRAP_PASSWORD")
    args = parser.parse_args()
    if args.command == "reset-password":
        password = os.environ.get(args.password_env, "")
        if not password:
            raise SystemExit(f"环境变量 {args.password_env} 未设置")
        reset_admin_password(args.username, password)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
