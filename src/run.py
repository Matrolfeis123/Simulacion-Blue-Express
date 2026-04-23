from __future__ import annotations

from pathlib import Path
from pprint import pprint

import pandas as pd

from config import build_peak_config
from inputs import InputModel
from simulation import build_and_run_simulation


def _build_release_time_by_n_os_stop(config, max_os_per_stop: int) -> dict[int, float]:
    release_base_time_s = config.turn_time_s
    release_time_per_os_s = config.pallet_load_unload_time_s / max_os_per_stop
    return {
        n_os_stop: release_base_time_s + (n_os_stop * release_time_per_os_s)
        for n_os_stop in range(1, max_os_per_stop + 1)
    }


def build_input_model_from_excel(
    excel_path: str | Path,
    os_per_hour: float = 693.0,
    distance_between_consecutive_exits_m: float = 5.2,
):
    """
    Construye InputModel leyendo data_entry.xlsx con el contrato de hojas v1 real.

    Notas:
    - distance_between_consecutive_exits_m queda paramétrico para el layout simétrico.
    - La distancia de retorno se lee explícitamente desde hoja dedicada
      (no se asume simetría con la ida).
    """
    config = build_peak_config()
    excel_path = Path(excel_path)

    destination_df = pd.read_excel(
        excel_path,
        sheet_name="destination_distribution",
        usecols=["destination_id", "probability"],
    ).dropna(subset=["destination_id", "probability"])
    destination_distribution = dict(
        zip(
            destination_df["destination_id"].astype(str),
            destination_df["probability"].astype(float),
        )
    )

    destination_to_exit_df = pd.read_excel(
        excel_path,
        sheet_name="destination_to_exit",
        usecols=["destination_id", "exit_id"],
    ).dropna(subset=["destination_id", "exit_id"])
    destination_to_exit = dict(
        zip(
            destination_to_exit_df["destination_id"].astype(str),
            destination_to_exit_df["exit_id"].astype(str),
        )
    )

    segment_df = pd.read_excel(
        excel_path,
        sheet_name="segment_distribution_by_dest",
        usecols=["destination_id", "segment", "probability"],
    ).dropna(subset=["destination_id", "segment", "probability"])

    segment_distribution_by_destination: dict[str, dict[str, float]] = {}
    for destination_id, group in segment_df.groupby("destination_id"):
        segment_distribution_by_destination[str(destination_id)] = {
            str(row.segment): float(row.probability)
            for row in group.itertuples(index=False)
        }

    receiving_distance_df = pd.read_excel(
        excel_path,
        sheet_name="travel_receiving_to_exit",
        usecols=["exit_id", "travel_distance_m"],
    ).dropna(subset=["exit_id", "travel_distance_m"])
    travel_distances_receiving_to_exit = dict(
        zip(
            receiving_distance_df["exit_id"].astype(str),
            receiving_distance_df["travel_distance_m"].astype(float),
        )
    )

    return_distance_df = pd.read_excel(
        excel_path,
        sheet_name="travel_exit_to_return",
        usecols=["exit_id", "travel_distance_m"],
    ).dropna(subset=["exit_id", "travel_distance_m"])
    travel_distances_exit_to_return = dict(
        zip(
            return_distance_df["exit_id"].astype(str),
            return_distance_df["travel_distance_m"].astype(float),
        )
    )

    # -----------------------------
    # Tiempos de preparación de rack
    # TODO: reemplazar con tu lógica real
    # -----------------------------
    rack_prep_time_by_n_os = {
        1: 20,
        2: 25.0,
        3: 30.0,
        4: 40.0,
        5: 50.0,
    }

    # -----------------------------
    # Tiempos de release por stop
    # -----------------------------
    release_time_by_n_os_stop = _build_release_time_by_n_os_stop(
        config=config,
        max_os_per_stop=max(rack_prep_time_by_n_os),
    )

    input_model = InputModel(
        config=config,
        os_per_hour=os_per_hour,
        destination_distribution=destination_distribution,
        destination_to_exit=destination_to_exit,
        segment_distribution_by_destination=segment_distribution_by_destination,
        travel_distances_receiving_to_exit=travel_distances_receiving_to_exit,
        travel_distances_exit_to_return=travel_distances_exit_to_return,
        distance_between_consecutive_exits_m=distance_between_consecutive_exits_m,
        rack_prep_time_by_n_os=rack_prep_time_by_n_os,
        release_time_by_n_os_stop=release_time_by_n_os_stop,
        turns_receiving_to_first_exit=2,
        turns_between_exits=4,
        turns_last_exit_to_return=3,
    )

    return config, input_model


def summarize_results(dfs: dict[str, pd.DataFrame], simulation_horizon_s: float) -> dict:
    summary: dict = {}

    completed = dfs["completed_racks"]
    os_arrivals = dfs["os_arrivals"]
    queue_events = dfs["exit_queue_events"]
    snapshots = dfs["state_snapshots"]

    if not completed.empty:
        total_racks = len(completed)
        total_os = completed["n_os"].sum()
        throughput_os_per_hour = total_os / (simulation_horizon_s / 3600.0)

        summary["total_completed_racks"] = total_racks
        summary["total_completed_os"] = float(total_os)
        summary["throughput_os_per_hour"] = float(throughput_os_per_hour)
        summary["mean_cycle_time_s"] = float(completed["cycle_time_total"].mean())
        summary["p90_cycle_time_s"] = float(completed["cycle_time_total"].quantile(0.90))
        summary["mean_queue_time_trip_s"] = float(completed["queue_time_total"].mean())
        summary["mean_release_time_trip_s"] = float(completed["release_time_total"].mean())
        summary["mean_travel_time_trip_s"] = float(completed["travel_time_total"].mean())
    else:
        summary["total_completed_racks"] = 0
        summary["total_completed_os"] = 0.0
        summary["throughput_os_per_hour"] = 0.0

    if not queue_events.empty:
        summary["mean_exit_queue_delay_s"] = float(queue_events["queue_delay_s"].mean())
        summary["p90_exit_queue_delay_s"] = float(queue_events["queue_delay_s"].quantile(0.90))
        summary["max_exit_queue_delay_s"] = float(queue_events["queue_delay_s"].max())
    else:
        summary["mean_exit_queue_delay_s"] = 0.0
        summary["p90_exit_queue_delay_s"] = 0.0
        summary["max_exit_queue_delay_s"] = 0.0

    if not snapshots.empty:
        summary["mean_os_buffer"] = float(snapshots["os_buffer_len"].mean())
        summary["mean_pending_racks"] = float(snapshots["pending_racks_len"].mean())
        summary["mean_ready_racks"] = float(snapshots["ready_racks_len"].mean())
        summary["mean_empty_racks_level"] = float(snapshots["empty_racks_level"].mean())
        summary["max_ready_racks"] = float(snapshots["ready_racks_len"].max())
        summary["max_pending_racks"] = float(snapshots["pending_racks_len"].max())
    else:
        summary["mean_os_buffer"] = 0.0
        summary["mean_pending_racks"] = 0.0
        summary["mean_ready_racks"] = 0.0
        summary["mean_empty_racks_level"] = 0.0
        summary["max_ready_racks"] = 0.0
        summary["max_pending_racks"] = 0.0

    return summary


def main():
    config, input_model = build_input_model_from_excel(
        excel_path="src/inputs_data/data_entry.xlsx",
        os_per_hour=693.0,
        distance_between_consecutive_exits_m=5.0,
    )

    metrics = build_and_run_simulation(
        config=config,
        input_model=input_model,
    )
    dfs = metrics.to_dataframes()

    summary = summarize_results(dfs, config.simulation_horizon)
    print("\n=== Simulation Summary ===")
    pprint(summary)

    # Export opcional
    for name, df in dfs.items():
        if not df.empty:
            df.to_csv(f"{name}.csv", index=False)

    print("\nCSV files exported for non-empty outputs.")


if __name__ == "__main__":
    main()
