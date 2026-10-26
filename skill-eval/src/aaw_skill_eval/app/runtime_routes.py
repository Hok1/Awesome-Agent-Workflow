from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from aaw_skill_eval.contracts.providers import DESIGNERS, JUDGES, RUNNERS, RUNTIME_FACTORIES
from aaw_skill_eval.errors import EvalError

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


def build_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

    @router.get("/agents")
    def agents():
        items = []
        for key, factory in RUNTIME_FACTORIES.items():
            info = factory(settings).payload(ensure_profiles=True)
            items.append(
                {
                    "id": key,
                    "name": "Chrys" if key == "chrys" else key,
                    "roles": [
                        role
                        for role, registry in (
                            ("runner", RUNNERS),
                            ("judge", JUDGES),
                            ("designer", DESIGNERS),
                        )
                        if key in registry
                    ],
                    "available": info.get("available", False),
                    "version": info.get("version"),
                    "error": info.get("error"),
                    "models": [
                        {field: model.get(field) for field in ("id", "name", "active", "modelId")}
                        for model in info.get("models", [])
                    ],
                }
            )
        return {"items": items}

    @router.get("/directories")
    def directories(path: str = ""):
        if not path and os.name == "nt":
            return {
                "path": "",
                "parent": None,
                "items": [
                    {"name": f"{letter}:\\", "path": f"{letter}:\\"}
                    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    if Path(f"{letter}:\\").is_dir()
                ],
            }
        root = Path(path).expanduser().resolve() if path else Path.home()
        if not root.is_dir():
            raise EvalError("DIRECTORY_NOT_FOUND", "目录不存在", status_code=404)
        try:
            children = sorted(
                (p for p in root.iterdir() if p.is_dir() and not p.is_symlink()),
                key=lambda p: p.name.casefold(),
            )
        except OSError as exc:
            raise EvalError("DIRECTORY_UNREADABLE", "无法读取目录", status_code=422) from exc
        return {
            "path": str(root),
            "parent": str(root.parent) if root.parent != root else None,
            "items": [{"name": p.name, "path": str(p)} for p in children[:1000]],
        }

    return router
