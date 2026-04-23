from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

import pandas as pd

from models import OS, RackMission


class MetricsCollector:
    def __init__(self) -> None:
        self.os_arrivals: List[Dict[str, Any]] = []
        self.rack_creations: List[Dict[str, Any]] = []
        self.reception_events: List[Dict[str, Any]] = []
        self.exit_queue_events: List[Dict[str, Any]] = []
        self.exit_service_events: List[Dict[str, Any]] = []
        self.travel_audit_events: List[Dict[str, Any]] = []
        self.completed_racks: List[Dict[str, Any]] = []
        self.state_snapshots: List[Dict[str, Any]] = []

    def record_os_arrival(self, os_obj: OS, time: float) -> None:
        self.os_arrivals.append(
            {
                "time": time,
                "os_id": os_obj.os_id,
                "segment": os_obj.segment,
                "destination_id": os_obj.destination_id,
                "exit_id": os_obj.exit_id,
                "zone": os_obj.zone,
            }
        )

    def record_rack_created(self, rack: RackMission, time: float) -> None:
        self.rack_creations.append(
            {
                "time": time,
                "rack_id": rack.rack_id,
                "n_os": rack.n_os,
                "n_stops": rack.n_stops,
                "exit_sequence": list(rack.exit_sequence),
                "segment_mix": dict(rack.segment_mix),
                "os_count_by_exit": dict(rack.os_count_by_exit),
            }
        )

    def record_reception_service_start(self, rack: RackMission, time: float) -> None:
        self.reception_events.append(
            {
                "time": time,
                "event": "start",
                "rack_id": rack.rack_id,
                "n_os": rack.n_os,
            }
        )

    def record_reception_service_end(self, rack: RackMission, time: float) -> None:
        self.reception_events.append(
            {
                "time": time,
                "event": "end",
                "rack_id": rack.rack_id,
                "n_os": rack.n_os,
                "ready_time": rack.ready_time,
            }
        )

    def record_exit_queue(self, exit_id: str, queue_delay_s: float, time: float) -> None:
        self.exit_queue_events.append(
            {
                "time": time,
                "exit_id": exit_id,
                "queue_delay_s": queue_delay_s,
            }
        )

    def record_exit_service(
        self,
        exit_id: str,
        release_time_s: float,
        n_os_stop: int,
        time: float,
    ) -> None:
        self.exit_service_events.append(
            {
                "time": time,
                "exit_id": exit_id,
                "release_time_s": release_time_s,
                "n_os_stop": n_os_stop,
            }
        )

    def record_travel_audit_event(self, event: Dict[str, Any]) -> None:
        self.travel_audit_events.append(event)

    def record_completed_rack(self, rack: RackMission, time: float) -> None:
        self.completed_racks.append(
            {
                "time": time,
                "rack_id": rack.rack_id,
                "creation_time": rack.creation_time,
                "ready_time": rack.ready_time,
                "pickup_time": rack.pickup_time,
                "return_time": rack.return_time,
                "n_os": rack.n_os,
                "n_stops": rack.n_stops,
                "travel_time_total": rack.travel_time_total,
                "release_time_total": rack.release_time_total,
                "queue_time_total": rack.queue_time_total,
                "cycle_time_total": rack.cycle_time_total,
                "exit_sequence": list(rack.exit_sequence),
                "os_count_by_exit": dict(rack.os_count_by_exit),
            }
        )

    def record_state_snapshot(
        self,
        time: float,
        os_buffer_len: int,
        pending_racks_len: int,
        ready_racks_len: int,
        empty_racks_level: float,
    ) -> None:
        self.state_snapshots.append(
            {
                "time": time,
                "os_buffer_len": os_buffer_len,
                "pending_racks_len": pending_racks_len,
                "ready_racks_len": ready_racks_len,
                "empty_racks_level": empty_racks_level,
            }
        )

    def to_dataframes(self) -> Dict[str, pd.DataFrame]:
        return {
            "os_arrivals": pd.DataFrame(self.os_arrivals),
            "rack_creations": pd.DataFrame(self.rack_creations),
            "reception_events": pd.DataFrame(self.reception_events),
            "exit_queue_events": pd.DataFrame(self.exit_queue_events),
            "exit_service_events": pd.DataFrame(self.exit_service_events),
            "travel_audit_events": pd.DataFrame(self.travel_audit_events),
            "completed_racks": pd.DataFrame(self.completed_racks),
            "state_snapshots": pd.DataFrame(self.state_snapshots),
        }