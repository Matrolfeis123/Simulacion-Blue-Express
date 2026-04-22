from __future__ import annotations

import random
from collections import Counter
from typing import Dict, List, Tuple

from models import OS, RackMission, SimulationConfig


class InputModel:
    """
    Modelo de inputs V1.

    Esta versión:
    - permite generar OS por tasa agregada
    - permite mapear destino -> salida
    - permite calcular tiempos desde tablas parametrizadas
    - permite reglas simples de consolidación
    """

    def __init__(
        self,
        config: SimulationConfig,
        os_per_hour: float,
        segment_distribution: Dict[str, float],
        exit_distribution: Dict[str, float],
        destination_to_exit: Dict[str, str],
        travel_times_receiving_to_exit: Dict[str, float],
        travel_times_exit_to_return: Dict[str, float],
        travel_times_between_exits: Dict[Tuple[str, str], float],
        rack_prep_time_by_n_os: Dict[int, float],
        release_time_by_n_os_stop: Dict[int, float],
    ) -> None:
        self.config = config
        self.os_per_hour = os_per_hour
        self.segment_distribution = self._normalize(segment_distribution)
        self.exit_distribution = self._normalize(exit_distribution)
        self.destination_to_exit = destination_to_exit

        self.travel_times_receiving_to_exit = travel_times_receiving_to_exit
        self.travel_times_exit_to_return = travel_times_exit_to_return
        self.travel_times_between_exits = travel_times_between_exits

        self.rack_prep_time_by_n_os = rack_prep_time_by_n_os
        self.release_time_by_n_os_stop = release_time_by_n_os_stop

        self.rng = random.Random(config.random_seed)

    # ---------------------------------------------------------------------
    # Sampling
    # ---------------------------------------------------------------------
    def sample_interarrival_time(self, current_time: float) -> float:
        """
        Llegadas Poisson agregadas:
        lambda = os_per_hour / 3600
        """
        rate_per_second = self.os_per_hour / 3600.0
        return self.rng.expovariate(rate_per_second)

    def sample_segment(self) -> str:
        return self._weighted_choice(self.segment_distribution)

    def sample_exit(self) -> str:
        return self._weighted_choice(self.exit_distribution)

    def sample_destination(self, exit_id: str | None = None) -> str:
        """
        V1 simple:
        destino = igual a exit_id si no existe catálogo detallado.
        Luego esto se puede refinar.
        """
        if exit_id is None:
            exit_id = self.sample_exit()
        return f"DEST_{exit_id}"

    def sample_zone(self, exit_id: str) -> str:
        exit_num = int(exit_id.split("_")[-1])
        return "SCL" if 1 <= exit_num <= 19 else "REG"

    # ---------------------------------------------------------------------
    # Reglas de consolidación
    # ---------------------------------------------------------------------
    def get_trip_building_capacity(self, segment: str) -> int:
        """
        Reglas actuales:
        - Regular + Medium: hasta 5
        - Big: hasta 2
        - SuperBig: 1
        """
        if segment in {"Regular", "Medium"}:
            return 5
        if segment == "Big":
            return 2
        if segment == "SuperBig":
            return 1
        raise ValueError(f"Unknown segment: {segment}")

    def get_rack_prep_time(self, n_os: int, segment_mix: Dict[str, int]) -> float:
        """
        V1: tiempo depende del número de OS del rack.
        Luego se puede hacer depender del mix real.
        """
        if n_os not in self.rack_prep_time_by_n_os:
            raise KeyError(f"No rack prep time for n_os={n_os}")
        return self.rack_prep_time_by_n_os[n_os]

    def get_release_time(self, n_os_stop: int) -> float:
        """
        Tiempo de liberación del bot en una parada.
        """
        if n_os_stop not in self.release_time_by_n_os_stop:
            raise KeyError(f"No release time for n_os_stop={n_os_stop}")
        return self.release_time_by_n_os_stop[n_os_stop]

    # ---------------------------------------------------------------------
    # Tiempos de viaje
    # ---------------------------------------------------------------------
    def get_travel_time_receiving_to_exit(self, exit_id: str) -> float:
        return self.travel_times_receiving_to_exit[exit_id]

    def get_travel_time_between_exits(self, exit_i: str, exit_j: str) -> float:
        return self.travel_times_between_exits[(exit_i, exit_j)]

    def get_travel_time_exit_to_return(self, exit_id: str) -> float:
        return self.travel_times_exit_to_return[exit_id]

    def get_all_exit_ids(self) -> List[str]:
        return list(self.exit_distribution.keys())

    # ---------------------------------------------------------------------
    # Construcción lógica de racks
    # ---------------------------------------------------------------------
    def try_build_rack_from_buffer(
        self,
        os_buffer: List[OS],
        current_time: float,
        rack_id: str,
    ) -> RackMission | None:
        """
        V1 simple y trazable:
        - prioriza OS por grupo de segmento
        - agrupa por capacidad teórica
        - no optimiza finamente combinaciones
        - mantiene secuencia de exits ordenada ascendente
        """
        if not os_buffer:
            return None

        # 1) intentar formar rack de Regular/Medium
        rm_candidates = [o for o in os_buffer if o.segment in {"Regular", "Medium"}]
        if len(rm_candidates) >= 1:
            chosen = rm_candidates[: min(5, len(rm_candidates))]
            if chosen:
                return self._build_rack(chosen, os_buffer, current_time, rack_id)

        # 2) intentar rack de Big
        big_candidates = [o for o in os_buffer if o.segment == "Big"]
        if len(big_candidates) >= 1:
            chosen = big_candidates[: min(2, len(big_candidates))]
            if chosen:
                return self._build_rack(chosen, os_buffer, current_time, rack_id)

        # 3) SuperBig individual
        super_candidates = [o for o in os_buffer if o.segment == "SuperBig"]
        if super_candidates:
            chosen = [super_candidates[0]]
            return self._build_rack(chosen, os_buffer, current_time, rack_id)

        return None

    def _build_rack(
        self,
        chosen_os: List[OS],
        os_buffer: List[OS],
        current_time: float,
        rack_id: str,
    ) -> RackMission:
        # Remover del buffer
        chosen_ids = {o.os_id for o in chosen_os}
        remaining = [o for o in os_buffer if o.os_id not in chosen_ids]
        os_buffer[:] = remaining

        for o in chosen_os:
            o.status = "assigned_to_rack"

        exit_counter = Counter(o.exit_id for o in chosen_os)
        exit_sequence = sorted(exit_counter.keys(), key=self._exit_sort_key)

        rack = RackMission(
            rack_id=rack_id,
            creation_time=current_time,
            os_list=chosen_os,
            n_os=len(chosen_os),
            exit_sequence=exit_sequence,
            n_stops=len(exit_sequence),
            segment_mix=dict(Counter(o.segment for o in chosen_os)),
            os_count_by_exit=dict(exit_counter),
            status="waiting_preparation",
        )
        return rack

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _weighted_choice(self, distribution: Dict[str, float]) -> str:
        keys = list(distribution.keys())
        weights = list(distribution.values())
        return self.rng.choices(keys, weights=weights, k=1)[0]

    def _normalize(self, distribution: Dict[str, float]) -> Dict[str, float]:
        total = sum(distribution.values())
        if total <= 0:
            raise ValueError("Distribution total must be > 0")
        return {k: v / total for k, v in distribution.items()}

    def _exit_sort_key(self, exit_id: str) -> int:
        return int(exit_id.split("_")[-1])