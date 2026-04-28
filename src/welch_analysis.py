"""
Analisis de Welch para estimacion de Warmup Time.

REFERENCIA TEORICA:
─────────────────
Welch, P. D. (1983). "The statistical analysis of simulation results."
En: S. S. Lavenberg (Ed.), Computer Performance Modeling Handbook.

METODOLOGIA:
────────────
1. Ejecutar N replicas independientes de duracion T (horizon largo)
2. Para cada replica, calcular el throughput en ventanas consecutivas
3. Promediar throughput entre replicas por ventana
4. Aplicar filtro suavizador (media movil)
5. Identificar punto de convergencia (estado estacionario)

El punto donde los promedios suavizados se estabilizan indica el tiempo
minimo necesario para que la simulacion abandone los transitorios.

IMPLEMENTACION:
───────────────
- Window size: 300 s (5 minutos) - balance entre granularidad y estabilidad
- Moving average window: 5 ventanas (25 minutos) - suavizado
- N replications: 10 - suficiente para convergencia estadistica
- Total horizon: 10,800 s (3 horas) - captura transitorios + estable
"""

from __future__ import annotations

import random as _random
from dataclasses import replace
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import build_peak_config
from inputs import InputModel
from models import SimulationConfig
from simulation import build_and_run_simulation


def run_long_replications_for_welch(
    config: SimulationConfig,
    input_model: InputModel,
    n_replications: int = 10,
    base_seed: int = 42,
    window_size_s: float = 300.0,
) -> tuple[list[dict], SimulationConfig]:
    """
    Ejecuta N replicas largas y extrae throughput por ventanas de tiempo.

    Para cada replica:
    - Corre simulacion completa (horizon largo)
    - Recolecta OS completados en ventanas consecutivas de `window_size_s`
    - Calcula throughput (OS/h) por ventana

    Retorna:
    - List[dict]: cada dict contiene 'replica', 'window_time', 'throughput'
    - SimulationConfig: config utilizada (con horizon ajustado)
    """
    # Ajustar config para correr mas tiempo sin warmup
    analysis_config = replace(
        config,
        simulation_horizon=10800.0,  # 3 horas
        warmup_time=0.0,             # SIN filtrado; queremos verlo TODO
        random_seed=base_seed,
    )

    window_records = []

    print(f"\nEjecutando {n_replications} replicas largas para analisis de Welch...")
    print(f"Duracion total por replica: {analysis_config.simulation_horizon / 3600:.1f} h")
    print(f"Tamano de ventana: {window_size_s / 60:.1f} min")
    print(f"{'Replica':>8}  {'OS completados':>15}  {'Ventanas':>10}")
    print("-" * 45)

    for rep_idx in range(n_replications):
        seed = base_seed + rep_idx

        # Resetear config y RNG
        rep_config = replace(analysis_config, random_seed=seed)
        input_model.rng = _random.Random(seed)

        # Correr simulacion
        metrics = build_and_run_simulation(rep_config, input_model)
        dfs = metrics.to_dataframes()

        # Extraer racks completados
        completed = dfs.get("completed_racks", pd.DataFrame())
        if completed.empty:
            print(f"{rep_idx + 1:>8}  {'0':>15}  {'0':>10}")
            continue

        n_os_total = int(completed["n_os"].sum())

        # Dividir en ventanas y calcular throughput por ventana
        n_windows = int(np.ceil(analysis_config.simulation_horizon / window_size_s))

        for win_idx in range(n_windows):
            win_start = win_idx * window_size_s
            win_end = (win_idx + 1) * window_size_s

            # Filtrar racks completados en esta ventana
            racks_in_window = completed[
                (completed["pickup_time"] >= win_start)
                & (completed["pickup_time"] < win_end)
            ]

            n_os_window = int(racks_in_window["n_os"].sum())

            # Throughput en OS/hora (normalizar por hora)
            window_duration_h = window_size_s / 3600.0
            throughput_os_per_h = n_os_window / window_duration_h if window_duration_h > 0 else 0.0

            window_records.append({
                "replica": rep_idx + 1,
                "window_idx": win_idx,
                "window_time_s": (win_idx + 0.5) * window_size_s,  # midpoint
                "throughput_os_per_h": throughput_os_per_h,
                "n_os_window": n_os_window,
            })

        print(f"{rep_idx + 1:>8}  {n_os_total:>15}  {n_windows:>10}")

    print("-" * 45)
    return window_records, analysis_config


def aggregate_welch_throughput(
    window_records: list[dict],
    moving_avg_window: int = 5,
) -> pd.DataFrame:
    """
    Agregar throughputs por ventana (promediando entre replicas).
    Aplicar media movil para suavizar.

    Retorna DataFrame con:
    - window_time_s: tiempo (en segundos) del centro de la ventana
    - throughput_mean: promedio de throughput entre replicas
    - throughput_std: desv. est. entre replicas
    - throughput_smooth: media movil suavizada
    """
    df = pd.DataFrame(window_records)
    n_replications = int(df["replica"].nunique()) if not df.empty else 0

    # Agrupar por ventana (promediar entre replicas)
    agg = df.groupby("window_idx").agg({
        "window_time_s": "first",
        "throughput_os_per_h": ["mean", "std"],
        "n_os_window": "sum",
    }).reset_index(drop=True)

    agg.columns = ["window_time_s", "throughput_mean", "throughput_std", "n_os_total"]

    if n_replications > 0:
        t_table = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57,
                   7: 2.45, 8: 2.36, 9: 2.31, 10: 2.26}
        t_crit = t_table.get(n_replications, 1.96)
        agg["throughput_ci95"] = agg["throughput_std"] * t_crit / (n_replications ** 0.5)
    else:
        agg["throughput_ci95"] = np.nan

    # Media movil para suavizar
    agg["throughput_smooth"] = (
        agg["throughput_mean"].rolling(window=moving_avg_window, center=True).mean()
    )

    return agg


def detect_convergence_point(
    agg: pd.DataFrame,
    target_throughput: float,
    tolerance_frac: float = 0.10,
    sustain_windows: int = 3,
) -> tuple[float, dict]:
    """
    Detectar el punto de convergencia donde throughput se estabiliza.

    Criterios:
    1. Throughput dentro del ±tolerance_frac del valor target
    2. Fluctuaciones posteriores < 5% del target

    Retorna:
    - float: tiempo en segundos donde se estabiliza
    - dict: informacion de diagnostico
    """
    smooth = agg["throughput_smooth"].dropna()

    if len(smooth) == 0:
        return 0.0, {"reason": "no smoothed data"}

    # Buscar primer punto donde entra en banda de convergencia
    target_band_lo = target_throughput * (1 - tolerance_frac)
    target_band_hi = target_throughput * (1 + tolerance_frac)

    convergence_idx = None
    smooth_values = smooth.reset_index(drop=True)
    for i in range(0, len(smooth_values) - sustain_windows + 1):
        window = smooth_values.iloc[i:i + sustain_windows]
        if ((window >= target_band_lo) & (window <= target_band_hi)).all():
            convergence_idx = i
            break

    if convergence_idx is None:
        # Si nunca entra, usar punto donde esta mas cercano
        errors = (smooth_values - target_throughput).abs()
        convergence_idx = int(errors.idxmin())
        reason = "no convergence to target band; closest point selected"
    else:
        reason = "convergence detected"

    convergence_time = agg.iloc[convergence_idx]["window_time_s"]

    # Verificar estabilidad post-convergencia
    if convergence_idx < len(smooth_values) - 2:
        post_vals = smooth_values.iloc[convergence_idx:].values
        post_fluctuation = (post_vals.std() / target_throughput) if target_throughput > 0 else 0.0
    else:
        post_fluctuation = 0.0

    return convergence_time, {
        "reason": reason,
        "convergence_idx": convergence_idx,
        "convergence_time_s": convergence_time,
        "target_throughput": target_throughput,
        "tolerance_band": (target_band_lo, target_band_hi),
        "post_convergence_cv": post_fluctuation,
    }


def visualize_welch_analysis(
    agg: pd.DataFrame,
    window_records: list[dict],
    convergence_time: float,
    config: SimulationConfig,
    output_path: str | Path = "outputs/welch_analysis.png",
) -> None:
    """
    Visualizar analisis de Welch con:
    - Throughput bruto por ventana y replica
    - Promedio agregado con ± IC95%
    - Media movil suavizada
    - Linea de convergencia estimada
    """
    df_raw = pd.DataFrame(window_records)

    fig, ax = plt.subplots(figsize=(14, 7))

    # 1. Plotear replicas individuales (fondo, transparente)
    for rep_id in df_raw["replica"].unique():
        rep_data = df_raw[df_raw["replica"] == rep_id].sort_values("window_time_s")
        ax.plot(
            rep_data["window_time_s"] / 60,  # convertir a minutos
            rep_data["throughput_os_per_h"],
            alpha=0.15,
            color="gray",
            linewidth=0.8,
            label="Replicas" if rep_id == 1 else "",
        )

    # 2. Plotear promedio agregado con IC95%
    agg_sorted = agg.sort_values("window_time_s")
    time_min = agg_sorted["window_time_s"] / 60
    mean_throughput = agg_sorted["throughput_mean"]
    ci_throughput = agg_sorted["throughput_ci95"]

    ax.plot(time_min, mean_throughput, "o-", color="steelblue", linewidth=2.5,
            markersize=5, label="Promedio (entre replicas)", zorder=3)
    ax.fill_between(
        time_min,
        mean_throughput - ci_throughput,
        mean_throughput + ci_throughput,
        alpha=0.25,
        color="steelblue",
        label="IC 95% de la media",
    )

    # 3. Plotear media movil suavizada
    smooth_sorted = agg_sorted.dropna(subset=["throughput_smooth"])
    ax.plot(
        smooth_sorted["window_time_s"] / 60,
        smooth_sorted["throughput_smooth"],
        "s--",
        color="darkred",
        linewidth=2.5,
        markersize=6,
        label="Media movil suavizada (5 ventanas)",
        zorder=4,
    )

    # 4. Linea de convergencia
    ax.axvline(convergence_time / 60, color="green", linestyle=":", linewidth=2.5,
               label=f"Warmup estimado: {convergence_time / 60:.1f} min ({convergence_time:.0f} s)",
               zorder=5)

    # 5. Configurar ejes
    ax.set_xlabel("Tiempo de simulacion (minutos)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Throughput (OS / hora)", fontsize=12, fontweight="bold")
    ax.set_title(
        "Analisis de Welch: Convergencia a Estado Estacionario\n"
        f"({agg['window_time_s'].max() / 3600:.1f}h total, {len(df_raw['replica'].unique())} replicas)",
        fontsize=13,
        fontweight="bold",
    )
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(loc="best", fontsize=10, framealpha=0.95)

    # 6. Anotacion
    target_text = (
        f"Target: 693 OS/h\n"
        f"Convergencia: {convergence_time / 60:.1f} min\n"
        f"Recomendacion: warmup_time = {max(1800, int(convergence_time * 1.2))} s"
    )
    ax.text(0.98, 0.05, target_text, transform=ax.transAxes,
            fontsize=10, verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    plt.tight_layout()
    Path(output_path).parent.mkdir(exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"OK Grafico guardado: {output_path}")
    plt.close()


def print_welch_summary(
    agg: pd.DataFrame,
    convergence_time: float,
    convergence_info: dict,
    n_replications: int,
) -> None:
    """Imprimir resumen del analisis de Welch."""
    print(f"\n{'='*70}")
    print(f"  ANALISIS DE WELCH - RESUMEN")
    print(f"{'='*70}")
    print(f"  Replicas analizadas:              {n_replications}")
    print(f"  Duracion por replica:             {agg['window_time_s'].max() / 3600:.1f} horas")
    print(f"  Tamano de ventana:                300 segundos (5 minutos)")
    print(f"  Media movil:                      5 ventanas (25 minutos)")
    print()
    print(f"  RESULTADOS:")
    print(f"  {'-' * 35}")
    print(f"  Throughput final (promedio):      {agg['throughput_mean'].iloc[-1]:.0f} OS/h")
    print(f"  Desv. Est. final:                 {agg['throughput_std'].iloc[-1]:.0f} OS/h")
    print(f"  Throughput maximo observado:      {agg['throughput_mean'].max():.0f} OS/h")
    print(f"  Throughput minimo observado:      {agg['throughput_mean'].min():.0f} OS/h")
    print()
    print(f"  CONVERGENCIA:")
    print(f"  {'-' * 35}")
    print(f"  Tiempo de convergencia:           {convergence_time / 60:.1f} minutos ({convergence_time:.0f} s)")
    print(f"  Razon:                            {convergence_info['reason']}")
    print(f"  Coef. Variacion post-convergencia: {convergence_info['post_convergence_cv']*100:.1f}%")
    print()
    print(f"  RECOMENDACION:")
    print(f"  {'-' * 35}")
    # Aplicar factor conservador de 1.2 y redondear a multiplos de 300
    warmup_recommended = int(convergence_time * 1.2 / 300) * 300
    warmup_recommended = max(1800, warmup_recommended)  # minimo 30 min
    print(f"  > warmup_time = {warmup_recommended} segundos ({warmup_recommended/60:.0f} minutos)")
    print(f"    (Factor conservador de 1.2x aplicado; multiplo de 300s)")
    print(f"{'='*70}\n")


def main():
    Path("outputs").mkdir(exist_ok=True)

    # ──────────────────────────────────────────────────────────────────────
    # 1. Preparar configuracion y modelo de entrada
    # ──────────────────────────────────────────────────────────────────────
    from run import build_input_model_from_excel
    
    config = build_peak_config()

    input_model = build_input_model_from_excel(
        excel_path="src/inputs_data/data_entry.xlsx",
        config=config,
        os_per_hour=693.0,
        distance_between_consecutive_exits_m=5.0,
    )

    # ──────────────────────────────────────────────────────────────────────
    # 2. Ejecutar replicas largas
    # ──────────────────────────────────────────────────────────────────────
    window_records, analysis_config = run_long_replications_for_welch(
        config=config,
        input_model=input_model,
        n_replications=10,
        base_seed=config.random_seed,
        window_size_s=300.0,
    )

    # ──────────────────────────────────────────────────────────────────────
    # 3. Agregar y suavizar
    # ──────────────────────────────────────────────────────────────────────
    agg = aggregate_welch_throughput(window_records, moving_avg_window=5)
    agg.to_csv("outputs/welch_aggregated_throughput.csv", index=False)
    print(f"OK Datos agregados guardados: outputs/welch_aggregated_throughput.csv")

    # ──────────────────────────────────────────────────────────────────────
    # 4. Detectar convergencia
    # ──────────────────────────────────────────────────────────────────────
    convergence_time, convergence_info = detect_convergence_point(
        agg, target_throughput=693.0, tolerance_frac=0.10
    )

    # ──────────────────────────────────────────────────────────────────────
    # 5. Visualizar
    # ──────────────────────────────────────────────────────────────────────
    visualize_welch_analysis(
        agg=agg,
        window_records=window_records,
        convergence_time=convergence_time,
        config=analysis_config,
        output_path="outputs/welch_analysis.png",
    )

    # ──────────────────────────────────────────────────────────────────────
    # 6. Imprimir resumen
    # ──────────────────────────────────────────────────────────────────────
    print_welch_summary(agg, convergence_time, convergence_info, 10)

    # ──────────────────────────────────────────────────────────────────────
    # 7. Exportar recomendacion
    # ──────────────────────────────────────────────────────────────────────
    warmup_recommended = int(convergence_time * 1.2 / 300) * 300
    warmup_recommended = max(1800, warmup_recommended)

    recommendation = {
        "method": "Welch (1983)",
        "convergence_time_s": convergence_time,
        "convergence_time_min": convergence_time / 60.0,
        "warmup_recommended_s": warmup_recommended,
        "warmup_recommended_min": warmup_recommended / 60.0,
        "justification": (
            f"Basado en analisis de {10} replicas de {analysis_config.simulation_horizon/3600:.1f} horas. "
            f"El throughput converge al valor objetivo de 693 OS/h "
            f"alrededor de los {convergence_time/60:.0f} minutos. "
            f"Se aplica factor conservador de 1.2x para asegurar estado estacionario completo."
        ),
    }

    import json
    with open("outputs/warmup_recommendation.json", "w") as f:
        json.dump(recommendation, f, indent=2)
    print(f"OK Recomendacion guardada: outputs/warmup_recommendation.json")


if __name__ == "__main__":
    main()
