from __future__ import annotations

from typing import Dict, List, Optional

import simpy

from inputs import InputModel
from metrics import MetricsCollector
from models import Bot, OS, RackMission, SimulationConfig


class WarehouseSimulation:
    def __init__(
        self,
        env: simpy.Environment,
        config: SimulationConfig,
        input_model: InputModel,
        metrics: MetricsCollector,
    ) -> None:
        self.env = env
        self.config = config
        self.input_model = input_model
        self.metrics = metrics

        # -----------------------------
        # Resources
        # -----------------------------
        self.reception = simpy.Resource(env, capacity=config.n_receiving_operators)

        self.exit_resources: Dict[str, simpy.Resource] = {
            exit_id: simpy.Resource(env, capacity=1)
            for exit_id in self.input_model.get_all_exit_ids()
        }

        self.pending_racks = simpy.Store(env)

        if config.ready_rack_buffer_capacity is None:
            self.ready_racks = simpy.Store(env)
        else:
            self.ready_racks = simpy.Store(env, capacity=config.ready_rack_buffer_capacity)

        self.empty_racks = simpy.Container(
            env,
            init=config.empty_rack_initial_inventory,
            capacity=config.empty_rack_initial_inventory,
        )

        # -----------------------------
        # State
        # -----------------------------
        self.os_buffer: List[OS] = []
        self.bots: List[Bot] = [
            Bot(bot_id=f"BOT_{i+1}", last_state_change=0.0)
            for i in range(config.n_bots)
        ]

        self.os_counter: int = 0
        self.rack_counter: int = 0

    # =========================================================
    # Public API
    # =========================================================
    def start(self) -> None:
        self.env.process(self.os_arrival_process())
        self.env.process(self.consolidation_process())
        self.env.process(self.snapshot_process())

        for op_id in range(self.config.n_receiving_operators):
            self.env.process(self.reception_preparation_process(op_id))

        for bot in self.bots:
            self.env.process(self.bot_process(bot))

    # =========================================================
    # Processes
    # =========================================================
    def os_arrival_process(self):
        """
        Genera OS con proceso de Poisson agregado.
        """
        while self.env.now < self.config.simulation_horizon:
            interarrival = self.input_model.sample_interarrival_time(self.env.now)
            yield self.env.timeout(interarrival)

            self.os_counter += 1
            destination_id = self.input_model.sample_destination()
            exit_id = self.input_model.get_exit_for_destination(destination_id)

            os_obj = OS(
                os_id=f"OS_{self.os_counter}",
                arrival_time=self.env.now,
                segment=self.input_model.sample_segment_for_destination(destination_id),
                destination_id=destination_id,
                exit_id=exit_id,
                zone=self.input_model.sample_zone(exit_id),
            )
            self.os_buffer.append(os_obj)
            self.metrics.record_os_arrival(os_obj, self.env.now)

    def consolidation_process(self):
        """
        Revisa periódicamente el buffer de OS e intenta formar racks.
        """
        while self.env.now < self.config.simulation_horizon:
            rack = self._try_build_rack()

            if rack is not None:
                yield self.pending_racks.put(rack)
                self.metrics.record_rack_created(rack, self.env.now)
            else:
                yield self.env.timeout(self.config.consolidation_check_interval_s)

    def reception_preparation_process(self, operator_id: int):
        """
        Operador de recepción toma racks pendientes, consume un rack vacío,
        prepara el rack y lo deja listo para retiro.
        """
        while True:
            rack: RackMission = yield self.pending_racks.get()

            with self.reception.request() as req:
                yield req

                # Toma un rack vacío
                yield self.empty_racks.get(1)

                self.metrics.record_reception_service_start(rack, self.env.now)

                prep_time = self.input_model.get_rack_prep_time(
                    n_os=rack.n_os,
                    segment_mix=rack.segment_mix,
                )

                yield self.env.timeout(prep_time)

                rack.ready_time = self.env.now
                rack.status = "ready"

                yield self.ready_racks.put(rack)
                self.metrics.record_reception_service_end(rack, self.env.now)

    def bot_process(self, bot: Bot):
        """
        Cada bot espera un rack listo, ejecuta la misión y vuelve a esperar.
        """
        while True:
            # Bot espera rack listo
            self._change_bot_state(bot, "waiting_rack")
            wait_start = self.env.now

            rack: RackMission = yield self.ready_racks.get()

            bot.total_idle_time += self.env.now - wait_start
            rack.pickup_time = self.env.now
            rack.status = "assigned"
            bot.current_rack_id = rack.rack_id

            yield self.env.process(self.execute_rack_mission(bot, rack))

    def execute_rack_mission(self, bot: Bot, rack: RackMission):
        """
        Ejecuta el recorrido completo:
        recepción -> exits -> retorno -> depósito de rack vacío
        """
        trip_start = self.env.now
        self._change_bot_state(bot, "traveling")

        # ----- Stops -----
        for stop_idx, exit_id in enumerate(rack.exit_sequence):
            travel_start = self.env.now
            distance, n_turns = self._get_distance_and_turns_for_stop(rack, stop_idx)
            travel_time = self.input_model.get_leg_time_from_distance_and_turns(
                distance_m=distance,
                n_turns=n_turns,
            )

            if stop_idx == 0:
                leg_type = "receiving_to_first_exit"
                leg_from = "receiving"
                leg_to = exit_id
            else:
                leg_type = "between_exits"
                leg_from = rack.exit_sequence[stop_idx - 1]
                leg_to = exit_id

            rack.travel_distance_total += distance
            rack.travel_time_total += travel_time
            yield self.env.timeout(travel_time)
            travel_end = self.env.now

            self.metrics.record_travel_audit_event(
                {
                    "time": travel_end,
                    "event_type": "travel_leg",
                    "bot_id": bot.bot_id,
                    "rack_id": rack.rack_id,
                    "stop_index": stop_idx + 1,
                    "exit_id": exit_id,
                    "leg_type": leg_type,
                    "from_node": leg_from,
                    "to_node": leg_to,
                    "travel_start": travel_start,
                    "travel_end": travel_end,
                    "distance_m": distance,
                    "n_turns": n_turns,
                    "travel_time_s": travel_time,
                }
            )

            # Llega a la salida y espera servicio si corresponde
            arrival_to_exit = self.env.now
            self._change_bot_state(bot, "waiting_exit")

            with self.exit_resources[exit_id].request() as req:
                yield req

                queue_delay = self.env.now - arrival_to_exit
                rack.queue_time_total += queue_delay
                self.metrics.record_exit_queue(exit_id, queue_delay, self.env.now)

                n_os_stop = rack.os_count_by_exit[exit_id]
                release_time = self.input_model.get_release_time(n_os_stop)
                rack.release_time_total += release_time
                service_start = self.env.now

                self.metrics.record_exit_service(
                    exit_id=exit_id,
                    release_time_s=release_time,
                    n_os_stop=n_os_stop,
                    time=self.env.now,
                )

                self._change_bot_state(bot, "traveling")
                yield self.env.timeout(release_time)
                service_end = self.env.now

                self.metrics.record_travel_audit_event(
                    {
                        "time": service_end,
                        "event_type": "exit_stop_service",
                        "bot_id": bot.bot_id,
                        "rack_id": rack.rack_id,
                        "stop_index": stop_idx + 1,
                        "exit_id": exit_id,
                        "queue_delay_s": queue_delay,
                        "service_start": service_start,
                        "service_end": service_end,
                        "release_time_s": release_time,
                        "n_os_stop": n_os_stop,
                    }
                )

        # ----- Return -----
        self._change_bot_state(bot, "returning")
        return_start = self.env.now
        return_distance, return_turns = self._get_return_distance_and_turns(rack)
        return_time = self.input_model.get_leg_time_from_distance_and_turns(
            distance_m=return_distance,
            n_turns=return_turns,
        )
        rack.travel_distance_total += return_distance
        rack.travel_time_total += return_time
        yield self.env.timeout(return_time)
        return_end = self.env.now

        self.metrics.record_travel_audit_event(
            {
                "time": return_end,
                "event_type": "return_leg",
                "bot_id": bot.bot_id,
                "rack_id": rack.rack_id,
                "stop_index": rack.n_stops,
                "exit_id": rack.exit_sequence[-1],
                "leg_type": "last_exit_to_return",
                "from_node": rack.exit_sequence[-1],
                "to_node": "return",
                "travel_start": return_start,
                "travel_end": return_end,
                "distance_m": return_distance,
                "n_turns": return_turns,
                "travel_time_s": return_time,
            }
        )

        # Deja rack vacío
        yield self.empty_racks.put(1)

        rack.return_time = self.env.now
        rack.cycle_time_total = rack.return_time - rack.pickup_time
        rack.status = "completed"

        bot.trip_count += 1
        bot.current_rack_id = None
        self._change_bot_state(bot, "idle")

        self.metrics.record_travel_audit_event(
            {
                "time": self.env.now,
                "event_type": "trip_completed",
                "bot_id": bot.bot_id,
                "rack_id": rack.rack_id,
                "n_os": rack.n_os,
                "n_stops": rack.n_stops,
                "trip_start": trip_start,
                "trip_end": self.env.now,
                "trip_duration_s": self.env.now - trip_start,
                "travel_distance_total": rack.travel_distance_total,
                "travel_time_total": rack.travel_time_total,
                "queue_time_total": rack.queue_time_total,
                "release_time_total": rack.release_time_total,
                "cycle_time_total": rack.cycle_time_total,
            }
        )

        self.metrics.record_completed_rack(rack, self.env.now)

    def snapshot_process(self):
        """
        Guarda snapshots periódicos para monitorear buffers y acumulación.
        """
        while self.env.now < self.config.simulation_horizon:
            self.metrics.record_state_snapshot(
                time=self.env.now,
                os_buffer_len=len(self.os_buffer),
                pending_racks_len=len(self.pending_racks.items),
                ready_racks_len=len(self.ready_racks.items),
                empty_racks_level=self.empty_racks.level,
            )
            yield self.env.timeout(60.0)  # snapshot cada 60s

    # =========================================================
    # Helpers
    # =========================================================
    def _try_build_rack(self) -> Optional[RackMission]:
        """
        Wrapper sobre InputModel para formar racks desde el buffer de OS.
        """
        if not self.os_buffer:
            return None

        self.rack_counter += 1
        rack_id = f"RACK_{self.rack_counter}"

        rack = self.input_model.try_build_rack_from_buffer(
            os_buffer=self.os_buffer,
            current_time=self.env.now,
            rack_id=rack_id,
        )

        if rack is None:
            self.rack_counter -= 1
            return None

        return rack

    def _get_distance_and_turns_for_stop(self, rack: RackMission, stop_idx: int) -> tuple[float, int]:
        if stop_idx == 0:
            exit_id = rack.exit_sequence[0]
            return (
                self.input_model.get_distance_receiving_to_exit(exit_id),
                self.input_model.get_turns_receiving_to_first_exit(),
            )

        prev_exit = rack.exit_sequence[stop_idx - 1]
        curr_exit = rack.exit_sequence[stop_idx]
        return (
            self.input_model.get_distance_between_exits(prev_exit, curr_exit),
            self.input_model.get_turns_between_exits(),
        )

    def _get_return_distance_and_turns(self, rack: RackMission) -> tuple[float, int]:
        last_exit = rack.exit_sequence[-1]
        return (
            self.input_model.get_distance_exit_to_return(last_exit),
            self.input_model.get_turns_last_exit_to_return(),
        )

    def _change_bot_state(self, bot: Bot, new_state: str) -> None:
        """
        Actualiza tiempos por estado de forma simple.
        """
        now = self.env.now
        elapsed = now - bot.last_state_change

        if bot.status in {"traveling", "waiting_exit", "returning"}:
            bot.total_busy_time += elapsed
        elif bot.status in {"idle", "waiting_rack"}:
            bot.total_idle_time += elapsed

        bot.status = new_state
        bot.last_state_change = now


def build_and_run_simulation(
    config: SimulationConfig,
    input_model: InputModel,
) -> MetricsCollector:
    env = simpy.Environment()
    metrics = MetricsCollector()

    simulation = WarehouseSimulation(
        env=env,
        config=config,
        input_model=input_model,
        metrics=metrics,
    )
    simulation.start()

    env.run(until=config.simulation_horizon)
    return metrics