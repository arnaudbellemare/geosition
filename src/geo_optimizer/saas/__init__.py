"""Multi-tenant GEO platform: orgs, domain verification, client workspaces."""

from __future__ import annotations

from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore

__all__ = ["PlatformStore", "PlatformService"]
