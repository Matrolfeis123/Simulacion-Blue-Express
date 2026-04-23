from __future__ import annotations

import random
from collections import Counter
from typing import Dict, List

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
        destination_distribution: Dict[str, float],
        destination_to_exit: Dict[str, str],
        segment_distribution_by_destination: Dict[str, Dict[str, float]],
        travel_distances_receiving_to_exit: Dict[str, float],
        travel_distances_exit_to_return: Dict[str, float],
        distance_between_consecutive_exits_m: float,
        rack_prep_time_by_n_os: Dict[int, float],
        release_time_by_n_os_stop: Dict[int, float],
        turns_receiving_to_first_exit: int = 2,
        turns_between_exits: int = 4,
        turns_last_exit_to_return: int = 3,
    ) -> None:
        self.config = config
        self.os_per_hour = os_per_hour
        self.destination_distribution = self._normalize(destination_distribution)
        self.active_destinations = {
            destination_id
            for destination_id, probability in self.destination_distribution.items()
            if probability > 0
        }
        self.destination_to_exit = dict(destination_to_exit)
        self.segment_distribution_by_destination = {}
        for destination_id, segment_distribution in segment_distribution_by_destination.items():
            if destination_id in self.active_destinations:
                self.segment_distribution_by_destination[destination_id] = self._normalize(
                    segment_distribution
                )
            else:
                self.segment_distribution_by_destination[destination_id] = dict(segment_distribution)

        self.travel_distances_receiving_to_exit = dict(travel_distances_receiving_to_exit)
        self.travel_distances_exit_to_return = dict(travel_distances_exit_to_return)
        self.distance_between_consecutive_exits_m = float(distance_between_consecutive_exits_m)

        self.turns_receiving_to_first_exit = int(turns_receiving_to_first_exit)
        self.turns_between_exits = int(turns_between_exits)
        self.turns_last_exit_to_return = int(turns_last_exit_to_return)

        self.rack_prep_time_by_n_os = rack_prep_time_by_n_os
        self.release_time_by_n_os_stop = release_time_by_n_os_stop

        self._validate_inputs()

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

    def sample_destination(self) -> str:
        return self._weighted_choice(self.destination_distribution)

    def get_exit_for_destination(self, destination_id: str) -> str:
        if destination_id not in self.destination_to_exit:
            raise KeyError(f"No exit mapping for destination '{destination_id}'")
        return self.destination_to_exit[destination_id]

    def sample_segment_for_destination(self, destination_id: str) -> str:
        if destination_id not in self.segment_distribution_by_destination:
            raise KeyError(
                f"No segment distribution for destination '{destination_id}'"
            )
        return self._weighted_choice(self.segment_distribution_by_destination[destination_id])

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
    # Viaje por distancias + giros
    # ---------------------------------------------------------------------
    def get_distance_receiving_to_exit(self, exit_id: str) -> float:
        return self.travel_distances_receiving_to_exit[exit_id]

    def get_distance_between_exits(self, exit_i: str, exit_j: str) -> float:
        i = self._exit_sort_key(exit_i)
        j = self._exit_sort_key(exit_j)
        return abs(j - i) * self.distance_between_consecutive_exits_m

    def get_distance_exit_to_return(self, exit_id: str) -> float:
        return self.travel_distances_exit_to_return[exit_id]

    def get_turns_receiving_to_first_exit(self) -> int:
        return self.turns_receiving_to_first_exit

    def get_turns_between_exits(self) -> int:
        return self.turns_between_exits

    def get_turns_last_exit_to_return(self) -> int:
        return self.turns_last_exit_to_return

    def get_leg_time_from_distance_and_turns(self, distance_m: float, n_turns: int) -> float:
        travel_time_s = distance_m / self.config.effective_speed_mps
        turn_time_s = n_turns * self.config.turn_time_s
        return travel_time_s + turn_time_s

    def get_all_exit_ids(self) -> List[str]:
        return sorted(
            set(self.destination_to_exit.values()),
            key=self._exit_sort_key,
        )

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

    def _validate_inputs(self) -> None:
        if self.config.effective_speed_mps <= 0:
            raise ValueError("effective_speed_mps must be > 0")

        if self.distance_between_consecutive_exits_m < 0:
            raise ValueError("distance_between_consecutive_exits_m must be >= 0")

        if any(v < 0 for v in self.travel_distances_receiving_to_exit.values()):
            raise ValueError("travel_distances_receiving_to_exit cannot contain negative values")

        if any(v < 0 for v in self.travel_distances_exit_to_return.values()):
            raise ValueError("travel_distances_exit_to_return cannot contain negative values")

        destination_ids = set(self.destination_distribution.keys())
        mapped_ids = set(self.destination_to_exit.keys())
        if not destination_ids.issubset(mapped_ids):
            missing = sorted(destination_ids - mapped_ids)
            raise ValueError(f"Missing destination_to_exit mapping for destinations: {missing}")

        segment_ids = set(self.segment_distribution_by_destination.keys())
        if not self.active_destinations.issubset(segment_ids):
            missing = sorted(self.active_destinations - segment_ids)
            raise ValueError(
                "Missing segment_distribution_by_destination for active destinations: "
                f"{missing}"
            )

        required_exits = {self.destination_to_exit[d] for d in self.active_destinations}
        exits_with_receiving_distance = set(self.travel_distances_receiving_to_exit.keys())
        exits_with_return_distance = set(self.travel_distances_exit_to_return.keys())

        if not required_exits.issubset(exits_with_receiving_distance):
            missing = sorted(required_exits - exits_with_receiving_distance)
            raise ValueError(
                "Missing receiving->exit distance for exits: "
                f"{missing}"
            )

        if not required_exits.issubset(exits_with_return_distance):
            missing = sorted(required_exits - exits_with_return_distance)
            raise ValueError(
                "Missing exit->return distance for exits: "
                f"{missing}"
            )

    def _exit_sort_key(self, exit_id: str) -> int:
        return int(exit_id.split("_")[-1])