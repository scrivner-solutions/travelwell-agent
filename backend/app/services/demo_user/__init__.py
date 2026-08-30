"""The demo account: its contents in data.py, its insertion walk in build.py."""

from app.services.demo_user.build import build_demo_user, wipe_demo_user

__all__ = ["build_demo_user", "wipe_demo_user"]
