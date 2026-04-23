from __future__ import annotations

from models import SimulationConfig


def build_peak_config() -> SimulationConfig:
    return SimulationConfig(
        simulation_horizon=1.138888889*3600.0,           # 1 hora
        warmup_time= 500.0,              # 1 hora de warmup para alcanzar estado estacionario
        n_bots=45,
        n_receiving_operators=20,
        empty_rack_initial_inventory=60,
        random_seed=42,
        effective_speed_mps=1,
        pallet_load_unload_time_s=30.0,
        turn_time_s=5.0,
        exit_queue_capacity=None,
        ready_rack_buffer_capacity=None,
        consolidation_check_interval_s=0.5,
    )


def build_bau_config() -> SimulationConfig:
    return SimulationConfig(
        simulation_horizon=3600.0,           # 1 hora
        warmup_time=0.0,
        n_bots=20,
        n_receiving_operators=10,
        empty_rack_initial_inventory=40,
        random_seed=42,
        effective_speed_mps=0.9,
        pallet_load_unload_time_s=30.0,
        turn_time_s=5.0,
        exit_queue_capacity=None,
        ready_rack_buffer_capacity=None,
        consolidation_check_interval_s=0.5,
    )
