from __future__ import annotations

from dataclasses import dataclass


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


@dataclass(frozen=True)
class RoomAirflow:
    name: str
    supply_airflow_m3_h: float
    return_airflow_m3_h: float = 0.0
    exhaust_airflow_m3_h: float = 0.0
    min_net_offset_m3_h: float | None = None
    max_net_offset_m3_h: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for field_name in (
            "supply_airflow_m3_h",
            "return_airflow_m3_h",
            "exhaust_airflow_m3_h",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative(getattr(self, field_name), field_name),
            )

        if self.min_net_offset_m3_h is not None:
            object.__setattr__(
                self, "min_net_offset_m3_h", float(self.min_net_offset_m3_h)
            )
        if self.max_net_offset_m3_h is not None:
            object.__setattr__(
                self, "max_net_offset_m3_h", float(self.max_net_offset_m3_h)
            )
        if (
            self.min_net_offset_m3_h is not None
            and self.max_net_offset_m3_h is not None
            and self.min_net_offset_m3_h > self.max_net_offset_m3_h
        ):
            raise ValueError(
                "min_net_offset_m3_h cannot exceed max_net_offset_m3_h"
            )


@dataclass(frozen=True)
class TransferAirflow:
    from_room: str
    to_room: str
    airflow_m3_h: float

    def __post_init__(self) -> None:
        if not self.from_room.strip() or not self.to_room.strip():
            raise ValueError("transfer-airflow room names cannot be empty")
        if self.from_room == self.to_room:
            raise ValueError("transfer airflow cannot start and end in the same room")
        value = float(self.airflow_m3_h)
        if value <= 0:
            raise ValueError("transfer airflow must be > 0")
        object.__setattr__(self, "airflow_m3_h", value)


@dataclass(frozen=True)
class AirBalanceProject:
    name: str
    rooms: tuple[RoomAirflow, ...]
    transfers: tuple[TransferAirflow, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name cannot be empty")
        if not self.rooms:
            raise ValueError("project must contain at least one room")

        names = [room.name for room in self.rooms]
        if len(names) != len(set(names)):
            raise ValueError("room names must be unique")

        known = set(names)
        seen_edges: set[tuple[str, str]] = set()
        for transfer in self.transfers:
            if transfer.from_room not in known or transfer.to_room not in known:
                raise ValueError(
                    "transfer airflow references an unknown room: "
                    f"{transfer.from_room} -> {transfer.to_room}"
                )
            edge = (transfer.from_room, transfer.to_room)
            if edge in seen_edges:
                raise ValueError(
                    "duplicate transfer-airflow link: "
                    f"{transfer.from_room} -> {transfer.to_room}"
                )
            seen_edges.add(edge)


def _tendency(net_offset_m3_h: float) -> str:
    if net_offset_m3_h > 0:
        return "positive"
    if net_offset_m3_h < 0:
        return "negative"
    return "neutral"


def analyze_air_balance(project: AirBalanceProject) -> dict:
    transfer_in = {room.name: 0.0 for room in project.rooms}
    transfer_out = {room.name: 0.0 for room in project.rooms}

    for transfer in project.transfers:
        transfer_out[transfer.from_room] += transfer.airflow_m3_h
        transfer_in[transfer.to_room] += transfer.airflow_m3_h

    room_results: list[dict] = []
    all_requirements_pass = True

    for room in project.rooms:
        entering = room.supply_airflow_m3_h + transfer_in[room.name]
        leaving = (
            room.return_airflow_m3_h
            + room.exhaust_airflow_m3_h
            + transfer_out[room.name]
        )
        net_offset = entering - leaving
        checks: list[dict] = []

        if room.min_net_offset_m3_h is not None:
            passed = net_offset >= room.min_net_offset_m3_h
            checks.append(
                {
                    "requirement": "min_net_offset_m3_h",
                    "limit": room.min_net_offset_m3_h,
                    "observed": round(net_offset, 3),
                    "passed": passed,
                }
            )
            all_requirements_pass = all_requirements_pass and passed

        if room.max_net_offset_m3_h is not None:
            passed = net_offset <= room.max_net_offset_m3_h
            checks.append(
                {
                    "requirement": "max_net_offset_m3_h",
                    "limit": room.max_net_offset_m3_h,
                    "observed": round(net_offset, 3),
                    "passed": passed,
                }
            )
            all_requirements_pass = all_requirements_pass and passed

        room_results.append(
            {
                "name": room.name,
                "supply_airflow_m3_h": round(room.supply_airflow_m3_h, 3),
                "return_airflow_m3_h": round(room.return_airflow_m3_h, 3),
                "exhaust_airflow_m3_h": round(room.exhaust_airflow_m3_h, 3),
                "transfer_in_airflow_m3_h": round(transfer_in[room.name], 3),
                "transfer_out_airflow_m3_h": round(transfer_out[room.name], 3),
                "total_entering_airflow_m3_h": round(entering, 3),
                "total_leaving_airflow_m3_h": round(leaving, 3),
                "net_offset_m3_h": round(net_offset, 3),
                "pressurization_tendency": _tendency(net_offset),
                "checks": checks,
                "requirements_pass": all(check["passed"] for check in checks),
            }
        )

    total_supply = sum(room.supply_airflow_m3_h for room in project.rooms)
    total_return = sum(room.return_airflow_m3_h for room in project.rooms)
    total_exhaust = sum(room.exhaust_airflow_m3_h for room in project.rooms)
    facility_external_offset = total_supply - total_return - total_exhaust
    sum_room_offsets = sum(room["net_offset_m3_h"] for room in room_results)

    return {
        "project": project.name,
        "rooms": room_results,
        "transfers": [
            {
                "from_room": transfer.from_room,
                "to_room": transfer.to_room,
                "airflow_m3_h": round(transfer.airflow_m3_h, 3),
            }
            for transfer in project.transfers
        ],
        "total_supply_airflow_m3_h": round(total_supply, 3),
        "total_return_airflow_m3_h": round(total_return, 3),
        "total_exhaust_airflow_m3_h": round(total_exhaust, 3),
        "facility_external_offset_m3_h": round(facility_external_offset, 3),
        "sum_room_net_offsets_m3_h": round(sum_room_offsets, 3),
        "internal_transfer_conservation_error_m3_h": round(
            sum_room_offsets - facility_external_offset, 9
        ),
        "all_requirements_pass": all_requirements_pass,
        "engineering_note": (
            "Net airflow offset indicates a pressurization tendency only. Actual room "
            "differential pressure depends on envelope leakage, openings, adjacent "
            "spaces, controls, and commissioning; offset is not converted to pressure."
        ),
    }
