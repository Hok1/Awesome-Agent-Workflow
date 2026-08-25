from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ProjectRegistry
from ..errors import ApiError
from ..models import AiMaster, ComponentAiMaster
from .queries import Filters, QueryService

# Tier thresholds for the AI Master assessment rules (based on the 80% rate).
_RATE_NONE = 0.65  # rate >= 0.65 -> no question requirement
_RATE_FIVE = 0.50  # rate < 0.50 -> need >= 5 questions

UNASSIGNED_MASTER_LABEL = "未分配"


def tier_for(rate: float | None) -> str:
    """Map an 80% adoption rate to an assessment tier.

    - rate >= 0.65            -> "none"   (no question requirement)
    - 0.50 <= rate < 0.65     -> "three"  (need >= 3 questions)
    - rate < 0.50             -> "five"   (need >= 5 questions)
    - rate is None            -> "no_data"
    """
    if rate is None:
        return "no_data"
    if rate >= _RATE_NONE:
        return "none"
    if rate >= _RATE_FIVE:
        return "three"
    return "five"


def _master_payload(master: AiMaster, component_count: int = 0) -> dict[str, Any]:
    return {
        "id": str(master.id),
        "name": master.name,
        "component_count": component_count,
    }


def _component_base(component: dict[str, Any]) -> dict[str, Any]:
    return {
        "component_id": component["component_id"],
        "name": component["name"],
        "se": component.get("se"),
        "used_aaw": bool(component.get("used_aaw")),
        "effective_lines": component.get("effective_lines") or 0,
        "attribution_rate_80": component.get("attribution_rate_80"),
        "tier": tier_for(component.get("attribution_rate_80")),
    }


class AiMasterService:
    def __init__(self, session: Session, projects: ProjectRegistry):
        self.session = session
        self.projects = projects
        self._query = QueryService(session, projects)

    # ── AI Master CRUD ────────────────────────────────────────────────

    def list_ai_masters(self) -> dict[str, Any]:
        masters = self.session.scalars(
            select(AiMaster).order_by(AiMaster.name)
        ).all()
        counts = self._component_counts_by_master()
        return {
            "items": [
                _master_payload(master, counts.get(master.id, 0)) for master in masters
            ]
        }

    def create_ai_master(self, name: str) -> dict[str, Any]:
        value = (name or "").strip()
        if not value:
            raise ApiError(400, "INVALID_AI_MASTER_NAME", "name must not be empty")
        existing = self.session.scalar(
            select(AiMaster).where(AiMaster.name == value)
        )
        if existing is not None:
            raise ApiError(409, "AI_MASTER_EXISTS", "an AI Master with this name exists")
        now = datetime.now(UTC)
        master = AiMaster(
            id=uuid.uuid4(), name=value, created_at=now, updated_at=now
        )
        self.session.add(master)
        self.session.commit()
        return _master_payload(master)

    def rename_ai_master(self, master_id: uuid.UUID, name: str) -> dict[str, Any]:
        master = self._get_master(master_id)
        value = (name or "").strip()
        if not value:
            raise ApiError(400, "INVALID_AI_MASTER_NAME", "name must not be empty")
        duplicate = self.session.scalar(
            select(AiMaster).where(AiMaster.name == value, AiMaster.id != master.id)
        )
        if duplicate is not None:
            raise ApiError(409, "AI_MASTER_EXISTS", "an AI Master with this name exists")
        master.name = value
        master.updated_at = datetime.now(UTC)
        self.session.commit()
        return _master_payload(master)

    def delete_ai_master(self, master_id: uuid.UUID) -> dict[str, Any]:
        master = self._get_master(master_id)
        # Unassign every component that points at this master so they fall back to
        # the "unassigned" bucket; the component itself is preserved.
        assignments = self.session.scalars(
            select(ComponentAiMaster).where(
                ComponentAiMaster.ai_master_id == master.id
            )
        ).all()
        for assignment in assignments:
            self.session.delete(assignment)
        self.session.delete(master)
        self.session.commit()
        return {"id": str(master.id), "deleted": True}

    # ── component assignment ───────────────────────────────────────────

    def list_assignments(self) -> dict[str, Any]:
        rows = self.session.scalars(select(ComponentAiMaster)).all()
        return {
            "assignments": {
                row.component_id: str(row.ai_master_id) for row in rows
            }
        }

    def assign_component(
        self, component_id: str, ai_master_id: uuid.UUID | None
    ) -> dict[str, Any]:
        if component_id not in {view.component_id for view in self.projects.components()}:
            raise ApiError(404, "COMPONENT_NOT_FOUND", "component is not configured")
        existing = self.session.get(ComponentAiMaster, component_id)
        if ai_master_id is None:
            if existing is not None:
                self.session.delete(existing)
                self.session.commit()
            return {"component_id": component_id, "ai_master_id": None}
        master = self._get_master(ai_master_id)
        if existing is None:
            self.session.add(
                ComponentAiMaster(component_id=component_id, ai_master_id=master.id)
            )
        elif existing.ai_master_id != master.id:
            existing.ai_master_id = master.id
        self.session.commit()
        return {"component_id": component_id, "ai_master_id": str(master.id)}

    # ── operations views ───────────────────────────────────────────────

    def operations(self, filters: Filters) -> dict[str, Any]:
        """Aggregate adoption tiers per AI Master, plus an 'unassigned' bucket."""
        components = self._components_with_rate(filters)
        assignments = {
            row.component_id: row.ai_master_id
            for row in self.session.scalars(select(ComponentAiMaster)).all()
        }
        masters = {
            master.id: master
            for master in self.session.scalars(select(AiMaster)).all()
        }
        buckets: dict[uuid.UUID | None, list[dict[str, Any]]] = {}
        for component in components:
            master_id = assignments.get(component["component_id"])
            if master_id is not None and master_id not in masters:
                master_id = None  # dangling assignment: treat as unassigned
            buckets.setdefault(master_id, []).append(component)

        # Preserve real masters in name order; the unassigned bucket goes last.
        ordered_ids = sorted(masters, key=lambda mid: masters[mid].name)
        cards = []
        for master_id in ordered_ids:
            cards.append(
                self._card_payload(
                    master_id=str(master_id),
                    name=masters[master_id].name,
                    components=buckets.get(master_id, []),
                )
            )
        unassigned = buckets.get(None, [])
        if unassigned:
            cards.append(
                self._card_payload(
                    master_id=None,
                    name=UNASSIGNED_MASTER_LABEL,
                    components=unassigned,
                )
            )
        return {"items": cards}

    def master_components(
        self, master_id: uuid.UUID, filters: Filters
    ) -> dict[str, Any]:
        master = self._get_master(master_id)
        components = self._components_with_rate(filters)
        assigned = {
            row.component_id
            for row in self.session.scalars(
                select(ComponentAiMaster).where(
                    ComponentAiMaster.ai_master_id == master.id
                )
            ).all()
        }
        rows = [
            _component_base(component)
            for component in components
            if component["component_id"] in assigned
        ]
        rows.sort(key=lambda row: row["name"])
        return {
            "ai_master_id": str(master.id),
            "name": master.name,
            "items": rows,
        }

    # ── helpers ────────────────────────────────────────────────────────

    def _get_master(self, master_id: uuid.UUID) -> AiMaster:
        master = self.session.get(AiMaster, master_id)
        if master is None:
            raise ApiError(404, "AI_MASTER_NOT_FOUND", "AI Master was not found")
        return master

    def _component_counts_by_master(self) -> dict[uuid.UUID, int]:
        rows = self.session.execute(
            select(ComponentAiMaster.ai_master_id).where(
                ComponentAiMaster.ai_master_id.is_not(None)
            )
        ).scalars().all()
        counts: dict[uuid.UUID, int] = {}
        for master_id in rows:
            counts[master_id] = counts.get(master_id, 0) + 1
        return counts

    def _components_with_rate(self, filters: Filters) -> list[dict[str, Any]]:
        """Return every configured component (yaml) with its adoption metrics.

        Only components declared in projects.yaml are considered; the synthetic
        "unassigned component" bucket is excluded because it cannot be owned.
        """
        summary = self._query.components_summary(filters)
        by_id = {
            item["component_id"]: item for item in summary.get("items", [])
        }
        result = []
        for view in self.projects.components():
            item = by_id.get(view.component_id)
            result.append(
                _component_base(
                    item
                    if item is not None
                    else {
                        "component_id": view.component_id,
                        "name": view.name,
                        "se": view.se,
                        "used_aaw": False,
                        "effective_lines": 0,
                        "attribution_rate_80": None,
                    }
                )
            )
        return result

    def _card_payload(
        self,
        *,
        master_id: str | None,
        name: str,
        components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        counts = {"none": 0, "three": 0, "five": 0, "no_data": 0}
        required_rates: list[float] = []
        for component in components:
            tier = component["tier"]
            counts[tier] += 1
            if tier in ("three", "five"):
                rate = component["attribution_rate_80"]
                if rate is not None:
                    required_rates.append(rate)
        return {
            "ai_master_id": master_id,
            "name": name,
            "total_components": len(components),
            "tier_counts": counts,
            "lowest_required_rate": min(required_rates) if required_rates else None,
        }
