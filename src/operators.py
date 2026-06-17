"""
Operadores moviles segmentados por ala (V1.5, Fase 1).

Modelo:
    - Dos pools independientes (upper, lower), cada uno con N operadores fijos.
    - Cada operador es un objeto con estado: id, ala, exit actual, status,
      acumuladores de tiempo y distancia.
    - Cuando un bot solicita servicio en un exit, el pool asigna el operador
      LIBRE mas cercano (politica: menor distancia desde su current_exit).
    - El operador camina hasta el exit (timeout = distancia / velocidad),
      ejecuta el release, actualiza su current_exit, y vuelve al pool.

Notas:
    - El pool no usa simpy.Resource estandar porque la politica "mas cercano"
      requiere inspeccionar el estado de cada operador libre, no FIFO.
    - Si no hay operadores libres, el bot se encola y es servido FIFO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import simpy

if TYPE_CHECKING:
    from geometry import Geometry, Wing


@dataclass
class Operator:
    operator_id: str
    wing: str               # 'upper' | 'lower'
    current_exit: str       # exit donde esta actualmente
    status: str = "idle"    # 'idle' | 'walking' | 'serving'
    total_walking_time_s: float = 0.0
    total_serving_time_s: float = 0.0
    total_idle_time_s: float = 0.0
    total_walking_distance_m: float = 0.0
    services_completed: int = 0
    last_state_change: float = 0.0

    def _change_status(self, new_status: str, now: float) -> None:
        elapsed = now - self.last_state_change
        if self.status == "idle":
            self.total_idle_time_s += elapsed
        elif self.status == "walking":
            self.total_walking_time_s += elapsed
        elif self.status == "serving":
            self.total_serving_time_s += elapsed
        self.status = new_status
        self.last_state_change = now


@dataclass
class ServiceRecord:
    """Registro de un servicio individual (para metricas)."""
    operator_id: str
    bot_id: str
    rack_id: str
    exit_id: str
    request_time: float       # cuando el bot pidio servicio
    assignment_time: float    # cuando se le asigno operador
    arrival_time: float       # cuando el operador llego al exit
    end_time: float           # cuando termino el release
    walking_distance_m: float
    walking_time_s: float
    serving_time_s: float
    wait_for_operator_s: float  # = assignment_time - request_time
    n_os_stop: int


class OperatorPool:
    """
    Pool de operadores asignados a un ala.

    Asignacion: cuando un bot llama request_service(exit_id), el pool
    asigna el operador LIBRE mas cercano. Si todos estan ocupados,
    el bot espera FIFO hasta que se libere alguno.
    """

    def __init__(
        self,
        env: simpy.Environment,
        wing: "Wing",
        n_operators: int,
        geometry: "Geometry",
        walking_speed_mps: float,
    ) -> None:
        self.env = env
        self.wing = wing
        self.geometry = geometry
        self.walking_speed = walking_speed_mps

        self.operators: list[Operator] = self._initialize_operators(n_operators)

        # Cola FIFO de pendientes cuando todos estan ocupados.
        # Cada request es un simpy.Event que se resuelve con el Operator asignado.
        self._waiting: list[tuple[str, simpy.Event]] = []

        self.service_records: list[ServiceRecord] = []

    # ------------------------------------------------------------------
    # Inicializacion
    # ------------------------------------------------------------------
    def _initialize_operators(self, n: int) -> list[Operator]:
        """
        Distribuye N operadores uniformemente entre los exits del ala.
        Si N >= n_exits, asigna uno por exit hasta cubrir todos, y el
        resto se distribuye desde el principio nuevamente.
        Si N < n_exits, los operadores se ubican espaciados.
        """
        if self.wing == "upper":
            exits = self.geometry.upper_exits()
        else:
            exits = self.geometry.lower_exits()

        if not exits:
            raise ValueError(f"No hay exits en el ala '{self.wing}'")
        if n <= 0:
            raise ValueError(f"n_operators debe ser > 0, recibido {n}")

        ops: list[Operator] = []
        for i in range(n):
            # indice del exit asignado, distribuido uniformemente
            exit_idx = int(round(i * len(exits) / n))
            exit_idx = min(exit_idx, len(exits) - 1)
            ops.append(
                Operator(
                    operator_id=f"OP_{self.wing[:1].upper()}{i+1}",
                    wing=self.wing,
                    current_exit=exits[exit_idx],
                    status="idle",
                    last_state_change=0.0,
                )
            )
        return ops

    # ------------------------------------------------------------------
    # Asignacion: operador mas cercano
    # ------------------------------------------------------------------
    def _find_closest_idle(self, target_exit: str) -> Operator | None:
        """Devuelve el operador idle mas cercano a target_exit, o None."""
        candidates = [op for op in self.operators if op.status == "idle"]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda op: self._walking_distance(op.current_exit, target_exit),
        )

    def _walking_distance(self, from_exit: str, to_exit: str) -> float:
        """
        Distancia que camina un operador entre dos exits del MISMO ala.
        Es |pos(j) - pos(i)| en el carril del ala.
        """
        if from_exit == to_exit:
            return 0.0
        pi = self.geometry.position_on_wing(from_exit)
        pj = self.geometry.position_on_wing(to_exit)
        return abs(pj - pi)

    # ------------------------------------------------------------------
    # API publica: solicitar servicio
    # ------------------------------------------------------------------
    def request_service(
        self,
        bot_id: str,
        rack_id: str,
        exit_id: str,
        release_time_s: float,
        n_os_stop: int,
    ):
        """
        Process generator. Yields hasta que el operador termina el release.

        Flujo:
            1. Espera operador libre (FIFO si todos ocupados).
            2. Camina hasta el exit (timeout proporcional a distancia).
            3. Ejecuta release (timeout = release_time_s).
            4. Actualiza estado y libera.

        Returns (via process result): el ServiceRecord generado.
        """
        request_time = self.env.now

        # 1. Buscar operador libre
        op = self._find_closest_idle(exit_id)

        if op is None:
            # Todos ocupados: encolarse FIFO
            evt = self.env.event()
            self._waiting.append((exit_id, evt))
            op = yield evt  # bloqueo hasta que alguien se libere

        # En este punto tenemos un operador asignado y reservado
        assignment_time = self.env.now
        op._change_status("walking", assignment_time)

        # 2. Caminata
        distance = self._walking_distance(op.current_exit, exit_id)
        walking_time = distance / self.walking_speed if self.walking_speed > 0 else 0.0
        if walking_time > 0:
            yield self.env.timeout(walking_time)

        arrival_time = self.env.now
        op._change_status("serving", arrival_time)
        op.total_walking_distance_m += distance

        # 3. Release
        yield self.env.timeout(release_time_s)
        end_time = self.env.now

        # 4. Cierre
        op.current_exit = exit_id
        op.services_completed += 1
        op._change_status("idle", end_time)

        record = ServiceRecord(
            operator_id=op.operator_id,
            bot_id=bot_id,
            rack_id=rack_id,
            exit_id=exit_id,
            request_time=request_time,
            assignment_time=assignment_time,
            arrival_time=arrival_time,
            end_time=end_time,
            walking_distance_m=distance,
            walking_time_s=walking_time,
            serving_time_s=release_time_s,
            wait_for_operator_s=assignment_time - request_time,
            n_os_stop=n_os_stop,
        )
        self.service_records.append(record)

        # 5. Si hay bots esperando, asignar el operador mas cercano (libre)
        # al primero de la cola FIFO. El op recien liberado es candidato pero
        # no necesariamente el elegido si otros estan mas cerca del exit pendiente.
        if self._waiting:
            next_exit, next_evt = self._waiting.pop(0)
            chosen = self._find_closest_idle(next_exit)
            if chosen is None:
                # Salvaguarda: este op acaba de quedar idle, no deberia pasar
                self._waiting.insert(0, (next_exit, next_evt))
            else:
                next_evt.succeed(chosen)

        return record

    # ------------------------------------------------------------------
    # Utilizacion final (al cerrar simulacion)
    # ------------------------------------------------------------------
    def finalize(self, now: float) -> None:
        """Cerrar el ultimo intervalo de estado de cada operador."""
        for op in self.operators:
            op._change_status(op.status, now)

    def utilization_summary(self, t_window_s: float) -> list[dict]:
        """
        Resumen por operador.
        t_window_s: tiempo de la ventana de medicion (excluyendo warmup).
        """
        out = []
        for op in self.operators:
            total = max(
                1e-9,
                op.total_walking_time_s + op.total_serving_time_s + op.total_idle_time_s,
            )
            out.append({
                "operator_id": op.operator_id,
                "wing": op.wing,
                "current_exit": op.current_exit,
                "services_completed": op.services_completed,
                "walking_time_s": op.total_walking_time_s,
                "serving_time_s": op.total_serving_time_s,
                "idle_time_s": op.total_idle_time_s,
                "walking_distance_m": op.total_walking_distance_m,
                "frac_walking": op.total_walking_time_s / total,
                "frac_serving": op.total_serving_time_s / total,
                "frac_idle": op.total_idle_time_s / total,
                "utilization": (op.total_walking_time_s + op.total_serving_time_s) / total,
            })
        return out
