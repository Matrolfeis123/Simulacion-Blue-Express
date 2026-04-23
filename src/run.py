from __future__ import annotations

from pathlib import Path
from pprint import pprint

import pandas as pd

from config import build_peak_config
from dashboard import build_dashboard
from inputs import InputModel
from models import SimulationConfig
from simulation import build_and_run_simulation


def _build_release_time_by_n_os_stop(config: SimulationConfig, max_os_per_stop: int) -> dict[int, float]:
    release_base_time_s = config.turn_time_s
    release_time_per_os_s = config.pallet_load_unload_time_s / max_os_per_stop
    return {
        n_os_stop: release_base_time_s + (n_os_stop * release_time_per_os_s)
        for n_os_stop in range(1, max_os_per_stop + 1)
    }


def build_input_model_from_excel(
    excel_path: str | Path,
    os_per_hour: float = 693.0,
    distance_between_consecutive_exits_m: float = 5.0,
):
    """
    Construye InputModel leyendo data_entry.xlsx con el contrato de hojas v1 real.
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

    rack_prep_time_by_n_os = {
        1: 8.0,
        2: 12.0,
        3: 16.0,
        4: 20.0,
        5: 24.0,
    }

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


def _filter_by_warmup(dfs: dict[str, pd.DataFrame], config: SimulationConfig) -> dict[str, pd.DataFrame]:
    """
    Filtra todos los DataFrames de métricas para excluir eventos anteriores
    a warmup_time. Cada tabla usa su campo temporal más representativo.

    Regla por tabla:
        completed_racks     → pickup_time >= warmup  (misión inició post-warmup)
        os_arrivals         → time >= warmup
        rack_creations      → time >= warmup
        reception_events    → time >= warmup
        exit_queue_events   → time >= warmup
        exit_service_events → time >= warmup
        travel_audit_events → time >= warmup
        state_snapshots     → time >= warmup  (solo para KPIs; plot usa df completo)
    """
    warmup = config.warmup_time
    if warmup <= 0.0:
        return dfs  # sin warmup, no hay nada que filtrar

    filtered: dict[str, pd.DataFrame] = {}
    time_field: dict[str, str] = {
        "completed_racks":     "pickup_time",
        "os_arrivals":         "time",
        "rack_creations":      "time",
        "reception_events":    "time",
        "exit_queue_events":   "time",
        "exit_service_events": "time",
        "travel_audit_events": "time",
        "state_snapshots":     "time",
    }

    for name, df in dfs.items():
        field = time_field.get(name)
        if field and not df.empty and field in df.columns:
            filtered[name] = df[df[field] >= warmup].copy()
        else:
            filtered[name] = df

    return filtered


def summarize_results(
    dfs: dict[str, pd.DataFrame],
    config: SimulationConfig,
) -> dict:
    """
    Calcula KPIs de resumen respetando warmup_time.

    El denominador de throughput usa (simulation_horizon - warmup_time)
    para reflejar solo el período de medición estable.
    """
    warmup   = config.warmup_time
    horizon  = config.simulation_horizon
    eff_time = config.effective_horizon      # usa la property validada
    eff_h    = eff_time / 3600.0

    # Aplicar filtro de warmup antes de calcular cualquier KPI
    mdfs = _filter_by_warmup(dfs, config)

    summary: dict = {
        "warmup_time_s":       warmup,
        "effective_horizon_s": eff_time,
    }

    # ── Racks completados ──────────────────────────────────────────────────
    completed = mdfs["completed_racks"]
    if not completed.empty:
        total_racks = len(completed)
        total_os    = int(completed["n_os"].sum())

        summary["total_completed_racks"]    = total_racks
        summary["total_completed_os"]       = total_os
        summary["throughput_os_per_hour"]   = total_os / eff_h
        summary["throughput_racks_per_hour"]= total_racks / eff_h
        summary["mean_cycle_time_s"]        = float(completed["cycle_time_total"].mean())
        summary["p50_cycle_time_s"]         = float(completed["cycle_time_total"].quantile(0.50))
        summary["p90_cycle_time_s"]         = float(completed["cycle_time_total"].quantile(0.90))
        summary["p95_cycle_time_s"]         = float(completed["cycle_time_total"].quantile(0.95))
        summary["mean_n_stops"]             = float(completed["n_stops"].mean())
        summary["mean_travel_time_s"]       = float(completed["travel_time_total"].mean())
        summary["mean_queue_time_trip_s"]   = float(completed["queue_time_total"].mean())
        summary["mean_release_time_trip_s"] = float(completed["release_time_total"].mean())
    else:
        summary.update({
            "total_completed_racks":    0,
            "total_completed_os":       0,
            "throughput_os_per_hour":   0.0,
            "throughput_racks_per_hour":0.0,
            "mean_cycle_time_s":        0.0,
            "p50_cycle_time_s":         0.0,
            "p90_cycle_time_s":         0.0,
            "p95_cycle_time_s":         0.0,
            "mean_n_stops":             0.0,
            "mean_travel_time_s":       0.0,
            "mean_queue_time_trip_s":   0.0,
            "mean_release_time_trip_s": 0.0,
        })

    # ── Utilización de bots ────────────────────────────────────────────────
    audit = mdfs["travel_audit_events"]
    trips = pd.DataFrame()
    if not audit.empty and "event_type" in audit.columns:
        trips = audit[audit["event_type"] == "trip_completed"]

    if not trips.empty:
        total_bot_time = config.n_bots * eff_time
        t_travel  = float(trips["travel_time_total"].sum())
        t_queue   = float(trips["queue_time_total"].sum())
        t_release = float(trips["release_time_total"].sum())
        t_busy    = t_travel + t_queue + t_release

        summary["bot_utilization"]        = t_busy / total_bot_time
        summary["bot_util_travel_frac"]   = t_travel  / total_bot_time
        summary["bot_util_queue_frac"]    = t_queue   / total_bot_time
        summary["bot_util_release_frac"]  = t_release / total_bot_time
        summary["bot_util_idle_frac"]     = max(0.0, 1.0 - summary["bot_utilization"])
        summary["total_trips"]            = len(trips)
    else:
        summary.update({
            "bot_utilization":       0.0,
            "bot_util_travel_frac":  0.0,
            "bot_util_queue_frac":   0.0,
            "bot_util_release_frac": 0.0,
            "bot_util_idle_frac":    1.0,
            "total_trips":           0,
        })

    # ── Colas en salidas ───────────────────────────────────────────────────
    queue_ev = mdfs["exit_queue_events"]
    if not queue_ev.empty:
        summary["mean_exit_queue_delay_s"] = float(queue_ev["queue_delay_s"].mean())
        summary["p90_exit_queue_delay_s"]  = float(queue_ev["queue_delay_s"].quantile(0.90))
        summary["max_exit_queue_delay_s"]  = float(queue_ev["queue_delay_s"].max())
    else:
        summary.update({
            "mean_exit_queue_delay_s": 0.0,
            "p90_exit_queue_delay_s":  0.0,
            "max_exit_queue_delay_s":  0.0,
        })

    # ── Snapshots de buffer ────────────────────────────────────────────────
    snaps = mdfs["state_snapshots"]
    if not snaps.empty:
        summary["mean_os_buffer"]        = float(snaps["os_buffer_len"].mean())
        summary["mean_pending_racks"]    = float(snaps["pending_racks_len"].mean())
        summary["mean_ready_racks"]      = float(snaps["ready_racks_len"].mean())
        summary["mean_empty_racks"]      = float(snaps["empty_racks_level"].mean())
        summary["max_os_buffer"]         = float(snaps["os_buffer_len"].max())
        summary["max_pending_racks"]     = float(snaps["pending_racks_len"].max())
        summary["max_ready_racks"]       = float(snaps["ready_racks_len"].max())
    else:
        summary.update({
            "mean_os_buffer": 0.0, "mean_pending_racks": 0.0,
            "mean_ready_racks": 0.0, "mean_empty_racks": 0.0,
            "max_os_buffer": 0.0, "max_pending_racks": 0.0,
            "max_ready_racks": 0.0,
        })

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

    # ── KPIs respetando warmup ─────────────────────────────────────────────
    summary = summarize_results(dfs, config)
    print("\n=== Simulation Summary ===")
    pprint(summary)

    # ── Dashboard de comparación ───────────────────────────────────────────
    # Reemplazar estos valores con los del modelo analítico en Excel
    analytical_targets = {
        "throughput_os_per_hour": 693.0,     # objetivo de demanda
        "cycle_time_s":           None,      # completar desde Excel
        "bot_utilization":        None,      # completar desde Excel  [0–1]
        "mean_queue_delay_s":     None,      # completar desde Excel
    }
    # Limpiar Nones para que el dashboard no dibuje referencias vacías
    analytical_targets = {k: v for k, v in analytical_targets.items() if v is not None}

    build_dashboard(
        dfs=dfs,
        summary=summary,
        config=config,
        analytical_targets=analytical_targets,
        output_path="outputs/simulation_dashboard.png",
    )

    # ── Export CSV ─────────────────────────────────────────────────────────
    for name, df in dfs.items():
        if not df.empty:
            df.to_csv(f"outputs/{name}.csv", index=False)

    print("\nCSV y dashboard exportados en outputs/")


if __name__ == "__main__":
    main()