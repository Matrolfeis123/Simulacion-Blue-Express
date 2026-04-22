📦 Backlog Técnico — Simulación RIL-M BlueExpress
🧭 Objetivo

Adaptar la simulación DES desde un modelo dummy a un modelo alineado con la operación real definida en Excel, permitiendo validar capacidad, colas, utilización y dimensionamiento de bots.

🔴 BLOQUE 1 — Inputs reales (CRÍTICO)

1. Distribución por destino + mapping destino → salida

Prioridad: Alta
Descripción:
Reemplazar la generación de OS por salida dummy por:

distribución real por destino
mapping destination → exit

Entregable:

destination_distribution
destination_to_exit
modificación de sample_destination()

Estimación: 1.5 – 2 horas
Dependencias: ninguna

2. Distribución de segmentos por destino

Prioridad: Alta
Descripción:
Incorporar mix de:

Regular / Medium / Big / SuperBig
por cada destino.

Entregable:

estructura tipo:
segment_distribution_by_destination = {
"MAIPU": {"Regular": 0.5, ...}
}

Estimación: 2 – 3 horas
Dependencias: (1)

3. Tiempos y distancias reales por salida

Prioridad: Alta
Descripción:
Reemplazar tiempos dummy por:

Receiving → Exit
Exit → Exit
Exit → Return

Entregable:

matrices reales cargadas desde Excel

Estimación: 2 – 4 horas
(depende de limpieza de datos)

Dependencias: ninguna

🟠 BLOQUE 2 — Lógica operativa 4. Validación de movimiento de bots (CRÍTICO)

Prioridad: Alta
Descripción:
Verificar que el bot:

recorre correctamente la secuencia de exits
usa distancias correctas
respeta retorno
acumula tiempos correctamente

Entregable:

debug logs de viajes
validación manual contra Excel

Estimación: 2 – 3 horas
Dependencias: (3)

5. Reemplazo de tiempos de recepción

Prioridad: Media
Descripción:
Actualizar tiempos de preparación de racks según número de OS.

Estimación: 1 – 2 horas
Dependencias: ninguna

6. Reemplazo de tiempos de release en salida

Prioridad: Media
Descripción:
Incorporar tiempo de liberación del bot según número de OS en cada parada.

Estimación: 1 – 2 horas
Dependencias: ninguna

7. Validar lógica de consolidación de racks

Prioridad: Alta
Descripción:
Verificar:

combinaciones válidas (R/M hasta 5, Big 2, SB 1)
generación de stops
secuencia de salida

Estimación: 2 – 3 horas
Dependencias: (1), (2)

8. Inventario real de racks vacíos

Prioridad: Media
Descripción:
Definir y parametrizar stock real de racks.

Estimación: 0.5 – 1 hora
Dependencias: ninguna

🟡 BLOQUE 3 — Colas y capacidad 9. Capacidad de cola por salida

Prioridad: Alta
Descripción:
Definir:

tamaño de cola por salida
diferencias SCL vs Regional

Entregable:

límite de cola
lógica de espera / bloqueo

Estimación: 2 – 3 horas
Dependencias: (4)

10. Validación de colas

Prioridad: Alta
Descripción:
Verificar:

formación de colas
saturación de salidas
tiempos de espera

Estimación: 1 – 2 horas
Dependencias: (9)

🟢 BLOQUE 4 — KPIs y visualización 11. KPIs básicos

Prioridad: Alta
Descripción:

throughput logrado
utilización bots
utilización salidas
tamaño de colas
cycle time promedio

Estimación: 2 – 3 horas
Dependencias: core funcional

12. Visualización gráfica

Prioridad: Media
Descripción:
Construir gráficos:

throughput vs objetivo
colas por salida
utilización
racks en recepción
distribución de stops

Tecnología sugerida:

matplotlib o plotly

Estimación: 3 – 5 horas
Dependencias: (11)

13. Validación contra Excel

Prioridad: Alta
Descripción:
Comparar:

OS/h
trips/h
mix de stops
cycle time

Estimación: 2 – 3 horas
Dependencias: (11)

🔵 BLOQUE 5 — Escalabilidad 14. Perfil horario (multi-hour simulation)

Prioridad: Media
Descripción:
Pasar de tasa fija a:

tasa por hora
o
input por timestamp

Estimación: 3 – 5 horas

15. Integración de logs reales

Prioridad: Media
Descripción:
Leer:

timestamp
destino
segmento

Estimación: 4 – 6 horas

16. Arquitectura para bloques / layout físico

Prioridad: Baja (por ahora)
Descripción:
Preparar transición:

salida → bloque
abstracción → layout

Estimación: 4 – 6 horas

⏱️ Estimación global
Bloque Tiempo
Inputs reales 6 – 9 h
Lógica operativa 6 – 9 h
Colas 3 – 5 h
KPIs + visualización 5 – 8 h
Escalabilidad 10 – 15 h

👉 Total completo: 30 – 45 horas

⚡ ¿Qué puedes lograr HOY?

Si hoy tienes, por ejemplo, 4–6 horas, mi recomendación óptima es:

🎯 Objetivo del día: primer modelo “realista”
Haz SOLO esto:
✅ Distribución por destino + mapping
✅ Tiempos reales por salida
✅ Validación básica del movimiento de bots

Tiempo estimado: 4–6 horas

Resultado que deberías obtener hoy

Si haces eso bien, ya podrás:

simular OS con destinos reales
tener tiempos de ciclo realistas
validar número de bots
comparar contra Excel
detectar desviaciones importantes

👉 Eso ya es suficiente para decir:
“la simulación replica el modelo analítico”
