"""
Tests unitarios de geometry.py (modelo refinado).
Calibrado contra el Excel real:
    EXIT_1=14.9m, EXIT_19=115.7m, EXIT_20=19.2m, EXIT_32=108.0m
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geometry import BoardGeometry, Geometry


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
        d_exit_off_U_m=2.5,
        n_turns_exit_off_U=1,
        d_exit_off_L_m=2.5,
        n_turns_exit_off_L=1,
        d_exit_on_U_m=2.5,
        n_turns_exit_on_U=1,
        d_exit_on_L_m=2.5,
        n_turns_exit_on_L=1,
        d_exit_on_R_m=2.5,
        n_turns_exit_on_R=1,
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


def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, abs_tol=tol)


# ------------------------------------------------------------------
def test_wing_of():
    g = _make_geometry()
    assert g.wing_of("EXIT_1") == "upper"
    assert g.wing_of("EXIT_19") == "upper"
    assert g.wing_of("EXIT_20") == "lower"
    assert g.wing_of("EXIT_32") == "lower"


def test_position_on_wing():
    g = _make_geometry()
    assert _approx(g.position_on_wing("EXIT_1"), 0.0)
    assert _approx(g.position_on_wing("EXIT_2"), 5.6)
    assert _approx(g.position_on_wing("EXIT_19"), 18 * 5.6)
    assert _approx(g.position_on_wing("EXIT_20"), 0.0)
    assert _approx(g.position_on_wing("EXIT_32"), 12 * 7.4)


def test_loop_order_upper_only():
    g = _make_geometry()
    upper, lower = g.loop_order(["EXIT_5", "EXIT_19", "EXIT_1"])
    assert upper == ["EXIT_1", "EXIT_5", "EXIT_19"]
    assert lower == []


def test_loop_order_lower_only():
    g = _make_geometry()
    upper, lower = g.loop_order(["EXIT_28", "EXIT_20", "EXIT_32"])
    assert upper == []
    assert lower == ["EXIT_32", "EXIT_28", "EXIT_20"]


def test_loop_order_both_wings():
    g = _make_geometry()
    upper, lower = g.loop_order(["EXIT_21", "EXIT_5", "EXIT_10"])
    assert upper == ["EXIT_5", "EXIT_10"]
    assert lower == ["EXIT_21"]


def test_wing_composition():
    g = _make_geometry()
    assert g.wing_composition(["EXIT_5", "EXIT_10"]) == "upper_only"
    assert g.wing_composition(["EXIT_21", "EXIT_30"]) == "lower_only"
    assert g.wing_composition(["EXIT_5", "EXIT_21"]) == "both"
    assert g.wing_composition([]) == "empty"


def test_distance_along_wing():
    g = _make_geometry()
    assert _approx(g.distance_along_wing(0.0, "EXIT_5", "upper"), 4 * 5.6)
    assert _approx(g.distance_along_wing(4 * 5.6, "EXIT_10", "upper"), 5 * 5.6)


def test_distance_along_wing_invalid_direction():
    g = _make_geometry()
    try:
        g.distance_along_wing(50.0, "EXIT_1", "upper")
    except ValueError:
        return
    raise AssertionError("Deberia haber lanzado ValueError")


def test_distance_along_R():
    g = _make_geometry()
    assert _approx(g.distance_along_R(100.8, 0.0), 100.8)
    assert _approx(g.distance_along_R(0.0, 0.0), 0.0)


def test_transit_time():
    g = _make_geometry()
    assert _approx(g.transit_time(10.0, 2), 10.0 / 0.9 + 10.0)


def test_distance_reception_to_exit_upper():
    """EXIT_1 = 14.9m, EXIT_19 = 115.7m (calibracion vs Excel viejo)."""
    g = _make_geometry()
    assert _approx(g.distance_reception_to_exit("EXIT_1"), 14.9)
    assert _approx(g.distance_reception_to_exit("EXIT_19"), 115.7)


def test_distance_reception_to_exit_lower():
    """EXIT_20 = 19.2m, EXIT_32 = 108.0m."""
    g = _make_geometry()
    assert _approx(g.distance_reception_to_exit("EXIT_20"), 19.2)
    assert _approx(g.distance_reception_to_exit("EXIT_32"), 108.0)


def test_choose_first_wing_only_upper():
    g = _make_geometry()
    assert g.choose_first_wing(["EXIT_5"], []) == "upper"


def test_choose_first_wing_only_lower():
    g = _make_geometry()
    assert g.choose_first_wing([], ["EXIT_25"]) == "lower"


def test_choose_first_wing_both_upper_closer():
    """[S.5, S.25]: S.5 esta a 34.8m, S.25 a 53.7m -> upper primero."""
    g = _make_geometry()
    upper, lower = g.loop_order(["EXIT_5", "EXIT_25"])
    assert g.choose_first_wing(upper, lower) == "upper"


def test_choose_first_wing_both_lower_closer():
    """[S.19, S.20]: S.19 a 115.7m, S.20 a 19.2m -> lower primero."""
    g = _make_geometry()
    upper, lower = g.loop_order(["EXIT_19", "EXIT_20"])
    assert g.choose_first_wing(upper, lower) == "lower"


def test_choose_first_wing_empty():
    g = _make_geometry()
    assert g.choose_first_wing([], []) is None


# ------------------------------------------------------------------
def main():
    tests = [
        test_wing_of,
        test_position_on_wing,
        test_loop_order_upper_only,
        test_loop_order_lower_only,
        test_loop_order_both_wings,
        test_wing_composition,
        test_distance_along_wing,
        test_distance_along_wing_invalid_direction,
        test_distance_along_R,
        test_transit_time,
        test_distance_reception_to_exit_upper,
        test_distance_reception_to_exit_lower,
        test_choose_first_wing_only_upper,
        test_choose_first_wing_only_lower,
        test_choose_first_wing_both_upper_closer,
        test_choose_first_wing_both_lower_closer,
        test_choose_first_wing_empty,
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
