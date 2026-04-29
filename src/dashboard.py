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
_SIM  = "#1D9E75"
_ANA  = "#E24B4A"
_NEU  = "#888780"
_TRAV = "#378ADD"
_WAIT = "#EF9F27"
_REL  = "#5DCAA5"
_IDLE = "#D3D1C7"


# ── Helpers ────────────────────────────────────────────────────────────────────
def _style_ax(ax: plt.Axes, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    ax.set_xlabel(xlabel, fontsize=8, labelpad=4)
    ax.set_ylabel(ylabel, fontsize=8, labelpad=4)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4, zorder=0)


def _vline(ax, x, label, color=_ANA):
    ax.axvline(x, color=color, linestyle="--", linewidth=1.3, label=label, zorder=5)


def _hline(ax, y, label, color=_ANA):
    ax.axhline(y, color=color, linestyle="--", linewidth=1.3, label=label, zorder=5)


def _no_data(ax):
    ax.text(0.5, 0.5, "Sin datos en ventana de medición",
            transform=ax.transAxes, ha="center", va="center", fontsize=9, color=_NEU)


# ── Panel 1: Throughput ────────────────────────────────────────────────────────
def _plot_throughput(ax, completed, warmup, horizon, targets):
    _style_ax(ax, "Throughput — OS completadas / hora",
              xlabel="Tiempo (s)", ylabel="OS / hora")
    if completed.empty:
        _no_data(ax); return

    window_s = 600.0
    times = np.arange(warmup + window_s, horizon + 1, 60.0)
    rolling = [
        completed.loc[
            (completed["time"] >= t - window_s) & (completed["time"] < t),
            "n_os"
        ].sum() / (window_s / 3600.0)
        for t in times
    ]
    ax.plot(times, rolling, color=_SIM, linewidth=1.5,
            label="Simulación (ventana 10 min)", zorder=3)

    avg_sim = completed["n_os"].sum() / ((horizon - warmup) / 3600.0)
    ax.axhline(avg_sim, color=_SIM, linestyle=":", linewidth=1.1,
               label=f"Promedio sim: {avg_sim:,.0f} OS/h", zorder=4)

    if "throughput_os_per_hour" in targets:
        t_val = targets["throughput_os_per_hour"]
        _hline(ax, t_val, f"Analítico: {t_val:,.0f} OS/h")
        gap = avg_sim - t_val
        sign = "+" if gap >= 0 else ""
        ax.text(0.98, 0.05, f"Δ = {sign}{gap:,.0f} OS/h",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
                color=_ANA if gap < 0 else _SIM)

    ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.set_xlim(warmup, horizon)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))


# ── Panel 2: Cycle time ────────────────────────────────────────────────────────
def _plot_cycle_time(ax, completed, targets):
    _style_ax(ax, "Cycle time por rack", xlabel="Segundos", ylabel="Frecuencia")
    if completed.empty:
        _no_data(ax); return

    ct = completed["cycle_time_total"].dropna()
    ax.hist(ct, bins=30, color=_SIM, alpha=0.75, edgecolor="white", linewidth=0.4, zorder=3)
    p50, p90, p95 = ct.quantile([0.50, 0.90, 0.95])
    _vline(ax, p50, f"p50: {p50:.0f}s", color=_SIM)
    _vline(ax, p90, f"p90: {p90:.0f}s", color=_NEU)
    _vline(ax, p95, f"p95: {p95:.0f}s", color=_NEU)
    if "cycle_time_s" in targets:
        _vline(ax, targets["cycle_time_s"], f"Analítico: {targets['cycle_time_s']:.0f}s")
    ax.legend(fontsize=7, frameon=False)


# ── Panel 3: Bot utilización ───────────────────────────────────────────────────
def _plot_bot_utilization(ax, audit, config, warmup, horizon, targets):
    effective = horizon - warmup
    total_bot_time = config.n_bots * effective

    trips = pd.DataFrame()
    if not audit.empty:
        trips = audit[(audit["event_type"] == "trip_completed") & (audit["time"] >= warmup)]

    if trips.empty:
        _style_ax(ax, "Utilización de bots (agregada)")
        _no_data(ax); return

    t_travel  = float(trips["travel_time_total"].sum())
    t_queue   = float(trips["queue_time_total"].sum())
    t_release = float(trips["release_time_total"].sum())
    t_busy    = t_travel + t_queue + t_release
    t_idle    = max(0.0, total_bot_time - t_busy)
    util_sim  = t_busy / total_bot_time * 100.0

    title = f"Utilización de bots — sim: {util_sim:.1f}%"
    if "bot_utilization" in targets:
        title += f"  ·  analítico: {targets['bot_utilization'] * 100:.1f}%"
    _style_ax(ax, title, ylabel="Tiempo total del pool (s)")

    bars = ax.barh(
        ["Viaje", "Release en salida", "Espera cola", "Idle"],
        [t_travel, t_release, t_queue, t_idle],
        color=[_TRAV, _REL, _WAIT, _IDLE],
        edgecolor="white", linewidth=0.5, zorder=3,
    )
    for bar, val in zip(bars, [t_travel, t_release, t_queue, t_idle]):
        pct = val / total_bot_time * 100.0
        ax.text(bar.get_width() + total_bot_time * 0.005,
                bar.get_y() + bar.get_height() / 2.0,
                f"{pct:.1f}%", va="center", fontsize=8)

    if "bot_utilization" in targets:
        ref_x = targets["bot_utilization"] * total_bot_time
        ax.axvline(ref_x, color=_ANA, linestyle="--", linewidth=1.3,
                   label=f"Analítico: {targets['bot_utilization']*100:.1f}%")
        ax.legend(fontsize=7, frameon=False)

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.4, zorder=0)
    ax.grid(axis="y", visible=False)


# ── Panel 4: Cola por salida ───────────────────────────────────────────────────
def _plot_queue_by_exit(ax, queue_ev, targets):
    _style_ax(ax, "Delay en cola — por salida", xlabel="Salida", ylabel="Delay (s)")
    if queue_ev.empty:
        _no_data(ax); return

    stats = (
        queue_ev.groupby("exit_id")["queue_delay_s"]
        .agg(mean="mean", p90=lambda x: x.quantile(0.90))
        .sort_values("mean", ascending=False)
    )
    x = np.arange(len(stats))
    ax.bar(x, stats["mean"], width=0.55, color=_SIM, alpha=0.85, label="Promedio", zorder=3)
    ax.bar(x, stats["p90"] - stats["mean"], width=0.55, bottom=stats["mean"],
           color=_WAIT, alpha=0.6, label="p90", zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels([e.replace("exit_", "S") for e in stats.index],
                       rotation=45, ha="right", fontsize=7)
    if "mean_queue_delay_s" in targets:
        _hline(ax, targets["mean_queue_delay_s"],
               f"Analítico: {targets['mean_queue_delay_s']:.1f}s")
    ax.legend(fontsize=7, frameon=False)


# ── Panel 5: Buffers ───────────────────────────────────────────────────────────
def _plot_buffers(ax, snapshots, warmup):
    _style_ax(ax, "Niveles de buffer en el tiempo", xlabel="Tiempo (s)", ylabel="Cantidad")
    if snapshots.empty:
        _no_data(ax); return

    s = snapshots[snapshots["time"] >= warmup]
    if s.empty:
        _no_data(ax); return

    ax.plot(s["time"], s["os_buffer_len"],     color=_TRAV, linewidth=1.2, label="OS en buffer")
    ax.plot(s["time"], s["pending_racks_len"], color=_WAIT, linewidth=1.2, label="Racks pendientes")
    ax.plot(s["time"], s["ready_racks_len"],   color=_SIM,  linewidth=1.2, label="Racks listos")
    ax.plot(s["time"], s["empty_racks_level"], color=_NEU,  linewidth=1.0,
            linestyle="--", label="Racks vacíos")
    ax.legend(fontsize=7, frameon=False, ncol=2)
    ax.set_xlim(s["time"].min(), s["time"].max())


# ── Panel 6: Distribución de stops ────────────────────────────────────────────
def _plot_stops_distribution(ax, completed):
    _style_ax(ax, "Distribución de stops por rack", xlabel="N° stops", ylabel="Frecuencia")
    if completed.empty:
        _no_data(ax); return

    counts = completed["n_stops"].value_counts().sort_index()
    ax.bar([str(v) for v in counts.index], counts.values,
           color=_SIM, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)
    mean_stops = completed["n_stops"].mean()
    pct_1stop  = (completed["n_stops"] == 1).mean() * 100
    ax.text(0.98, 0.95, f"Promedio: {mean_stops:.2f} stops/rack",
            transform=ax.transAxes, ha="right", va="top", fontsize=8)
    ax.text(0.98, 0.85, f"1 stop: {pct_1stop:.1f}% de racks",
            transform=ax.transAxes, ha="right", va="top", fontsize=8, color=_SIM)


# ── Panel 7a: Utilización de operadores ───────────────────────────────────────
def _plot_reception_utilization(ax, reception_ev, config, warmup):
    """Barra de utilización de operadores vs referencia de saturación."""
    _style_ax(ax, "Recepción — utilización de operadores",
              xlabel="", ylabel="Utilización (%)")

    if reception_ev.empty:
        _no_data(ax); return

    starts = reception_ev[reception_ev["event"] == "start"]
    ends   = reception_ev[reception_ev["event"] == "end"]

    prep_pairs = pd.merge(
        starts[["rack_id", "time"]].rename(columns={"time": "t_start"}),
        ends[["rack_id",   "time"]].rename(columns={"time": "t_end"}),
        on="rack_id",
    )
    total_prep_active = float((prep_pairs["t_end"] - prep_pairs["t_start"]).sum())
    total_op_time     = config.n_receiving_operators * config.effective_horizon
    util_pct          = total_prep_active / total_op_time * 100.0 if total_op_time > 0 else 0.0

    ax.bar(["Operadores"], [util_pct], color=_SIM, alpha=0.85,
           edgecolor="white", linewidth=0.5, width=0.35, zorder=3)
    ax.axhline(100, color=_ANA, linestyle="--", linewidth=1.2,
               label="Saturación (100%)", zorder=4)
    ax.set_ylim(0, 115)
    ax.text(0, util_pct + 3, f"{util_pct:.1f}%",
            ha="center", fontsize=11, fontweight="bold", color=_SIM)
    ax.legend(fontsize=7, frameon=False)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.4, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Diagnóstico textual
    if util_pct >= 90:
        msg = "⚠ Operadores saturados\n→ cuello de botella en recepción"
        color = _ANA
    elif util_pct >= 50:
        msg = "Operadores con carga moderada\n→ cuello puede estar upstream"
        color = _WAIT
    else:
        msg = "Operadores con carga baja\n→ cuello está upstream"
        color = _SIM
    ax.text(0.98, 0.95, msg, transform=ax.transAxes,
            ha="right", va="top", fontsize=8, color=color)


# ── Panel 7b: Espera pre-preparación ──────────────────────────────────────────
def _plot_reception_wait(ax, reception_ev, rack_creations, warmup):
    """Histograma del tiempo de espera desde creación del rack hasta inicio de preparación."""
    _style_ax(ax, "Recepción — espera en cola de preparación",
              xlabel="Tiempo de espera (s)", ylabel="Frecuencia")

    if reception_ev.empty or rack_creations.empty:
        _no_data(ax); return

    starts = reception_ev[reception_ev["event"] == "start"]
    wait_df = pd.merge(
        starts[["rack_id", "time"]].rename(columns={"time": "t_service_start"}),
        rack_creations[["rack_id", "time"]].rename(columns={"time": "t_created"}),
        on="rack_id",
    )
    wait_df["wait_s"] = (wait_df["t_service_start"] - wait_df["t_created"]).clip(lower=0)
    wait_s = wait_df["wait_s"]

    mean_wait = float(wait_s.mean())
    p90_wait  = float(wait_s.quantile(0.90))

    if wait_s.max() < 0.1:
        ax.text(0.5, 0.5,
                f"Espera ≈ 0s\nOperadores siempre disponibles\n(no hay cola de preparación)",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=9, color=_SIM,
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          edgecolor=_SIM, linewidth=0.8))
    else:
        ax.hist(wait_s, bins=30, color=_WAIT, alpha=0.8,
                edgecolor="white", linewidth=0.4, zorder=3)
        _vline(ax, mean_wait, f"Media: {mean_wait:.1f}s", color=_SIM)
        _vline(ax, p90_wait,  f"p90:   {p90_wait:.1f}s",  color=_ANA)
        ax.legend(fontsize=7, frameon=False)


# ── Entry point: dashboard de réplica única ────────────────────────────────────
def build_dashboard(
    dfs: Dict[str, pd.DataFrame],
    summary: Dict[str, Any],
    config: SimulationConfig,
    analytical_targets: Dict[str, float],
    output_path: str | Path = "simulation_dashboard.png",
) -> Path:
    """
    Dashboard de 8 paneles (4 × 2).

    [0,0] Throughput en el tiempo       [0,1] Cycle time (histograma)
    [1,0] Utilización de bots           [1,1] Delay en cola por salida
    [2,0] Niveles de buffer             [2,1] Distribución de stops
    [3,0] Util. operadores recepción    [3,1] Espera pre-preparación
    """
    warmup  = config.warmup_time
    horizon = config.simulation_horizon

    completed      = dfs.get("completed_racks",    pd.DataFrame())
    snapshots      = dfs.get("state_snapshots",     pd.DataFrame())
    queue_ev       = dfs.get("exit_queue_events",   pd.DataFrame())
    audit          = dfs.get("travel_audit_events", pd.DataFrame())
    reception_ev   = dfs.get("reception_events",    pd.DataFrame())
    rack_creations = dfs.get("rack_creations",      pd.DataFrame())

    # Filtro de warmup
    if not completed.empty and warmup > 0:
        completed = completed[completed["time"] >= warmup].copy()
    if not queue_ev.empty and warmup > 0:
        queue_ev = queue_ev[queue_ev["time"] >= warmup].copy()
    if not reception_ev.empty and warmup > 0:
        reception_ev = reception_ev[reception_ev["time"] >= warmup].copy()
    if not rack_creations.empty and warmup > 0:
        rack_creations = rack_creations[rack_creations["time"] >= warmup].copy()

    # Figura 4x2
    fig, axes = plt.subplots(4, 2, figsize=(14, 14))
    fig.patch.set_facecolor("white")

    warmup_label = f"warmup = {warmup:.0f}s" if warmup > 0 else "sin warmup"
    fig.suptitle(
        f"Simulación DES — BlueExpress RIL-M  ·  {config.n_bots} bots  ·  {warmup_label}",
        fontsize=12, fontweight="bold", y=0.999,
    )

    _plot_throughput(axes[0, 0], completed, warmup, horizon, analytical_targets)
    _plot_cycle_time(axes[0, 1], completed, analytical_targets)
    _plot_bot_utilization(axes[1, 0], audit, config, warmup, horizon, analytical_targets)
    _plot_queue_by_exit(axes[1, 1], queue_ev, analytical_targets)
    _plot_buffers(axes[2, 0], snapshots, warmup)
    _plot_stops_distribution(axes[2, 1], completed)
    _plot_reception_utilization(axes[3, 0], reception_ev, config, warmup)
    _plot_reception_wait(axes[3, 1], reception_ev, rack_creations, warmup)

    plt.tight_layout(rect=[0, 0, 1, 0.997])

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Dashboard guardado en: {out.resolve()}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard de réplicas
# ══════════════════════════════════════════════════════════════════════════════

def _plot_kpi_replicas(ax, summaries, key, title, ylabel,
                       analytic_value=None, is_pct=False):
    scale  = 100.0 if is_pct else 1.0
    values = [s[key] * scale for s in summaries if key in s]
    x      = list(range(1, len(values) + 1))

    if not values:
        _no_data(ax); return

    mean_v = sum(values) / len(values)
    var_v  = sum((v - mean_v) ** 2 for v in values) / max(len(values) - 1, 1)
    std_v  = var_v ** 0.5
    n      = len(values)
    t_table = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57,
               7: 2.45,  8: 2.36, 9: 2.31, 10: 2.26}
    tc  = t_table.get(n, 1.96)
    ci  = tc * std_v / (n ** 0.5)
    lo  = mean_v - ci
    hi  = mean_v + ci

    ax.scatter(x, values, color=_SIM, zorder=4, s=40, alpha=0.85)
    ax.axhline(mean_v, color=_SIM, linewidth=1.5, linestyle="-",
               label=f"Media: {mean_v:.1f}", zorder=3)
    ax.fill_between([0.5, n + 0.5], lo, hi,
                    color=_SIM, alpha=0.12, zorder=2, label=f"IC95%: ±{ci:.1f}")

    if analytic_value is not None:
        av = analytic_value * scale
        ax.axhline(av, color=_ANA, linewidth=1.3, linestyle="--",
                   label=f"Analítico: {av:.1f}", zorder=5)
        within = lo <= av <= hi
        tag = "✓ dentro IC95%" if within else "✗ fuera IC95%"
        ax.text(0.98, 0.05, tag, transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8,
                color=_SIM if within else _ANA)

    ax.set_xlim(0.3, n + 0.7)
    ax.set_xticks(x)
    ax.set_xticklabels([f"R{i}" for i in x], fontsize=7)
    _style_ax(ax, title, xlabel="Réplica", ylabel=ylabel)
    ax.text(0.98, 0.95,
            "Cada punto = una réplica\nMedia e IC95% con peso uniforme",
            transform=ax.transAxes, ha="right", va="top", fontsize=7,
            color=_NEU)
    ax.legend(fontsize=7, frameon=False, loc="upper left")


def _plot_throughput_convergence(ax, summaries, analytic_value=None):
    values = [s["throughput_os_per_hour"] for s in summaries
              if "throughput_os_per_hour" in s]
    n = len(values)
    if n == 0:
        _no_data(ax); return

    running_mean = [sum(values[:i + 1]) / (i + 1) for i in range(n)]
    t_table = {2: 12.71, 3: 4.30, 4: 3.18, 5: 2.78, 6: 2.57,
               7: 2.45, 8: 2.36, 9: 2.31, 10: 2.26}
    running_ci95 = []
    for i in range(n):
        k = i + 1
        if k < 2:
            running_ci95.append(0.0)
            continue
        mean_k = running_mean[i]
        std_k = (sum((v - mean_k) ** 2 for v in values[:k]) / (k - 1)) ** 0.5
        tcrit = t_table.get(k, 1.96)
        running_ci95.append(tcrit * std_k / (k ** 0.5))

    xs = list(range(1, n + 1))
    ax.plot(xs, running_mean, color=_SIM, linewidth=1.8,
            marker="o", markersize=5, label="Media acumulada", zorder=4)
    ax.fill_between(xs,
                    [running_mean[i] - running_ci95[i] for i in range(n)],
                    [running_mean[i] + running_ci95[i] for i in range(n)],
                    color=_SIM, alpha=0.12, label="IC95% de la media acumulada", zorder=2)

    if analytic_value is not None:
        ax.axhline(analytic_value, color=_ANA, linewidth=1.3, linestyle="--",
                   label=f"Analítico: {analytic_value:.0f} OS/h", zorder=5)

    _style_ax(ax, "Convergencia — media acumulada de throughput",
              xlabel="N réplicas", ylabel="OS / hora")
    ax.set_xticks(xs)
    if n >= 2:
        final_rhw = (running_ci95[-1] / abs(running_mean[-1]) * 100.0) if abs(running_mean[-1]) > 1e-12 else np.nan
        if pd.notna(final_rhw):
            ax.text(0.98, 0.05, f"RHW95 final: {final_rhw:.1f}%",
                    transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color=_NEU)
    ax.legend(fontsize=7, frameon=False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))


def _plot_summary_table(ax, agg, analytical_targets):
    ax.axis("off")
    N  = agg.get("n_replications", "?")
    tc = agg.get("t_critical_95", 1.96)

    lines = [
        f"Resumen — {N} réplicas  (t₉₅ = {tc:.2f})",
        "─" * 48,
    ]
    kpis = [
        ("throughput_os_per_hour",  "Throughput",        "throughput_os_per_hour", False),
        ("p50_cycle_time_s",        "Cycle time p50",    "cycle_time_s",           False),
        ("mean_cycle_time_s",       "Cycle time media",  None,                     False),
        ("bot_utilization",         "Bot utilización",   "bot_utilization",        True),
        ("bot_util_idle_frac",      "Bot idle",          None,                     True),
        ("mean_exit_queue_delay_s", "Queue delay",       "mean_queue_delay_s",     False),
    ]
    for key, label, tkey, is_pct in kpis:
        if key not in agg:
            continue
        m  = agg[key]
        ci = agg.get(f"{key}_ci95", 0.0)
        lo = agg.get(f"{key}_lo", m)
        hi = agg.get(f"{key}_hi", m)
        rhw = agg.get(f"{key}_rhw95", float("nan"))

        if is_pct:
            val_str = f"{m*100:.1f}% ± {ci*100:.1f}pp"
        else:
            unit = "s" if ("time" in key or "delay" in key) else " OS/h"
            val_str = f"{m:.1f}{unit} ± {ci:.1f}"

        if pd.notna(rhw):
            val_str += f"  [RHW95 {rhw:.1f}%]"

        if tkey and tkey in analytical_targets:
            tval   = analytical_targets[tkey]
            within = lo <= tval <= hi
            sym    = "✓" if within else "✗"
            tv_str = f"{tval*100:.1f}%" if is_pct else f"{tval:.0f}"
            vs     = f"  {sym} {tv_str}"
        else:
            vs = ""

        lines.append(f"  {label:<20} {val_str}{vs}")

    lines.extend([
        "",
        "Guía de precisión (RHW95):",
        "  <= 5%  buena precisión",
        "  5-10%  precisión moderada",
        "  > 10%  conviene más réplicas",
    ])

    ax.text(0.05, 0.95, "\n".join(lines),
            transform=ax.transAxes, va="top", ha="left", fontsize=9,
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="#cccccc", linewidth=0.8))


def build_replications_dashboard(
    summaries: list[dict],
    agg: dict,
    config: SimulationConfig,
    analytical_targets: dict,
    output_path: str | Path = "outputs/replications_dashboard.png",
) -> Path:
    """
    Dashboard de 6 paneles para análisis de réplicas.

    [0,0] Throughput por réplica + IC95%   [0,1] Cycle time p50 por réplica
    [1,0] Bot utilización por réplica      [1,1] Queue delay por réplica
    [2,0] Convergencia media throughput    [2,1] Tabla resumen estadístico
    """
    N = agg.get("n_replications", len(summaries))

    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.patch.set_facecolor("white")
    fig.suptitle(
        f"Análisis de réplicas — {N} réplicas  ·  {config.n_bots} bots  "
        f"·  warmup = {config.warmup_time:.0f}s",
        fontsize=12, fontweight="bold", y=0.999,
    )

    tp_target = analytical_targets.get("throughput_os_per_hour")
    ct_target = analytical_targets.get("cycle_time_s")
    bu_target = analytical_targets.get("bot_utilization")

    _plot_kpi_replicas(axes[0, 0], summaries,
                       "throughput_os_per_hour", "Throughput por réplica",
                       "OS / hora", analytic_value=tp_target)
    _plot_kpi_replicas(axes[0, 1], summaries,
                       "p50_cycle_time_s", "Cycle time p50 por réplica",
                       "Segundos", analytic_value=ct_target)
    _plot_kpi_replicas(axes[1, 0], summaries,
                       "bot_utilization", "Bot utilización por réplica",
                       "%", analytic_value=bu_target, is_pct=True)
    _plot_kpi_replicas(axes[1, 1], summaries,
                       "mean_exit_queue_delay_s", "Queue delay media por réplica",
                       "Segundos", analytic_value=analytical_targets.get("mean_queue_delay_s"))
    _plot_throughput_convergence(axes[2, 0], summaries, analytic_value=tp_target)
    _plot_summary_table(axes[2, 1], agg, analytical_targets)

    plt.tight_layout(rect=[0, 0, 1, 0.997])

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Dashboard de réplicas guardado en: {out.resolve()}")
    return out