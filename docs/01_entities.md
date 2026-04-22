# 1. Entidades del simulador

## 1.1 OS (Order)

Representa una orden individual que entra al sistema.

### Atributos

- os_id
- arrival_time
- segment (Regular, Medium, Big, SuperBig)
- destination_id
- exit_id
- zone (SCL / REG)
- status (waiting_consolidation, assigned_to_rack, processed)

### Rol

- Alimenta el sistema
- Se agrupa en racks
- No se mueve directamente en la simulación

---

## 1.2 RackMission

Entidad principal de la simulación. Representa un rack consolidado que será transportado por un bot.

### Atributos

- rack_id
- creation_time
- ready_time
- pickup_time
- return_time
- os_list
- n_os
- segment_mix
- exit_sequence
- n_stops
- travel_distance_total
- travel_time_total
- release_time_total
- queue_time_total
- cycle_time_total
- status (building, waiting_preparation, ready, assigned, in_trip, completed)

### Rol

- Unidad operacional
- Viaja desde recepción → salidas → retorno

---

## 1.3 Bot

Representa un bot disponible.

### Atributos

- bot_id
- status (idle, waiting_rack, traveling, waiting_exit, returning)
- current_location
- current_rack_id
- total_busy_time
- total_idle_time
- trip_count

### Rol

- Ejecuta RackMissions

---

## 1.4 ExitServer

Recurso de servicio en cada salida.

### Atributos

- exit_id
- zone
- queue_capacity
- current_queue_length
- busy_time
- served_stops
- max_queue_observed

### Rol

- Atiende bots en salidas

---

## 1.5 ReceptionServer

Recurso de operadores de recepción.

### Atributos

- server_id
- busy_time
- served_racks
- status

### Rol

- Prepara racks antes de ser retirados por bots
