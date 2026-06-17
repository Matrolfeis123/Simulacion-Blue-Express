"""
Test de integracion minimo: verifica que simulation.py con la nueva
arquitectura de OperatorPool puede instanciarse y correr sin errores,
y produce los outputs esperados.

NO depende del metrics.py, models.py, ni run.py reales. Crea stubs.
El objetivo es validar el contrato entre simulation.py y operators.py.
"""
from __future__ import annotations

import sys
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import simpy

from geometry import BoardGeometry, Geometry
from operators import OperatorPool, ServiceRecord


# ----------------------------------------------------------------------
# Stubs minimos de models.py
# ----------------------------------------------------------------------
@dataclass
class OS:
    os_id: str
    arrival_time: float
    segment: str
    destination_id: str
    exit_id: str
    zone: str
    status: str = "waiting"


@dataclass
class RackMission:
    rack_id: str
    creation_time: float
    os_list: list
    n_os: int
    exit_sequence: list
    n_stops: int
    segment_mix: dict
    os_count_by_exit: dict
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
    simulation_horizon: float = 600.0
    warmup_time: float = 0.0
    cooldown_time_s: float = 0.0
    n_bots: int = 5
    n_receiving_operators: int = 3
    empty_rack_initial_inventory: int = 20
    random_seed: int = 42
    effective_speed_mps: float = 0.9
    pallet_load_unload_time_s: float = 30.0
    turn_time_s: float = 5.0
    exit_queue_capacity: Optional[int] = None
    ready_rack_buffer_capacity: Optional[int] = None
    consolidation_check_interval_s: float = 0.5
    consolidation_threshold_rm: int = 3
    consolidation_threshold_big: int = 2
    consolidation_timeout_rm_s: float = 45.0
    consolidation_timeout_big_s: float = 60.0
    # CAMPOS NUEVOS
    n_operators_upper: int = 19
    n_operators_lower: int = 13
    operator_walking_speed_mps: float = 1.0

    @property
    def arrival_cutoff(self) -> float:
        return self.simulation_horizon - self.cooldown_time_s

    @property
    def effective_horizon(self) -> float:
        return self.arrival_cutoff - self.warmup_time


# ----------------------------------------------------------------------
# Stub minimo de MetricsCollector con record_operator_service
# ----------------------------------------------------------------------
class MetricsCollector:
    def __init__(self):
        self.os_arrivals = []
        self.rack_creations = []
        self.reception_events = []
        self.exit_queue_events = []
        self.exit_queue_length_events = []
        self.exit_service_events = []
        self.travel_audit_events = []
        self.completed_racks = []
        self.state_snapshots = []
        self.operator_service_events = []  # NUEVO

    def record_os_arrival(self, os_obj, time): self.os_arrivals.append((time, os_obj.os_id))
    def record_rack_created(self, rack, time): self.rack_creations.append((time, rack.rack_id))
    def record_reception_service_start(self, rack, time): self.reception_events.append(("start", time, rack.rack_id))
    def record_reception_service_end(self, rack, time): self.reception_events.append(("end", time, rack.rack_id))
    def record_exit_queue(self, exit_id, queue_delay_s, time): self.exit_queue_events.append((time, exit_id, queue_delay_s))
    def record_exit_queue_length_change(self, exit_id, time, delta, event, bot_id, rack_id):
        self.exit_queue_length_events.append((time, exit_id, delta, event, bot_id, rack_id))
    def record_exit_service(self, exit_id, release_time_s, n_os_stop, time): self.exit_service_events.append((time, exit_id, release_time_s, n_os_stop))
    def record_travel_audit_event(self, event): self.travel_audit_events.append(event)
    def record_completed_rack(self, rack, time): self.completed_racks.append((time, rack.rack_id, rack.n_os))
    def record_state_snapshot(self, **kw): self.state_snapshots.append(kw)

    def record_operator_service(self, record: ServiceRecord):
        """NUEVO: registra un servicio individual del pool de operadores."""
        self.operator_service_events.append({
            "operator_id": record.operator_id,
            "bot_id": record.bot_id,
            "rack_id": record.rack_id,
            "exit_id": record.exit_id,
            "request_time": record.request_time,
            "arrival_time": record.arrival_time,
            "end_time": record.end_time,
            "walking_distance_m": record.walking_distance_m,
            "walking_time_s": record.walking_time_s,
            "serving_time_s": record.serving_time_s,
            "wait_for_operator_s": record.wait_for_operator_s,
            "n_os_stop": record.n_os_stop,
            "time": record.end_time,
        })


# ----------------------------------------------------------------------
# Stub minimo de InputModel
# ----------------------------------------------------------------------
class InputModelStub:
    def __init__(self, geometry: Geometry, os_per_hour: float, config: SimulationConfig):
        self.geometry = geometry
        self.os_per_hour = os_per_hour
        self.config = config
        self.rng = random.Random(config.random_seed)
        # Asume distribucion uniforme entre todos los exits para el stub
        self._all_exits = geometry.upper_exits() + geometry.lower_exits()

    def sample_interarrival_time(self, t):
        rate = self.os_per_hour / 3600.0
        return self.rng.expovariate(rate)

    def sample_destination(self):
        return self.rng.choice(self._all_exits)

    def get_exit_for_destination(self, dest):
        return dest  # destination = exit_id en el stub

    def sample_segment_for_destination(self, dest):
        return self.rng.choice(["Regular", "Medium"])

    def sample_zone(self, exit_id):
        return "SCL" if 1 <= int(exit_id.split("_")[1]) <= 19 else "REG"

    def get_rack_prep_time(self, n_os, segment_mix):
        return 20.0 + n_os * 5.0

    def get_release_time(self, n_os_stop):
        return 5.0 + n_os_stop * 6.0

    def get_distance_receiving_to_exit(self, exit_id):
        return self.geometry.legacy_distance_receiving_to_exit(exit_id)

    def get_distance_between_exits(self, e1, e2):
        return self.geometry.legacy_distance_between_exits(e1, e2)

    def get_distance_exit_to_return(self, exit_id):
        return self.geometry.legacy_distance_exit_to_return(exit_id)

    def get_turns_receiving_to_first_exit(self):
        return 2

    def get_turns_between_exits(self):
        return 1

    def get_turns_last_exit_to_return(self):
        return 2

    def get_leg_time_from_distance_and_turns(self, distance_m, n_turns):
        return distance_m / self.config.effective_speed_mps + n_turns * self.config.turn_time_s

    def get_all_exit_ids(self):
        return list(self._all_exits)

    def try_build_rack_from_buffer(self, os_buffer, current_time, rack_id, config):
        if len(os_buffer) < 3:
            return None
        chosen = os_buffer[:3]
        os_buffer[:] = os_buffer[3:]
        exit_counter = {}
        for o in chosen:
            exit_counter[o.exit_id] = exit_counter.get(o.exit_id, 0) + 1
        # Ordenar exits por loop flow (upper asc, lower desc)
        upper_asc, lower_desc = self.geometry.loop_order(list(exit_counter.keys()))
        exit_sequence = upper_asc + lower_desc
        return RackMission(
            rack_id=rack_id,
            creation_time=current_time,
            os_list=chosen,
            n_os=len(chosen),
            exit_sequence=exit_sequence,
            n_stops=len(exit_sequence),
            segment_mix={"Regular": 3},
            os_count_by_exit=exit_counter,
            status="waiting_preparation",
        )


# ----------------------------------------------------------------------
# Setup helpers
# ----------------------------------------------------------------------
def make_geometry():
    wing_by_exit = {f"EXIT_{i}": "upper" for i in range(1, 20)}
    wing_by_exit.update({f"EXIT_{i}": "lower" for i in range(20, 33)})
    board = BoardGeometry(
        d_reception_to_bifurcation_m=7.0, n_turns_reception_to_bifurcation=1,
        d_bifurcation_to_U_m=5.4, n_turns_bifurcation_to_U=1,
        d_bifurcation_to_L_m=9.7, n_turns_bifurcation_to_L=1,
        d_upper_m=5.6, d_lower_m=7.4,
        d_return_segment_upper_m=5.6, d_return_segment_lower_m=7.4,
        d_exit_off_U_m=2.5, n_turns_exit_off_U=1,
        d_exit_off_L_m=2.5, n_turns_exit_off_L=1,
        d_exit_on_U_m=2.5, n_turns_exit_on_U=1,
        d_exit_on_L_m=2.5, n_turns_exit_on_L=1,
        d_exit_on_R_m=2.5, n_turns_exit_on_R=1,
        pos_R_bifurcation_m=0.0,
        d_R_shortcut_to_L_m=11.0, n_turns_R_shortcut_to_L=2,
        d_R_bifurcation_to_reception_m=14.9, n_turns_R_bifurcation_to_reception=1,
        t_bifurcation_headway_s=2.0,
        t_merge_window_forward_s=15.0,
        t_merge_window_backward_s=3.0,
        wing_by_exit=wing_by_exit,
    )
    return Geometry(board=board, effective_speed_mps=0.9, turn_time_s=5.0)


# Inyectar los stubs en sys.modules antes de importar simulation
import types
models_mod = types.ModuleType("models")
models_mod.OS = OS
models_mod.RackMission = RackMission
models_mod.Bot = Bot
models_mod.SimulationConfig = SimulationConfig
sys.modules["models"] = models_mod

inputs_mod = types.ModuleType("inputs")
inputs_mod.InputModel = InputModelStub
sys.modules["inputs"] = inputs_mod

metrics_mod = types.ModuleType("metrics")
metrics_mod.MetricsCollector = MetricsCollector
sys.modules["metrics"] = metrics_mod

# Ahora si, importar simulation
from simulation import WarehouseSimulation, build_and_run_simulation


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_simulation_instantiates():
    """La WarehouseSimulation se puede instanciar con la nueva geometry/pools."""
    geometry = make_geometry()
    config = SimulationConfig(simulation_horizon=100.0, n_bots=2, n_receiving_operators=2,
                              empty_rack_initial_inventory=5)
    input_model = InputModelStub(geometry, os_per_hour=100.0, config=config)
    metrics = MetricsCollector()
    env = simpy.Environment()
    sim = WarehouseSimulation(env, config, input_model, metrics, geometry)
    assert "upper" in sim.operator_pools
    assert "lower" in sim.operator_pools
    assert len(sim.operator_pools["upper"].operators) == 19
    assert len(sim.operator_pools["lower"].operators) == 13


def test_simulation_runs_end_to_end():
    """Una corrida corta completa sin errores, con metricas de operadores."""
    geometry = make_geometry()
    config = SimulationConfig(
        simulation_horizon=600.0, n_bots=3, n_receiving_operators=2,
        empty_rack_initial_inventory=10,
        n_operators_upper=19, n_operators_lower=13,
    )
    input_model = InputModelStub(geometry, os_per_hour=300.0, config=config)
    metrics = build_and_run_simulation(config, input_model, geometry)

    # Verificaciones basicas
    assert hasattr(metrics, "operator_service_events"), "No hay events de operadores"
    assert hasattr(metrics, "operator_summary"), "No hay summary de operadores"
    assert len(metrics.completed_racks) > 0, "No completo ningun rack"
    assert len(metrics.operator_service_events) > 0, "No hay servicios registrados"

    # Con 1 op por exit, walking_time deberia ser 0 en TODOS los servicios
    for ev in metrics.operator_service_events:
        assert ev["walking_time_s"] == 0.0, (
            f"Con 1 op por exit, walking deberia ser 0 pero fue "
            f"{ev['walking_time_s']} para {ev['operator_id']} en {ev['exit_id']}"
        )

    # Summary tiene los 32 operadores (19 + 13)
    upper_summary = metrics.operator_summary["upper"]
    lower_summary = metrics.operator_summary["lower"]
    assert len(upper_summary) == 19
    assert len(lower_summary) == 13

    print(f"  Racks completados: {len(metrics.completed_racks)}")
    print(f"  Servicios registrados: {len(metrics.operator_service_events)}")
    print(f"  Total ops upper: {len(upper_summary)}, lower: {len(lower_summary)}")
    # Mostrar utilizacion de un operador como sanity check
    for s in upper_summary[:3]:
        print(f"    {s['operator_id']}: services={s['services_completed']}, "
              f"util={s['utilization']*100:.1f}%, walking_dist={s['walking_distance_m']:.1f}m")


def test_reduced_operators_causes_walking():
    """Con menos operadores que exits, los operadores caminan."""
    geometry = make_geometry()
    config = SimulationConfig(
        simulation_horizon=600.0, n_bots=4, n_receiving_operators=2,
        empty_rack_initial_inventory=10,
        n_operators_upper=5, n_operators_lower=4,   # MENOS que exits
    )
    input_model = InputModelStub(geometry, os_per_hour=300.0, config=config)
    metrics = build_and_run_simulation(config, input_model, geometry)

    walking_times = [ev["walking_time_s"] for ev in metrics.operator_service_events]
    total_walking = sum(walking_times)
    assert total_walking > 0, f"Esperaba walking > 0 con menos ops que exits"

    n_walked = sum(1 for w in walking_times if w > 0)
    print(f"  Servicios con caminata: {n_walked} / {len(walking_times)}")
    print(f"  Tiempo total caminado: {total_walking:.1f}s")


# ----------------------------------------------------------------------
def main():
    tests = [
        test_simulation_instantiates,
        test_simulation_runs_end_to_end,
        test_reduced_operators_causes_walking,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print()
    if failed:
        print(f"{failed} tests fallaron de {len(tests)}")
        sys.exit(1)
    print(f"Todos los {len(tests)} tests pasaron")


if __name__ == "__main__":
    main()
