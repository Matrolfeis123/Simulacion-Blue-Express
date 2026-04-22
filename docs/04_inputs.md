# 4. Inputs del simulador

## 4.1 Demanda

- simulation_mode (hourly / historical)
- os_per_hour
- distribution by exit
- distribution by segment

---

## 4.2 Consolidación

- max_os_regular_medium = 5
- max_os_big = 2
- max_os_superbig = 1

---

## 4.3 Bots

- n_bots
- effective_speed
- turn_time
- load/unload time

---

## 4.4 Recepción

- n_receiving_operators
- prep_time(n_os)

---

## 4.5 Salidas

- release_time(n_os)
- queue_capacity

---

## 4.6 Distancias

- receiving_to_exit[k]
- exit_to_exit[i,j]
- exit_to_return[k]
- turns

---

## 4.7 Estructura

- number of exits
- rack inventory
- buffer capacities

---

## 4.8 Simulación

- simulation_horizon
- warmup_time
- replications
- seed
