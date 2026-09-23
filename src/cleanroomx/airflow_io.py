from __future__ import annotations

import json
from pathlib import Path

from .airflow_balance import AirBalanceProject, RoomAirflow, TransferAirflow


def air_balance_project_from_dict(data: dict) -> AirBalanceProject:
    rooms = tuple(RoomAirflow(**item) for item in data["rooms"])
    transfers = tuple(TransferAirflow(**item) for item in data.get("transfers", []))
    return AirBalanceProject(
        name=data["name"],
        rooms=rooms,
        transfers=transfers,
    )


def load_air_balance_project(path: str | Path) -> AirBalanceProject:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return air_balance_project_from_dict(data)
