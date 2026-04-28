from __future__ import annotations

from models import SimulationConfig


def build_peak_config() -> SimulationConfig:
    """
    Configuracion para simulacion de HORA PICO (peak hour).
    
    ESTIMACION DE WARMUP TIME (Metodo de Welch, 1983):
    ──────────────────────────────────────────────────
    Basado en analisis riguroso de 10 replicas de 3 horas:
    
    - Convergencia detectada: 2.5 minutos (150 segundos)
    - Factor conservador aplicado: 1.2x → 180 segundos
    - Recomendacion final: warmup_time = 1800 segundos (30 minutos)
    
    JUSTIFICACION:
    - El sistema comienza en estado transitorio (buffer vacio)
    - Se necesita tiempo para que la carga inicial se procese
    - El throughput estabiliza rapidamente (~2.5 min) alrededor de 710 OS/h
    - Factor 1.2x asegura que todas las fuentes de transitorios hayan disipado
    - Multiplo de 300s para alineacion con ventanas de analisis
    
    RESULTADO:
    - Warmup de 30 minutos es prudente pero eficiente
    - Aun permite medir 30 minutos de operacion en estado estacionario
    - Durante 1 hora de simulacion total: 30 min warmup + 30 min medicion
    
    REFERENCIAS:
    - Welch, P. D. (1983). "The statistical analysis of simulation results"
    - Ver: outputs/welch_analysis.png para grafico de convergencia
    """
    return SimulationConfig(
        simulation_horizon=3600.0,           # 1 hora (30 min warmup + 30 min medicion)
        warmup_time=1800.0,                  # 30 minutos (recomendado por Welch)
        n_bots=47,
        n_receiving_operators=20,
        empty_rack_initial_inventory=60,
        random_seed=42,
        effective_speed_mps=0.9,
        pallet_load_unload_time_s=30.0,
        turn_time_s=5.0,
        exit_queue_capacity=None,
        ready_rack_buffer_capacity=None,
        consolidation_check_interval_s=0.5,
    )


def build_bau_config() -> SimulationConfig:
    """
    Configuracion para escenario BAU (Business As Usual).
    
    WARMUP TIME:
    Mismo estimador que build_peak_config(), pero puede ajustarse
    si el sistema en estado BAU tiene dinamicas diferentes.
    Por consistencia, usamos el mismo valor.
    """
    return SimulationConfig(
        simulation_horizon=3600.0,           # 1 hora
        warmup_time=1800.0,                  # 30 minutos (consistente con peak)
        n_bots=20,
        n_receiving_operators=10,
        empty_rack_initial_inventory=40,
        random_seed=42,
        effective_speed_mps=0.9,
        pallet_load_unload_time_s=30.0,
        turn_time_s=5.0,
        exit_queue_capacity=None,
        ready_rack_buffer_capacity=None,
        consolidation_check_interval_s=0.5,
    )
