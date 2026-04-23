from __future__ import annotations

import random as _random
from dataclasses import replace
from pathlib import Path
from pprint import pprint

import pandas as pd

from config import build_peak_config
from dashboard import build_dashboard, build_replications_dashboard
from inputs import InputModel
from models import SimulationConfig
from simulation import build_and_run_simulation


# ── Helpers de tiempo de release ───────────────────────────────────────────────
def _build_release_time_by_n_os_stop(
    config: SimulationConfig, max_os_per_stop: int
) -> dict[int, float]:
    release_base_time_s = config.turn_time_s
    release_time_per_os_s = config.pallet_load_unload_time_s / max_os_per_stop
    return {
        n: release_base_time_s + (n * release_time_per_os_s)
        for n in range(1, max_os_per_stop + 1)
    }


# ── Lectura de Excel ───────────────────────────────────────────────────────────
def build_input_model_from_excel(
    excel_path: str | Path,
    config: SimulationConfig,
    os_per_hour: float = 693.0,
    distance_between_consecutive_exits_m: float = 5.0,
) -> InputModel:
    """
    Construye InputModel leyendo data_entry.xlsx.
    Recibe config para derivar tiempos de release.
    """
    excel_path = Path(excel_path)

    destination_df = pd.read_excel(
        excel_path, sheet_name="destination_distribution",
        usecols=["destination_id", "probability"],
    ).dropna(subset=["destination_id", "probability"])
    destination_distribution = dict(zip(
        destination_df["destination_id"].astype(str),
        destination_df["probability"].astype(float),
    ))

    dest_exit_df = pd.read_excel(
        excel_path, sheet_name="destination_to_exit",
        usecols=["destination_id", "exit_id"],
    ).dropna(subset=["destination_id", "exit_id"])
    destination_to_exit = dict(zip(
        dest_exit_df["destination_id"].astype(str),
        dest_exit_df["exit_id"].astype(str),
    ))

    segment_df = pd.read_excel(
        excel_path, sheet_name="segment_distribution_by_dest",
        usecols=["destination_id", "segment", "probability"],
    ).dropna(subset=["destination_id", "segment", "probability"])
    segment_distribution_by_destination: dict[str, dict[str, float]] = {}
    for dest_id, group in segment_df.groupby("destination_id"):
        segment_distribution_by_destination[str(dest_id)] = {
            str(row.segment): float(row.probability)
            for row in group.itertuples(index=False)
        }

    recv_df = pd.read_excel(
        excel_path, sheet_name="travel_receiving_to_exit",
        usecols=["exit_id", "travel_distance_m"],
    ).dropna(subset=["exit_id", "travel_distance_m"])
    travel_distances_receiving_to_exit = dict(zip(
        recv_df["exit_id"].astype(str),
        recv_df["travel_distance_m"].astype(float),
    ))

    ret_df = pd.read_excel(
        excel_path, sheet_name="travel_exit_to_return",
        usecols=["exit_id", "travel_distance_m"],
    ).dropna(subset=["exit_id", "travel_distance_m"])
    travel_distances_exit_to_return = dict(zip(
        ret_df["exit_id"].astype(str),
        ret_df["travel_distance_m"].astype(float),
    ))

    rack_prep_time_by_n_os = {1: 8.0, 2: 12.0, 3: 16.0, 4: 20.0, 5: 24.0}
    release_time_by_n_os_stop = _build_release_time_by_n_os_stop(
        config=config, max_os_per_stop=max(rack_prep_time_by_n_os),
    )

    return InputModel(
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


# ── Filtro de warmup ───────────────────────────────────────────────────────────
def _filter_by_warmup(
    dfs: dict[str, pd.DataFrame], config: SimulationConfig
) -> dict[str, pd.DataFrame]:
    warmup = config.warmup_time
    if warmup <= 0.0:
        return dfs

    time_field = {
        "completed_racks":     "pickup_time",
        "os_arrivals":         "time",
        "rack_creations":      "time",
        "reception_events":    "time",
        "exit_queue_events":   "time",
        "exit_service_events": "time",
        "travel_audit_events": "time",
        "state_snapshots":     "time",
    }
    filtered: dict[str, pd.DataFrame] = {}
    for name, df in dfs.items():
        field = time_field.get(name)
        if field and not df.empty and field in df.columns:
            filtered[name] = df[df[field] >= warmup].copy()
        else:
            filtered[name] = df
    return filtered


# ── Resumen de KPIs ────────────────────────────────────────────────────────────
def summarize_results(
    dfs: dict[str, pd.DataFrame],
    config: SimulationConfig,
) -> dict:
    warmup   = config.warmup_time
    horizon  = config.simulation_horizon
    eff_time = config.effective_horizon
    eff_h    = eff_time / 3600.0

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
        summary.update({
            "total_completed_racks":     total_racks,
            "total_completed_os":        total_os,
            "throughput_os_per_hour":    total_os / eff_h,
            "throughput_racks_per_hour": total_racks / eff_h,
            "mean_cycle_time_s":         float(completed["cycle_time_total"].mean()),
            "p50_cycle_time_s":          float(completed["cycle_time_total"].quantile(0.50)),
            "p90_cycle_time_s":          float(completed["cycle_time_total"].quantile(0.90)),
            "p95_cycle_time_s":          float(completed["cycle_time_total"].quantile(0.95)),
            "mean_n_stops":              float(completed["n_stops"].mean()),
            "mean_travel_time_s":        float(completed["travel_time_total"].mean()),
            "mean_queue_time_trip_s":    float(completed["queue_time_total"].mean()),
            "mean_release_time_trip_s":  float(completed["release_time_total"].mean()),
        })
    else:
        summary.update({
            "total_completed_racks": 0, "total_completed_os": 0,
            "throughput_os_per_hour": 0.0, "throughput_racks_per_hour": 0.0,
            "mean_cycle_time_s": 0.0, "p50_cycle_time_s": 0.0,
            "p90_cycle_time_s": 0.0, "p95_cycle_time_s": 0.0,
            "mean_n_stops": 0.0, "mean_travel_time_s": 0.0,
            "mean_queue_time_trip_s": 0.0, "mean_release_time_trip_s": 0.0,
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
        summary.update({
            "bot_utilization":        t_busy / total_bot_time,
            "bot_util_travel_frac":   t_travel  / total_bot_time,
            "bot_util_queue_frac":    t_queue   / total_bot_time,
            "bot_util_release_frac":  t_release / total_bot_time,
            "bot_util_idle_frac":     max(0.0, 1.0 - t_busy / total_bot_time),
            "total_trips":            len(trips),
        })
    else:
        summary.update({
            "bot_utilization": 0.0, "bot_util_travel_frac": 0.0,
            "bot_util_queue_frac": 0.0, "bot_util_release_frac": 0.0,
            "bot_util_idle_frac": 1.0, "total_trips": 0,
        })

    # ── Colas en salidas ───────────────────────────────────────────────────
    queue_ev = mdfs["exit_queue_events"]
    if not queue_ev.empty:
        summary.update({
            "mean_exit_queue_delay_s": float(queue_ev["queue_delay_s"].mean()),
            "p90_exit_queue_delay_s":  float(queue_ev["queue_delay_s"].quantile(0.90)),
            "max_exit_queue_delay_s":  float(queue_ev["queue_delay_s"].max()),
        })
    else:
        summary.update({
            "mean_exit_queue_delay_s": 0.0,
            "p90_exit_queue_delay_s":  0.0,
            "max_exit_queue_delay_s":  0.0,
        })

    # ── Snapshots de buffer ────────────────────────────────────────────────
    snaps = mdfs["state_snapshots"]
    if not snaps.empty:
        summary.update({
            "mean_os_buffer":     float(snaps["os_buffer_len"].mean()),
            "mean_pending_racks": float(snaps["pending_racks_len"].mean()),
            "mean_ready_racks":   float(snaps["ready_racks_len"].mean()),
            "mean_empty_racks":   float(snaps["empty_racks_level"].mean()),
            "max_os_buffer":      float(snaps["os_buffer_len"].max()),
            "max_pending_racks":  float(snaps["pending_racks_len"].max()),
            "max_ready_racks":    float(snaps["ready_racks_len"].max()),
        })
    else:
        summary.update({
            "mean_os_buffer": 0.0, "mean_pending_racks": 0.0,
            "mean_ready_racks": 0.0, "mean_empty_racks": 0.0,
            "max_os_buffer": 0.0, "max_pending_racks": 0.0,
            "max_ready_racks": 0.0,
        })

    return summary


# ── Múltiples réplicas ─────────────────────────────────────────────────────────
def run_replications(
    config: SimulationConfig,
    input_model: InputModel,
    n_replications: int = 10,
    base_seed: int = 42,
) -> list[dict]:
    """
    Ejecuta N réplicas variando únicamente la semilla aleatoria.

    Para cada réplica:
      - Se crea una nueva SimulationConfig con random_seed = base_seed + i
      - Se resetea el RNG del InputModel (sin releer Excel)
      - Se corre la simulación completa y se calcula el summary

    Retorna lista de summaries (uno por réplica) con campo 'replica' agregado.
    """
    summaries = []
    print(f"\nCorriendo {n_replications} réplicas...")
    print(f"{'Réplica':>8}  {'Throughput':>12}  {'Cycle p50':>10}  {'Bot util':>9}  {'Idle':>7}")
    print("─" * 58)

    for i in range(n_replications):
        seed = base_seed + i

        # Nueva config con semilla distinta (todo lo demás igual)
        rep_config = replace(config, random_seed=seed)

        # Resetear RNG del input model (evita releer Excel)
        input_model.rng = _random.Random(seed)

        metrics = build_and_run_simulation(rep_config, input_model)
        dfs     = metrics.to_dataframes()
        summary = summarize_results(dfs, rep_config)
        summary["replica"] = i + 1
        summaries.append(summary)

        print(
            f"{i+1:>8}  "
            f"{summary['throughput_os_per_hour']:>10.0f}/h  "
            f"{summary['p50_cycle_time_s']:>9.1f}s  "
            f"{summary['bot_utilization']*100:>8.1f}%  "
            f"{summary['bot_util_idle_frac']*100:>6.1f}%"
        )

    print("─" * 58)
    return summaries


def aggregate_replications(summaries: list[dict]) -> dict:
    """
    Para cada KPI escalar calcula: mean, std e IC95%.

    IC95% = mean ± t(0.025, N-1) × std / √N

    t crítico: usa scipy si está disponible, si no usa aproximación normal (z=1.96).
    Para N ≥ 10 la diferencia es < 0.15 puntos.
    """
    try:
        from scipy.stats import t as t_dist
        def t_crit(n: int) -> float:
            return float(t_dist.ppf(0.975, df=n - 1))
    except ImportError:
        def t_crit(n: int) -> float:
            # Aproximación t → z para N grande; conservador para N pequeño
            table = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57,
                     7: 2.45, 8: 2.36, 9: 2.31, 10: 2.26}
            return table.get(n, 1.96)

    df = pd.DataFrame(summaries)
    N  = len(df)
    tc = t_crit(N)

    scalar_cols = [c for c in df.columns if c not in ("replica",) and pd.api.types.is_numeric_dtype(df[c])]

    agg: dict = {"n_replications": N, "t_critical_95": tc}
    for col in scalar_cols:
        m  = float(df[col].mean())
        s  = float(df[col].std(ddof=1))
        ci = tc * s / (N ** 0.5)
        agg[col]           = m
        agg[f"{col}_std"]  = s
        agg[f"{col}_ci95"] = ci
        agg[f"{col}_lo"]   = m - ci
        agg[f"{col}_hi"]   = m + ci

    return agg


def _print_aggregated_summary(agg: dict, analytical_targets: dict) -> None:
    """Imprime tabla de KPIs clave con IC95% y comparación vs analítico."""
    N  = agg["n_replications"]
    tc = agg["t_critical_95"]
    print(f"\n{'='*62}")
    print(f"  Resumen agregado — {N} réplicas  (t₀.₀₂₅,{N-1} = {tc:.3f})")
    print(f"{'='*62}")
    print(f"  {'KPI':<30} {'Media':>9}  {'IC95% ±':>9}  {'vs analítico':>13}")
    print(f"  {'-'*58}")

    kpis = [
        ("throughput_os_per_hour",  "Throughput (OS/h)",    "throughput_os_per_hour"),
        ("p50_cycle_time_s",        "Cycle time p50 (s)",   "cycle_time_s"),
        ("mean_cycle_time_s",       "Cycle time media (s)",  None),
        ("bot_utilization",         "Bot utilización",      "bot_utilization"),
        ("bot_util_idle_frac",      "Bot idle",              None),
        ("mean_exit_queue_delay_s", "Queue delay media (s)", "mean_queue_delay_s"),
    ]

    for key, label, target_key in kpis:
        if key not in agg:
            continue
        m   = agg[key]
        ci  = agg.get(f"{key}_ci95", 0.0)
        lo  = agg.get(f"{key}_lo", m)
        hi  = agg.get(f"{key}_hi", m)

        is_pct = "frac" in key or key == "bot_utilization"
        fmt    = f"{m*100:.1f}%" if is_pct else f"{m:.1f}"
        fmt_ci = f"{ci*100:.1f}pp" if is_pct else f"{ci:.1f}"

        if target_key and target_key in analytical_targets:
            tval = analytical_targets[target_key]
            within = "✓ dentro CI" if lo <= tval <= hi else "✗ fuera CI"
            tval_fmt = f"{tval*100:.1f}%" if is_pct else f"{tval:.1f}"
            vs = f"{tval_fmt} [{within}]"
        else:
            vs = "—"

        print(f"  {label:<30} {fmt:>9}  {fmt_ci:>9}  {vs:>13}")

    print(f"{'='*62}\n")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    # ── Configuración ──────────────────────────────────────────────────────
    config = build_peak_config()

    input_model = build_input_model_from_excel(
        excel_path="src/inputs_data/data_entry.xlsx",
        config=config,
        os_per_hour=693.0,
        distance_between_consecutive_exits_m=5.0,
    )

    analytical_targets = {
        "throughput_os_per_hour": 693.0,
        # "cycle_time_s":         ...,   # completar desde modelo analítico
        # "bot_utilization":      ...,   # completar desde modelo analítico
        # "mean_queue_delay_s":   ...,   # completar desde modelo analítico
    }
    analytical_targets = {k: v for k, v in analytical_targets.items() if v is not None}

    Path("outputs").mkdir(exist_ok=True)

    # ── Réplica única (dashboard detallado) ────────────────────────────────
    print("Corriendo réplica base para dashboard detallado...")
    metrics = build_and_run_simulation(config, input_model)
    dfs     = metrics.to_dataframes()
    summary = summarize_results(dfs, config)

    print("\n=== Réplica base ===")
    pprint({k: v for k, v in summary.items() if not k.endswith("_s") or "time" in k})

    build_dashboard(
        dfs=dfs,
        summary=summary,
        config=config,
        analytical_targets=analytical_targets,
        output_path="outputs/simulation_dashboard.png",
    )

    for name, df in dfs.items():
        if not df.empty:
            df.to_csv(f"outputs/{name}.csv", index=False)

    # ── Múltiples réplicas ─────────────────────────────────────────────────
    N_REPLICATIONS = 10   # ← ajustar según tiempo disponible

    # Resetear RNG del input_model al seed base antes de las réplicas
    input_model.rng = _random.Random(config.random_seed)

    summaries = run_replications(
        config=config,
        input_model=input_model,
        n_replications=N_REPLICATIONS,
        base_seed=config.random_seed,
    )
    agg = aggregate_replications(summaries)

    _print_aggregated_summary(agg, analytical_targets)

    # Dashboard de réplicas
    build_replications_dashboard(
        summaries=summaries,
        agg=agg,
        config=config,
        analytical_targets=analytical_targets,
        output_path="outputs/replications_dashboard.png",
    )

    # CSV con una fila por réplica
    pd.DataFrame(summaries).to_csv("outputs/replications_summary.csv", index=False)
    print("Outputs exportados en outputs/")


if __name__ == "__main__":
    main()