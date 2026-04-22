from __future__ import annotations

from pprint import pprint

import pandas as pd

from config import build_peak_config
from inputs import InputModel
from simulation import build_and_run_simulation


def build_example_input_model():
    """
    Caso base mínimo para probar el simulador.

    Luego esto se reemplaza por lectura desde Excel / CSV.
    """
    config = build_peak_config()

    # -----------------------------
    # Demanda
    # -----------------------------
    os_per_hour = 693.0

    segment_distribution = {
        "Regular": 0.336,
        "Medium": 0.158,
        "Big": 0.192,
        "SuperBig": 0.315,
    }

    # 32 salidas
    exit_distribution = {f"EXIT_{i}": 1 / 32 for i in range(1, 33)}

    exit_distribution = {"EXIT_1":0.01917, "EXIT_2":0.00816, "EXIT_3":0.01065, 
                         "EXIT_4":0.00745, "EXIT_5":0.01775, "EXIT_6":0.00639, 
                         "EXIT_7":0.00568, "EXIT_8":0.00532, "EXIT_9": 0.00355,
                         "EXIT_10": 0.01207, "EXIT_11": 0.01278, "EXIT_12": 0.02840, 
                         "EXIT_13": 0.02378, "EXIT_14": 0.01704, "EXIT_15": 0.02662,
                         "EXIT_16": 0.01171, "EXIT_17": 0.01136, "EXIT_18": 0.01881,
                         "EXIT_19": 0.00674, "EXIT_20": 0.02201, "EXIT_21": 0.04650,
                         "EXIT_22": 0.06248, "EXIT_23": 0.00923, "EXIT_24": 0.07916, 
                         "EXIT_25": 0.05112, "EXIT_26": 0.07242, "EXIT_27": 0.08626,
                         "EXIT_28": 0.11147, "EXIT_29": 0.08626, "EXIT_30": 0.03905,
                         "EXIT_31": 0.06212, "EXIT_32": 0.01846
                         }

    destination_to_exit = {
        # SCL / RM
        "SCL 103": "EXIT_1",
        "SCL 104": "EXIT_1",
        "SCL 105": "EXIT_1",

        "PUDAHUEL 175": "EXIT_2",
        "PUDAHUEL 172": "EXIT_2",
        "PUDAHUEL 171": "EXIT_2",

        "COLINA": "EXIT_3",
        "LA PINTANA": "EXIT_3",
        "TIL TIL": "EXIT_4",
        "PEÑAFLOR": "EXIT_4",
        "CALERA DE TANGO": "EXIT_4",

        "BUIN": "EXIT_5",
        "PAINE": "EXIT_5",
        "LAMPA": "EXIT_5",

        "PIRQUE": "EXIT_6",
        "SAN JOSE DE MAIPO": "EXIT_6",
        "PADRE HURTADO": "EXIT_6",

        "LA GRANJA": "EXIT_7",
        "LA CISTERNA": "EXIT_7",
        "ISLA DE MAIPO": "EXIT_7",

        "CERRILLOS": "EXIT_8",
        "SAN RAMON": "EXIT_8",
        "EL BOSQUE": "EXIT_8",

        "LO PRADO": "EXIT_9",
        "PEDRO AGUIRRE CERDA": "EXIT_9",
        "LO ESPEJO": "EXIT_9",

        "SAN JOAQUIN": "EXIT_10",
        "INDEPENDENCIA": "EXIT_10",
        "HUECHURABA": "EXIT_10",

        "CERRO NAVIA": "EXIT_11",
        "QUINTA NORMAL": "EXIT_11",
        "ESTACION CENTRAL": "EXIT_11",

        "MAIPU": "EXIT_12",
        "QUILICURA": "EXIT_12",
        "RENCA": "EXIT_12",

        "RECOLETA": "EXIT_13",
        "PUENTE ALTO": "EXIT_13",

        "LO BARNECHEA": "EXIT_14",
        "VITACURA": "EXIT_14",
        "LA REINA": "EXIT_14",

        "SAN BERNARDO": "EXIT_15",
        "LA FLORIDA": "EXIT_15",

        "PEÑALOLEN": "EXIT_16",
        "PROVIDENCIA": "EXIT_16",

        "MACUL": "EXIT_17",
        "ÑUÑOA": "EXIT_17",

        "LAS CONDES 204": "EXIT_18",
        "LAS CONDES 205": "EXIT_18",
        "LAS CONDES 206": "EXIT_18",

        "SAN MIGUEL": "EXIT_19",
        "CONCHALI": "EXIT_19",

        # REGIONAL
        "ARICA": "EXIT_20",
        "IQUIQUE": "EXIT_20",

        "ANTOFAGASTA": "EXIT_21",
        "CALAMA": "EXIT_21",

        "COPIAPO": "EXIT_22",
        "LA SERENA": "EXIT_22",

        "OVALLE": "EXIT_23",
        "VALPARAISO": "EXIT_23",

        "QUILPUE": "EXIT_24",
        "VIÑA DEL MAR": "EXIT_24",

        "LA CALERA": "EXIT_25",
        "LOS ANDES": "EXIT_25",

        "MELIPILLA": "EXIT_26",
        "RANCAGUA": "EXIT_26",

        "CURICO": "EXIT_27",
        "TALCA": "EXIT_27",

        "CHILLAN": "EXIT_28",
        "CONCEPCION": "EXIT_28",

        "LOS ANGELES": "EXIT_29",
        "TEMUCO": "EXIT_29",

        "VALDIVIA": "EXIT_30",
        "OSORNO": "EXIT_30",

        "PUERTO MONTT": "EXIT_31",
        "CASTRO": "EXIT_31",

        "COYHAIQUE": "EXIT_32",
        "PUNTA ARENAS": "EXIT_32",
    }

    # -----------------------------
    # Tiempos de viaje (ejemplo simple)
    # TODO: reemplazar con tu parametrización real
    # -----------------------------
    travel_times_receiving_to_exit = {
        f"EXIT_{i}": 30.0 + (i * 12.0) for i in range(1, 33)
    }

    travel_times_exit_to_return = {
        f"EXIT_{i}": 28.0 + (i * 1.5) for i in range(1, 33)
    }

    travel_times_between_exits = {}
    for i in range(1, 33):
        for j in range(1, 33):
            if i == j:
                travel_times_between_exits[(f"EXIT_{i}", f"EXIT_{j}")] = 0.0
            else:
                travel_times_between_exits[(f"EXIT_{i}", f"EXIT_{j}")] = abs(j - i) * 5.0 + 8.0

    # -----------------------------
    # Tiempos de preparación de rack
    # TODO: reemplazar con tu lógica real
    # -----------------------------
    rack_prep_time_by_n_os = {
        1: 8.0,
        2: 12.0,
        3: 16.0,
        4: 20.0,
        5: 24.0,
    }

    # -----------------------------
    # Tiempos de release por stop
    # -----------------------------
    max_os_per_stop = max(rack_prep_time_by_n_os)
    release_base_time_s = config.turn_time_s
    release_time_per_os_s = config.pallet_load_unload_time_s / max_os_per_stop
    release_time_by_n_os_stop = {
        n_os_stop: release_base_time_s + (n_os_stop * release_time_per_os_s)
        for n_os_stop in range(1, max_os_per_stop + 1)
    }

    input_model = InputModel(
        config=config,
        os_per_hour=os_per_hour,
        segment_distribution=segment_distribution,
        exit_distribution=exit_distribution,
        destination_to_exit=destination_to_exit,
        travel_times_receiving_to_exit=travel_times_receiving_to_exit,
        travel_times_exit_to_return=travel_times_exit_to_return,
        travel_times_between_exits=travel_times_between_exits,
        rack_prep_time_by_n_os=rack_prep_time_by_n_os,
        release_time_by_n_os_stop=release_time_by_n_os_stop,
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
    config, input_model = build_example_input_model()

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
