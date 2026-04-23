from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Any, Dict

from models import SimulationConfig


# ── Paleta ─────────────────────────────────────────────────────────────────────
_SIM  = "#1D9E75"   # teal  → simulación
_ANA  = "#E24B4A"   # rojo  → modelo analítico
_NEU  = "#888780"   # gris  → referencia secundaria
_TRAV = "#378ADD"   # azul  → tiempo de viaje
_WAIT = "#EF9F27"   # ámbar → espera en cola
_REL  = "#5DCAA5"   # verde claro → release en salida
_IDLE = "#D3D1C7"   # gris claro → idle


# ── Helpers ────────────────────────────────────────────────────────────────────
def _style_ax(ax: plt.Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    ax.set_xlabel(xlabel, fontsize=8, labelpad=4)
    ax.set_ylabel(ylabel, fontsize=8, labelpad=4)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4, zorder=0)


def _vline(ax: plt.Axes, x: float, label: str, color: str = _ANA) -> None:
    ax.axvline(x, color=color, linestyle="--", linewidth=1.3, label=label, zorder=5)


def _hline(ax: plt.Axes, y: float, label: str, color: str = _ANA) -> None:
    ax.axhline(y, color=color, linestyle="--", linewidth=1.3, label=label, zorder=5)


def _no_data(ax: plt.Axes) -> None:
    ax.text(0.5, 0.5, "Sin datos en ventana de medición",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=9, color=_NEU)


# ── Panel 1: Throughput en el tiempo ──────────────────────────────────────────
def _plot_throughput(
    ax: plt.Axes,
    completed: pd.DataFrame,
    warmup: float,
    horizon: float,
    targets: Dict[str, float],
) -> None:
    _style_ax(ax, "Throughput — OS completadas / hora",
              xlabel="Tiempo (s)", ylabel="OS / hora")

    if completed.empty:
        _no_data(ax)
        return

    # Rolling sobre ventana de 10 minutos
    window_s = 600.0
    times = np.arange(warmup + window_s, horizon + 1, 60.0)
    rolling = []
    for t in times:
        mask = (completed["pickup_time"] >= t - window_s) & (completed["pickup_time"] < t)
        rolling.append(completed.loc[mask, "n_os"].sum() / (window_s / 3600.0))

    ax.plot(times, rolling, color=_SIM, linewidth=1.5,
            label="Simulación (ventana 10 min)", zorder=3)

    # Promedio global de la simulación
    avg_sim = completed["n_os"].sum() / ((horizon - warmup) / 3600.0)
    ax.axhline(avg_sim, color=_SIM, linestyle=":", linewidth=1.1,
               label=f"Promedio sim: {avg_sim:,.0f} OS/h", zorder=4)

    if "throughput_os_per_hour" in targets:
        t_val = targets["throughput_os_per_hour"]
        _hline(ax, t_val, f"Analítico: {t_val:,.0f} OS/h")

    # Brecha
    if "throughput_os_per_hour" in targets:
        gap = avg_sim - targets["throughput_os_per_hour"]
        sign = "+" if gap >= 0 else ""
        ax.text(0.98, 0.05, f"Δ = {sign}{gap:,.0f} OS/h",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color=_ANA if gap < 0 else _SIM)

    ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.set_xlim(warmup, horizon)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))


# ── Panel 2: Distribución de cycle time ───────────────────────────────────────
def _plot_cycle_time(
    ax: plt.Axes,
    completed: pd.DataFrame,
    targets: Dict[str, float],
) -> None:
    _style_ax(ax, "Cycle time por rack",
              xlabel="Segundos", ylabel="Frecuencia")

    if completed.empty:
        _no_data(ax)
        return

    ct = completed["cycle_time_total"].dropna()
    ax.hist(ct, bins=30, color=_SIM, alpha=0.75,
            edgecolor="white", linewidth=0.4, zorder=3)

    p50, p90, p95 = ct.quantile([0.50, 0.90, 0.95])
    _vline(ax, p50, f"p50: {p50:.0f}s", color=_SIM)
    _vline(ax, p90, f"p90: {p90:.0f}s", color=_NEU)
    _vline(ax, p95, f"p95: {p95:.0f}s", color=_NEU)

    if "cycle_time_s" in targets:
        _vline(ax, targets["cycle_time_s"],
               f"Analítico: {targets['cycle_time_s']:.0f}s")

    ax.legend(fontsize=7, frameon=False)


# ── Panel 3: Utilización de bots ──────────────────────────────────────────────
def _plot_bot_utilization(
    ax: plt.Axes,
    audit: pd.DataFrame,
    config: SimulationConfig,
    warmup: float,
    horizon: float,
    targets: Dict[str, float],
) -> None:
    effective = horizon - warmup
    total_bot_time = config.n_bots * effective

    trips = pd.DataFrame()
    if not audit.empty:
        trips = audit[
            (audit["event_type"] == "trip_completed") &
            (audit["time"] >= warmup)
        ]

    if trips.empty:
        _style_ax(ax, "Utilización de bots (agregada)")
        _no_data(ax)
        return

    t_travel  = float(trips["travel_time_total"].sum())
    t_queue   = float(trips["queue_time_total"].sum())
    t_release = float(trips["release_time_total"].sum())
    t_busy    = t_travel + t_queue + t_release
    t_idle    = max(0.0, total_bot_time - t_busy)

    util_sim = t_busy / total_bot_time * 100.0

    title = f"Utilización de bots — sim: {util_sim:.1f}%"
    if "bot_utilization" in targets:
        title += f"  ·  analítico: {targets['bot_utilization'] * 100:.1f}%"
    _style_ax(ax, title, ylabel="Tiempo total del pool (s)")

    labels  = ["Viaje", "Release en salida", "Espera cola", "Idle"]
    values  = [t_travel, t_release, t_queue, t_idle]
    colors  = [_TRAV, _REL, _WAIT, _IDLE]

    bars = ax.barh(labels, values, color=colors, edgecolor="white",
                   linewidth=0.5, zorder=3)

    for bar, val in zip(bars, values):
        pct = val / total_bot_time * 100.0
        x_pos = bar.get_width() + total_bot_time * 0.005
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2.0,
                f"{pct:.1f}%", va="center", fontsize=8)

    if "bot_utilization" in targets:
        ref_x = targets["bot_utilization"] * total_bot_time
        ax.axvline(ref_x, color=_ANA, linestyle="--", linewidth=1.3,
                   label=f"Analítico: {targets['bot_utilization']*100:.1f}%")
        ax.legend(fontsize=7, frameon=False)

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.4, zorder=0)
    ax.grid(axis="y", visible=False)


# ── Panel 4: Cola por salida ──────────────────────────────────────────────────
def _plot_queue_by_exit(
    ax: plt.Axes,
    queue_ev: pd.DataFrame,
    targets: Dict[str, float],
) -> None:
    _style_ax(ax, "Delay en cola — por salida",
              xlabel="Salida", ylabel="Delay (s)")

    if queue_ev.empty:
        _no_data(ax)
        return

    stats = (
        queue_ev.groupby("exit_id")["queue_delay_s"]
        .agg(mean="mean", p90=lambda x: x.quantile(0.90))
        .sort_values("mean", ascending=False)
    )

    x = np.arange(len(stats))
    w = 0.55

    ax.bar(x, stats["mean"], width=w, color=_SIM, alpha=0.85,
           label="Promedio", zorder=3)
    ax.bar(x, stats["p90"] - stats["mean"], width=w,
           bottom=stats["mean"], color=_WAIT, alpha=0.6,
           label="p90", zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(
        [e.replace("exit_", "S") for e in stats.index],
        rotation=45, ha="right", fontsize=7,
    )

    if "mean_queue_delay_s" in targets:
        _hline(ax, targets["mean_queue_delay_s"],
               f"Analítico: {targets['mean_queue_delay_s']:.1f}s")

    ax.legend(fontsize=7, frameon=False)


# ── Panel 5: Niveles de buffer ────────────────────────────────────────────────
def _plot_buffers(
    ax: plt.Axes,
    snapshots: pd.DataFrame,
    warmup: float,
) -> None:
    _style_ax(ax, "Niveles de buffer en el tiempo",
              xlabel="Tiempo (s)", ylabel="Cantidad")

    if snapshots.empty:
        _no_data(ax)
        return

    s = snapshots[snapshots["time"] >= warmup]
    if s.empty:
        _no_data(ax)
        return

    ax.plot(s["time"], s["os_buffer_len"],     color=_TRAV, linewidth=1.2,
            label="OS en buffer")
    ax.plot(s["time"], s["pending_racks_len"], color=_WAIT, linewidth=1.2,
            label="Racks pendientes")
    ax.plot(s["time"], s["ready_racks_len"],   color=_SIM,  linewidth=1.2,
            label="Racks listos")
    ax.plot(s["time"], s["empty_racks_level"], color=_NEU,  linewidth=1.0,
            linestyle="--", label="Racks vacíos")

    ax.legend(fontsize=7, frameon=False, ncol=2)
    ax.set_xlim(s["time"].min(), s["time"].max())


# ── Panel 6: Distribución de stops ───────────────────────────────────────────
def _plot_stops_distribution(
    ax: plt.Axes,
    completed: pd.DataFrame,
) -> None:
    _style_ax(ax, "Distribución de stops por rack",
              xlabel="N° stops", ylabel="Frecuencia")

    if completed.empty:
        _no_data(ax)
        return

    counts = completed["n_stops"].value_counts().sort_index()
    x = [str(v) for v in counts.index]
    ax.bar(x, counts.values, color=_SIM, alpha=0.85,
           edgecolor="white", linewidth=0.5, zorder=3)

    mean_stops = completed["n_stops"].mean()
    ax.text(0.98, 0.95, f"Promedio: {mean_stops:.2f} stops/rack",
            transform=ax.transAxes, ha="right", va="top", fontsize=8)

    # % de racks con 1 stop (máxima eficiencia de viaje)
    pct_1stop = (completed["n_stops"] == 1).mean() * 100
    ax.text(0.98, 0.85, f"1 stop: {pct_1stop:.1f}% de racks",
            transform=ax.transAxes, ha="right", va="top", fontsize=8, color=_SIM)


# ── Entry point ───────────────────────────────────────────────────────────────
def build_dashboard(
    dfs: Dict[str, pd.DataFrame],
    summary: Dict[str, Any],
    config: SimulationConfig,
    analytical_targets: Dict[str, float],
    output_path: str | Path = "simulation_dashboard.png",
) -> Path:
    """
    Genera dashboard de 6 paneles comparando simulación vs modelo analítico.

    Claves válidas para analytical_targets:
        throughput_os_per_hour  → throughput objetivo (OS/h)
        cycle_time_s            → cycle time promedio esperado (s)
        bot_utilization         → utilización esperada en [0, 1]
        mean_queue_delay_s      → delay promedio en cola esperado (s)
    """
    warmup  = config.warmup_time
    horizon = config.simulation_horizon

    completed = dfs.get("completed_racks", pd.DataFrame())
    snapshots = dfs.get("state_snapshots", pd.DataFrame())
    queue_ev  = dfs.get("exit_queue_events", pd.DataFrame())
    audit     = dfs.get("travel_audit_events", pd.DataFrame())

    # Aplicar filtro de warmup sobre los DataFrames que llegan al dashboard
    # (summarize_results ya los filtró, pero las funciones de plot
    #  reciben los dfs completos para poder calcular rolling sobre el tiempo)
    if not completed.empty and warmup > 0:
        completed = completed[completed["pickup_time"] >= warmup].copy()
    if not queue_ev.empty and warmup > 0:
        queue_ev = queue_ev[queue_ev["time"] >= warmup].copy()

    fig, axes = plt.subplots(3, 2, figsize=(14, 13))
    fig.patch.set_facecolor("white")

    warmup_label = f"warmup = {warmup:.0f}s" if warmup > 0 else "sin warmup"
    fig.suptitle(
        f"Simulación DES — BlueExpress RIL-M  ·  {config.n_bots} bots  ·  {warmup_label}",
        fontsize=12, fontweight="bold", y=0.998,
    )

    _plot_throughput(axes[0, 0], completed, warmup, horizon, analytical_targets)
    _plot_cycle_time(axes[0, 1], completed, analytical_targets)
    _plot_bot_utilization(axes[1, 0], audit, config, warmup, horizon, analytical_targets)
    _plot_queue_by_exit(axes[1, 1], queue_ev, analytical_targets)
    _plot_buffers(axes[2, 0], snapshots, warmup)
    _plot_stops_distribution(axes[2, 1], completed)

    plt.tight_layout(rect=[0, 0, 1, 0.996])

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Dashboard guardado en: {out.resolve()}")
    return out