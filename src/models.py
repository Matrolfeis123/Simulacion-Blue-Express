from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class OS:
    os_id: str
    arrival_time: float
    segment: str
    destination_id: str
    exit_id: str
    zone: str
    status: str = "waiting_consolidation"


@dataclass
class RackMission:
    rack_id: str
    creation_time: float
    os_list: List[OS]
    n_os: int
    exit_sequence: List[str]
    n_stops: int
    segment_mix: Dict[str, int]

    # Clave para la V1: cuántas OS se descargan en cada salida
    os_count_by_exit: Dict[str, int]

    # Tiempos emergentes
    ready_time: float = 0.0
    pickup_time: float = 0.0
    return_time: float = 0.0
    travel_distance_total: float = 0.0
    travel_time_total: float = 0.0
    release_time_total: float = 0.0
    queue_time_total: float = 0.0
    cycle_time_total: float = 0.0

    # Estado
    status: str = "building"


@dataclass
class Bot:
    bot_id: str
    status: str = "idle"
    current_location: str = "empty_rack_zone"
    current_rack_id: Optional[str] = None
    total_busy_time: float = 0.0
    total_idle_time: float = 0.0
    trip_count: int = 0
    last_state_change: float = 0.0


@dataclass
class SimulationConfig:
    simulation_horizon: float
    warmup_time: float
    n_bots: int
    n_receiving_operators: int
    empty_rack_initial_inventory: int
    random_seed: int = 42

    # Parámetros bot
    effective_speed_mps: float = 0.8
    pallet_load_unload_time_s: float = 20.0
    turn_time_s: float = 2.0

    # Capacidad de cola por salida (None = infinita)
    exit_queue_capacity: Optional[int] = None

    # Capacidad ready buffer (None = infinita)
    ready_rack_buffer_capacity: Optional[int] = None

    # Polling consolidación
    consolidation_check_interval_s: float = 0.5