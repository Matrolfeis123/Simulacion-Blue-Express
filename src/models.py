from __future__ import annotations

from dataclasses import dataclass
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
    os_count_by_exit: Dict[str, int]

    ready_time: float = 0.0
    pickup_time: float = 0.0
    return_time: float = 0.0
    travel_distance_total: float = 0.0
    travel_time_total: float = 0.0
    release_time_total: float = 0.0
    queue_time_total: float = 0.0
    cycle_time_total: float = 0.0
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
    """
    Relacion entre tiempos
    ----------------------
    simulation_horizon : tiempo TOTAL que corre la simulacion (segundos).
    warmup_time        : periodo inicial excluido de KPIs (segundos).
                         Debe ser estrictamente menor que simulation_horizon.

    Ventana de medicion efectiva = simulation_horizon - warmup_time

    Ejemplos
    --------
    Sin warmup:        horizon=3600, warmup=0    -> mide 3600 s
    Warmup 10 min:     horizon=3600, warmup=600  -> mide 3000 s
    Warmup 1h + 1h:    horizon=7200, warmup=3600 -> mide 3600 s
    """
    simulation_horizon: float
    warmup_time: float
    n_bots: int
    n_receiving_operators: int
    empty_rack_initial_inventory: int
    random_seed: int = 42

    effective_speed_mps: float = 0.9
    pallet_load_unload_time_s: float = 30.0
    turn_time_s: float = 5.0

    exit_queue_capacity: Optional[int] = None
    ready_rack_buffer_capacity: Optional[int] = None
    consolidation_check_interval_s: float = 0.5

    def __post_init__(self) -> None:
        if self.warmup_time < 0:
            raise ValueError("warmup_time no puede ser negativo.")
        if self.warmup_time >= self.simulation_horizon:
            raise ValueError(
                f"warmup_time ({self.warmup_time}s) debe ser menor que "
                f"simulation_horizon ({self.simulation_horizon}s). "
                f"Ventana de medicion efectiva seria <= 0."
            )

    @property
    def effective_horizon(self) -> float:
        """Duracion de la ventana de medicion (segundos)."""
        return self.simulation_horizon - self.warmup_time