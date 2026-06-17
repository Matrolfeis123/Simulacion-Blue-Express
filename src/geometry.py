"""
Geometria del tablero RIL-M (V1.5, modelo refinado).

Carriles fisicos:
    U = ida ala upper (S.1..S.19), unidireccional D->I
    L = ida ala lower (S.20..S.32), unidireccional D->I
    R = vuelta interna, unidireccional I->D, con bifurcacion interna cerca
        de Reception que ofrece dos salidas:
            (a) hacia Reception (tramo final)
            (b) hacia entrada del carril L (atajo R->L)

Conectividad:
    Reception
       |
       v
    Bifurcacion inicial ----> entrada U
       |                  +-> entrada L
       v
    (eleccion 1ra ala)
       |
       v
    ... recorrido por carriles ...

    Cada salida tiene 4 conexiones fisicas:
        off-ramp desde carril de ida (entrada a cola)
        on-ramp a carril de ida   (= seguir en misma ala)
        on-ramp a carril R         (= terminar la ala)
        (off-ramp desde R no se usa en este modelo)

Convencion de posiciones (sistema 1D por carril):
    U: pos(S.1)=0, pos(S.k) = (k-1) * d_upper          [crece hacia izq]
    L: pos(S.20)=0, pos(S.k) = (k-20) * d_lower        [crece hacia izq]
    R: pos=0 en el extremo derecho (cerca de Reception),
       crece hacia la izquierda. Cada exit tiene un merge point en R
       en la MISMA posicion absoluta que en su carril de ida.

Logica del recorrido:
    1. Determinar 1ra ala visitada (la cuya 1ra parada esta mas cerca de
       Reception, comparando distancia total Reception -> 1ra parada).
    2. Recorrer 1ra ala: dentro de la misma ala, despues de cada parada
       (que no sea la ultima de esa ala), VOLVER al carril de ida (NO a R).
       Despues de la ultima parada de la 1ra ala, subir a R.
    3. Si hay 2da ala: avanzar por R hasta pos_R_bifurcation, tomar el
       atajo hacia la entrada del carril de la 2da ala, y recorrer 2da ala.
    4. Despues de la ultima parada del recorrido, subir a R y retornar
       desde pos_R_bifurcation hacia Reception.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Wing = Literal["upper", "lower"]
Lane = Literal["U", "R", "L"]


@dataclass(frozen=True)
class BoardGeometry:
    """Parametros geometricos crudos del tablero, leidos desde Excel."""

    # Reception -> bifurcacion inicial
    d_reception_to_bifurcation_m: float
    n_turns_reception_to_bifurcation: int

    # Bifurcacion inicial -> entradas de carriles de ida
    d_bifurcation_to_U_m: float
    n_turns_bifurcation_to_U: int
    d_bifurcation_to_L_m: float
    n_turns_bifurcation_to_L: int

    # Espaciamientos dentro de cada carril
    d_upper_m: float
    d_lower_m: float
    d_return_segment_upper_m: float
    d_return_segment_lower_m: float

    # Off-ramps y on-ramps diferenciados
    d_exit_off_U_m: float
    n_turns_exit_off_U: int
    d_exit_off_L_m: float
    n_turns_exit_off_L: int
    d_exit_on_U_m: float
    n_turns_exit_on_U: int
    d_exit_on_L_m: float
    n_turns_exit_on_L: int
    d_exit_on_R_m: float
    n_turns_exit_on_R: int

    # Bifurcacion interna en R + atajo R->L
    pos_R_bifurcation_m: float
    d_R_shortcut_to_L_m: float
    n_turns_R_shortcut_to_L: int
    d_R_bifurcation_to_reception_m: float
    n_turns_R_bifurcation_to_reception: int

    # Parametros temporales
    t_bifurcation_headway_s: float
    t_merge_window_forward_s: float
    t_merge_window_backward_s: float

    # Mapeo exit_id -> ala
    wing_by_exit: dict[str, Wing] = field(default_factory=dict)


class Geometry:
    """
    Calculadora pura de geometria y orden de paradas.
    NO mantiene estado de simulacion.
    """

    def __init__(
        self,
        board: BoardGeometry,
        effective_speed_mps: float,
        turn_time_s: float,
    ) -> None:
        if effective_speed_mps <= 0:
            raise ValueError("effective_speed_mps debe ser > 0")
        if turn_time_s < 0:
            raise ValueError("turn_time_s debe ser >= 0")

        self.board = board
        self.speed = effective_speed_mps
        self.turn_time_s = turn_time_s

        self._upper_exits = sorted(
            (e for e, w in board.wing_by_exit.items() if w == "upper"),
            key=self._exit_num,
        )
        self._lower_exits = sorted(
            (e for e, w in board.wing_by_exit.items() if w == "lower"),
            key=self._exit_num,
        )

        self._pos_U: dict[str, float] = {
            e: i * board.d_upper_m for i, e in enumerate(self._upper_exits)
        }
        self._pos_L: dict[str, float] = {
            e: i * board.d_lower_m for i, e in enumerate(self._lower_exits)
        }

        self._U_length = (
            (len(self._upper_exits) - 1) * board.d_upper_m if self._upper_exits else 0.0
        )
        self._L_length = (
            (len(self._lower_exits) - 1) * board.d_lower_m if self._lower_exits else 0.0
        )

        # Posiciones en R: cada exit tiene un merge point en R en la misma
        # posicion absoluta que su posicion en el carril de ida.
        self._pos_R: dict[str, float] = {}
        for e, p in self._pos_U.items():
            self._pos_R[e] = p
        for e, p in self._pos_L.items():
            self._pos_R[e] = p

    # ------------------------------------------------------------------
    # Helpers basicos
    # ------------------------------------------------------------------
    @staticmethod
    def _exit_num(exit_id: str) -> int:
        return int(exit_id.split("_")[-1])

    def wing_of(self, exit_id: str) -> Wing:
        if exit_id not in self.board.wing_by_exit:
            raise KeyError(f"Exit '{exit_id}' no tiene wing asignada")
        return self.board.wing_by_exit[exit_id]

    def upper_exits(self) -> list[str]:
        return list(self._upper_exits)

    def lower_exits(self) -> list[str]:
        return list(self._lower_exits)

    # ------------------------------------------------------------------
    # Posiciones
    # ------------------------------------------------------------------
    def position_on_wing(self, exit_id: str) -> float:
        if exit_id in self._pos_U:
            return self._pos_U[exit_id]
        if exit_id in self._pos_L:
            return self._pos_L[exit_id]
        raise KeyError(f"Exit '{exit_id}' no esta en ningun carril")

    def position_on_R(self, exit_id: str) -> float:
        if exit_id not in self._pos_R:
            raise KeyError(f"Exit '{exit_id}' no tiene posicion en R")
        return self._pos_R[exit_id]

    @property
    def U_length(self) -> float:
        return self._U_length

    @property
    def L_length(self) -> float:
        return self._L_length

    # ------------------------------------------------------------------
    # Ordenamiento de paradas
    # ------------------------------------------------------------------
    def loop_order(self, exit_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Devuelve (upper_asc, lower_desc).

        upper_asc: paradas en U ordenadas por numero de exit ascendente
                   (S.1 primero porque esta mas cerca de la entrada).
        lower_desc: paradas en L ordenadas por numero de exit descendente
                    (S.32 primero porque esta mas cerca de la entrada de L).

        Aclaracion: para L, la entrada esta en pos=0 (lado derecho).
        S.20 esta en pos=0 (primero por flujo), S.32 esta en pos=12*d_lower.
        Pero el usuario indico que el orden de visita es DESCENDENTE de
        numero de exit, lo cual significa que S.20 esta mas LEJOS de la
        entrada y S.32 mas CERCA. Esto implica que la convencion fisica
        es: en L, S.32 esta cerca de la entrada y S.20 cerca del extremo.
        Reinterpretamos las posiciones de L invirtiendolas.
        """
        upper = [e for e in exit_ids if self.wing_of(e) == "upper"]
        lower = [e for e in exit_ids if self.wing_of(e) == "lower"]
        upper_asc = sorted(upper, key=self._exit_num)
        lower_desc = sorted(lower, key=self._exit_num, reverse=True)
        return upper_asc, lower_desc

    def wing_composition(self, exit_ids: list[str]) -> str:
        if not exit_ids:
            return "empty"
        wings = {self.wing_of(e) for e in exit_ids}
        if wings == {"upper"}:
            return "upper_only"
        if wings == {"lower"}:
            return "lower_only"
        return "both"

    def choose_first_wing(
        self,
        upper_stops: list[str],
        lower_stops: list[str],
    ) -> Wing | None:
        """
        Decide cual ala visita primero basado en la 1ra parada mas cercana
        a Reception (medida en distancia fisica total).

        Returns:
            'upper' o 'lower' si hay paradas, None si ambas listas vacias.
        """
        if not upper_stops and not lower_stops:
            return None
        if not lower_stops:
            return "upper"
        if not upper_stops:
            return "lower"

        # Ambas alas tienen paradas: comparar distancias
        first_upper = upper_stops[0]
        first_lower = lower_stops[0]

        d_to_first_upper = self.distance_reception_to_exit(first_upper)
        d_to_first_lower = self.distance_reception_to_exit(first_lower)

        return "upper" if d_to_first_upper <= d_to_first_lower else "lower"

    # ------------------------------------------------------------------
    # Distancias (alto nivel)
    # ------------------------------------------------------------------
    def distance_reception_to_exit(self, exit_id: str) -> float:
        """
        Distancia fisica total desde Reception hasta la cola del exit.
        Reception -> bifurcacion -> entrada carril -> avance -> off-ramp.
        """
        b = self.board
        wing = self.wing_of(exit_id)
        if wing == "upper":
            return (
                b.d_reception_to_bifurcation_m
                + b.d_bifurcation_to_U_m
                + self._pos_U[exit_id]
                + b.d_exit_off_U_m
            )
        return (
            b.d_reception_to_bifurcation_m
            + b.d_bifurcation_to_L_m
            + self._pos_L[exit_id]
            + b.d_exit_off_L_m
        )

    def distance_along_wing(
        self,
        from_pos: float,
        to_exit: str,
        wing: Wing,
    ) -> float:
        target = self._pos_U[to_exit] if wing == "upper" else self._pos_L[to_exit]
        if target < from_pos - 1e-9:
            raise ValueError(
                f"Movimiento contrario al flujo en {wing}: "
                f"from_pos={from_pos:.2f} > pos({to_exit})={target:.2f}"
            )
        return max(0.0, target - from_pos)

    def distance_along_R(self, from_pos: float, to_pos: float) -> float:
        """R va de alta pos (izquierda) a baja pos (derecha)."""
        if to_pos > from_pos + 1e-9:
            raise ValueError(
                f"Movimiento contrario al flujo en R: "
                f"from_pos={from_pos:.2f} < to_pos={to_pos:.2f}"
            )
        return max(0.0, from_pos - to_pos)

    # ------------------------------------------------------------------
    # Tiempo de transito
    # ------------------------------------------------------------------
    def transit_time(self, distance_m: float, n_turns: int) -> float:
        if distance_m < 0:
            raise ValueError("distance_m debe ser >= 0")
        if n_turns < 0:
            raise ValueError("n_turns debe ser >= 0")
        return distance_m / self.speed + n_turns * self.turn_time_s

    # ------------------------------------------------------------------
    # API legacy (puente para simulation.py hasta A.2)
    # ------------------------------------------------------------------
    def legacy_distance_receiving_to_exit(self, exit_id: str) -> float:
        return self.distance_reception_to_exit(exit_id)

    def legacy_distance_between_exits(self, from_exit: str, to_exit: str) -> float:
        """
        Distancia 'como el Excel viejo': solo para mantener simulation.py
        funcional hasta A.2. NO refleja la geometria de tres carriles.
        """
        wing_i = self.wing_of(from_exit)
        wing_j = self.wing_of(to_exit)
        pos_i = self._pos_U[from_exit] if wing_i == "upper" else self._pos_L[from_exit]
        pos_j = self._pos_U[to_exit] if wing_j == "upper" else self._pos_L[to_exit]
        if wing_i == wing_j:
            return abs(pos_j - pos_i)
        # Alas distintas: aproximacion gruesa (en A.2 esto se calcula correctamente)
        return pos_i + pos_j + self.board.d_R_shortcut_to_L_m

    def legacy_distance_exit_to_return(self, exit_id: str) -> float:
        """Aproximacion: exit -> on-ramp R -> bif interna -> Reception."""
        b = self.board
        d_in_R = self.position_on_R(exit_id) - b.pos_R_bifurcation_m
        d_in_R = max(0.0, d_in_R)
        return b.d_exit_on_R_m + d_in_R + b.d_R_bifurcation_to_reception_m
