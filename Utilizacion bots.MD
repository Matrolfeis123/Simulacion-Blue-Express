Excelente pregunta. Viendo el dashboard **antes de Iter 2**, puedo darte una respuesta basada en los números que estás observando. El 47% de idle **no es un problema**, es el resultado esperado de tu configuración actual. Te lo desgloso:

---

## Análisis de la utilización observada (53% busy / 47% idle)

### Cálculo de capacidad vs demanda

Del dashboard extraigo:

| Métrica observada     | Valor                                       |
| --------------------- | ------------------------------------------- |
| Throughput promedio   | 666 OS/h                                    |
| Cycle time p50        | 226 s                                       |
| Distribución de stops | 1 stop: 56.5%, 2 stops: ~22%, 3 stops: ~22% |
| N° de bots            | 47                                          |
| Utilización bots      | 53.0%                                       |

**Paso 1: Calcular capacidad teórica de la flota**

$$\text{Capacidad (trips/h)} = \frac{\text{N bots} \times 3600\text{ s/h}}{\text{cycle time promedio}}$$

$$\text{Capacidad} = \frac{47 \times 3600}{226} \approx 749 \text{ trips/h}$$

**Paso 2: Calcular demanda real (trips necesarios)**

Con throughput de 666 OS/h y un promedio de ~1.67 OS/rack (calculado del panel de stops):

$$\text{Trips necesarios} = \frac{666 \text{ OS/h}}{1.67 \text{ OS/trip}} \approx 399 \text{ trips/h}$$

**Paso 3: Utilización esperada**

$$\text{Utilización esperada} = \frac{399}{749} \approx 53.3\%$$

**Resultado: ¡Coincide exactamente con lo observado (53.0%)!**

---

## Por qué el idle es tan alto: tres causas combinadas

### 1. **Consolidación mejorada (Iter 1) redujo el número de trips**

Antes de Iter 1, con política greedy, cada bot llevaba ~1 OS por trip. Ahora llevan 1.67 OS/trip en promedio. Esto significa:

- **Antes**: 666 OS/h → 666 trips/h necesarios → util = 666/749 = **89%**
- **Ahora**: 666 OS/h → 399 trips/h necesarios → util = 399/749 = **53%**

El idle **subió porque la consolidación funciona**. Esto es bueno, no malo.

### 2. **Throughput real (666) vs objetivo (693): gap de 27 OS/h**

Hay una discrepancia pequeña. Causas probables:

- **Right-censoring** del horizonte (se corrige en Iter 2): algunos racks que empezaron tarde no se registran como completados.
- **Varianza Poisson**: en esta réplica particular llegaron un poco menos OS de las esperadas.
- **Desacople en recepción** (ver abajo): si los racks se preparan más lento de lo que los bots pueden retirarlos, se acumula WIP.

Con Iter 2 verás `arrival_rate` vs `departure_rate` y sabrás exactamente si el sistema procesa todo lo que llega.

### 3. **Flota sobredimensionada para la carga actual**

Con 47 bots y capacidad de ~749 trips/h, el sistema podría sostener:

$$\text{Capacidad máxima (OS/h)} = 749 \times 1.67 \approx 1251 \text{ OS/h}$$

Pero solo recibe 666 OS/h → estás usando **53% de tu capacidad instalada**. El resto es margen.

---

## El desacople visible: pending alto, ready bajo

Algo interesante que veo en el panel de buffers:

| Buffer                     | Nivel observado |
| -------------------------- | --------------- |
| **Racks pendientes**       | 20-45 (alto)    |
| **Racks listos**           | 0-5 (muy bajo)  |
| **Operadores utilización** | 12.6%           |

Esto sugiere un **cuello de botella leve en preparación**:

1. Los racks se crean rápido (consolidación eficiente → pending alto)
2. Los operadores los preparan más lento → ready bajo
3. Los bots esperan que haya racks listos → parte del idle

**¿Por qué los operadores tienen solo 12.6% de utilización si hay tanto trabajo pendiente?**

La métrica de utilización de operadores solo cuenta el tiempo **activamente preparando** (entre `record_reception_service_start` y `record_reception_service_end`). No cuenta:

- Tiempo esperando que llegue un rack a `pending_racks`
- Tiempo esperando un operador disponible
- Tiempo esperando un rack vacío de inventario

Con prep_time promedio de ~10s por rack y ~399 racks/h:

$$\text{Utilización esperada} = \frac{399 \times 10 / 3600}{7} \approx 15.8\%$$

El 12.6% observado está cerca. La diferencia puede deberse a que durante parte del tiempo no hay suficiente trabajo (OS buffer bajo, consolidación esperando threshold).

**Este desacople NO es crítico** porque:

- Los operadores tienen capacidad de sobra (12.6% util → 87.4% margen)
- El ready buffer oscila 0-5 pero no se vacía completamente (los bots no se quedan sin trabajo sostenidamente)
- El sistema está en equilibrio dinámico

---

## Entonces, ¿el 47% idle es un problema?

**No, es el resultado esperado de:**

1. **Consolidación eficiente**: menos trips por OS → menos utilización de bots
2. **Sobredimensionamiento**: 47 bots pueden manejar ~1251 OS/h, pero solo reciben 666 OS/h
3. **Carga sub-nominal**: si el objetivo es 693 OS/h pero llegan 666, estás ~4% por debajo

---

## ¿Qué validar con Iter 2?

Una vez implementes los cambios de métrica (Iter 2), busca estos KPIs:

```
arrival_rate_os_per_hour: ~693
departure_rate_os_per_hour: ~693
arrival_departure_gap_os_per_hour: ~0
wip_end_os: ~0
```

Si el gap es 0 y wip_end es 0, confirma que el sistema **procesa todo lo que llega**. En ese caso, el 47% idle simplemente significa que tienes margen para crecer.

Si el gap es significativo (digamos, 20-30 OS/h sostenido), entonces hay un cuello de botella oculto que habría que investigar.

---

## Diagnóstico final

| Pregunta                        | Respuesta                                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- |
| ¿Por qué 47% idle?              | Capacidad instalada (749 trips/h) > demanda (399 trips/h)                                                |
| ¿Es un problema?                | No, es margen de capacidad. El sistema puede crecer a 1251 OS/h.                                         |
| ¿Por qué throughput 666 vs 693? | Right-censoring (Iter 2) + varianza Poisson. Validar con `arrival_departure_gap`.                        |
| ¿Qué hacer?                     | Implementar Iter 2, validar que gap ≈ 0. Si es 0, considerar reducir flota a ~27-30 bots para util ~80%. |

El sistema está funcionando correctamente. El idle alto refleja dimensionamiento conservador, no ineficiencia.
