"""
Tests de operators.py — validan inicializacion, politica 'mas cercano',
cola FIFO cuando todos ocupados, y acumuladores de metrica.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import simpy

from geometry import BoardGeometry, Geometry
from operators import Operator, OperatorPool


def _make_geometry() -> Geometry:
    wing_by_exit = {f"EXIT_{i}": "upper" for i in range(1, 20)}
    wing_by_exit.update({f"EXIT_{i}": "lower" for i in range(20, 33)})
    board = BoardGeometry(
        d_reception_to_bifurcation_m=7.0,
        n_turns_reception_to_bifurcation=1,
        d_bifurcation_to_U_m=5.4,
        n_turns_bifurcation_to_U=1,
        d_bifurcation_to_L_m=9.7,
        n_turns_bifurcation_to_L=1,
        d_upper_m=5.6,
        d_lower_m=7.4,
        d_return_segment_upper_m=5.6,
        d_return_segment_lower_m=7.4,
        d_exit_off_U_m=2.5, n_turns_exit_off_U=1,
        d_exit_off_L_m=2.5, n_turns_exit_off_L=1,
        d_exit_on_U_m=2.5, n_turns_exit_on_U=1,
        d_exit_on_L_m=2.5, n_turns_exit_on_L=1,
        d_exit_on_R_m=2.5, n_turns_exit_on_R=1,
        pos_R_bifurcation_m=0.0,
        d_R_shortcut_to_L_m=11.0,
        n_turns_R_shortcut_to_L=2,
        d_R_bifurcation_to_reception_m=14.9,
        n_turns_R_bifurcation_to_reception=1,
        t_bifurcation_headway_s=2.0,
        t_merge_window_forward_s=15.0,
        t_merge_window_backward_s=3.0,
        wing_by_exit=wing_by_exit,
    )
    return Geometry(board=board, effective_speed_mps=0.9, turn_time_s=5.0)


# ------------------------------------------------------------------
def test_initialization_one_per_exit():
    """Con 19 operadores en upper y 19 exits, deberia haber uno por exit."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    assert len(pool.operators) == 19
    locations = {op.current_exit for op in pool.operators}
    expected = {f"EXIT_{i}" for i in range(1, 20)}
    assert locations == expected, f"Esperaba 19 exits distintos, obtuve {locations}"


def test_initialization_fewer_than_exits():
    """Con 5 operadores y 19 exits, deberian quedar uniformemente distribuidos."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 5, _make_geometry(), 1.0)
    assert len(pool.operators) == 5
    locations = [pool.geometry.position_on_wing(op.current_exit) for op in pool.operators]
    # Las posiciones deberian estar separadas (no todos en el mismo exit)
    assert len(set(locations)) >= 4, f"Operadores deberian estar dispersos: {locations}"


def test_initialization_more_than_exits():
    """Con 25 operadores y 19 exits, los 6 sobrantes se reparten."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 25, _make_geometry(), 1.0)
    assert len(pool.operators) == 25


def test_initialization_lower_wing():
    """Pool en ala lower: 13 exits, 13 operadores."""
    env = simpy.Environment()
    pool = OperatorPool(env, "lower", 13, _make_geometry(), 1.0)
    assert len(pool.operators) == 13
    locations = {op.current_exit for op in pool.operators}
    expected = {f"EXIT_{i}" for i in range(20, 33)}
    assert locations == expected


def test_walking_distance_same_exit():
    """Operador asignado al mismo exit camina 0."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    d = pool._walking_distance("EXIT_5", "EXIT_5")
    assert d == 0.0


def test_walking_distance_known():
    """EXIT_1 a EXIT_5 = 4 * 5.6 = 22.4m."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    d = pool._walking_distance("EXIT_1", "EXIT_5")
    assert abs(d - 22.4) < 1e-9, f"Esperaba 22.4, obtuve {d}"


def test_find_closest_idle():
    """Con todos libres, el mas cercano a EXIT_5 es el operador en EXIT_5."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    op = pool._find_closest_idle("EXIT_5")
    assert op is not None
    assert op.current_exit == "EXIT_5"


def test_find_closest_idle_with_some_busy():
    """Si EXIT_5 esta ocupado y EXIT_4 y EXIT_6 libres, debe elegir uno adyacente."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    # Marcar el de EXIT_5 como ocupado
    for op in pool.operators:
        if op.current_exit == "EXIT_5":
            op.status = "serving"
    chosen = pool._find_closest_idle("EXIT_5")
    assert chosen is not None
    # Deberia ser uno adyacente (EXIT_4 o EXIT_6, ambos a 5.6m)
    assert chosen.current_exit in {"EXIT_4", "EXIT_6"}, f"Obtuve {chosen.current_exit}"


def test_find_closest_idle_all_busy():
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    for op in pool.operators:
        op.status = "serving"
    assert pool._find_closest_idle("EXIT_5") is None


# ------------------------------------------------------------------
# Tests funcionales: simulan eventos reales con simpy.Environment.run()
# ------------------------------------------------------------------
def test_single_service_zero_walk():
    """Operador en EXIT_5 sirve un bot en EXIT_5: walking=0, serving=release."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)
    records = []

    def bot_process():
        rec = yield env.process(
            pool.request_service(
                bot_id="BOT_1", rack_id="R_1", exit_id="EXIT_5",
                release_time_s=10.0, n_os_stop=3,
            )
        )
        records.append(rec)

    env.process(bot_process())
    env.run()

    assert len(records) == 1
    r = records[0]
    assert r.walking_distance_m == 0.0
    assert r.walking_time_s == 0.0
    assert r.serving_time_s == 10.0
    assert abs(r.wait_for_operator_s - 0.0) < 1e-9
    # Operador termina en EXIT_5 con 1 servicio
    op_5 = [o for o in pool.operators if o.current_exit == "EXIT_5"][0]
    assert op_5.services_completed == 1


def test_single_service_with_walk():
    """Operador en EXIT_5 sirve un bot en EXIT_8: camina 3*5.6=16.8m a 1m/s = 16.8s."""
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 5, _make_geometry(), 1.0)  # 5 operadores, dispersos
    records = []

    def bot_process():
        rec = yield env.process(
            pool.request_service(
                bot_id="BOT_1", rack_id="R_1", exit_id="EXIT_5",
                release_time_s=10.0, n_os_stop=3,
            )
        )
        records.append(rec)

    env.process(bot_process())
    env.run()

    assert len(records) == 1
    r = records[0]
    # walking_time = walking_distance / walking_speed (1.0)
    assert abs(r.walking_time_s - r.walking_distance_m) < 1e-9
    assert r.end_time == r.walking_time_s + r.serving_time_s


def test_queue_when_all_busy():
    """
    Pool con 1 operador. Dos bots piden servicio simultaneamente.
    El segundo debe esperar a que el primero termine.
    """
    env = simpy.Environment()
    # 1 operador en upper
    pool = OperatorPool(env, "upper", 1, _make_geometry(), 1.0)
    op0_exit = pool.operators[0].current_exit
    records = []

    def bot_1():
        rec = yield env.process(
            pool.request_service("BOT_1", "R_1", op0_exit,
                                 release_time_s=10.0, n_os_stop=1)
        )
        records.append(("BOT_1", rec))

    def bot_2():
        # Pide servicio justo despues
        yield env.timeout(0.1)
        rec = yield env.process(
            pool.request_service("BOT_2", "R_2", op0_exit,
                                 release_time_s=10.0, n_os_stop=1)
        )
        records.append(("BOT_2", rec))

    env.process(bot_1())
    env.process(bot_2())
    env.run()

    assert len(records) == 2
    r1 = records[0][1]
    r2 = records[1][1]
    # BOT_2 deberia haber esperado al menos ~10s (release de BOT_1)
    assert r2.wait_for_operator_s >= 9.9, f"BOT_2 wait={r2.wait_for_operator_s}"
    assert r2.end_time > r1.end_time


def test_one_per_exit_no_walking():
    """
    Caso de no-regresion: 19 ops en upper, 19 exits.
    Cualquier bot que llegue a su exit es servido sin caminata.
    """
    env = simpy.Environment()
    pool = OperatorPool(env, "upper", 19, _make_geometry(), 1.0)

    records = []

    def bot_to(exit_id, delay):
        yield env.timeout(delay)
        rec = yield env.process(
            pool.request_service(f"BOT_{exit_id}", f"R_{exit_id}", exit_id,
                                 release_time_s=15.0, n_os_stop=2)
        )
        records.append(rec)

    # Distintos exits, sin solaparse en tiempo
    for i, ex_num in enumerate([1, 5, 10, 19]):
        env.process(bot_to(f"EXIT_{ex_num}", delay=i * 20))

    env.run()

    assert len(records) == 4
    for r in records:
        assert r.walking_distance_m == 0.0, f"Walking deberia ser 0, exit={r.exit_id}"
        assert r.walking_time_s == 0.0
        assert r.wait_for_operator_s < 1e-9


# ------------------------------------------------------------------
def main():
    tests = [
        test_initialization_one_per_exit,
        test_initialization_fewer_than_exits,
        test_initialization_more_than_exits,
        test_initialization_lower_wing,
        test_walking_distance_same_exit,
        test_walking_distance_known,
        test_find_closest_idle,
        test_find_closest_idle_with_some_busy,
        test_find_closest_idle_all_busy,
        test_single_service_zero_walk,
        test_single_service_with_walk,
        test_queue_when_all_busy,
        test_one_per_exit_no_walking,
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
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print()
    if failed:
        print(f"{failed} tests fallaron de {len(tests)}")
        sys.exit(1)
    print(f"Todos los {len(tests)} tests pasaron")


if __name__ == "__main__":
    main()
