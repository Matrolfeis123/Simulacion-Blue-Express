# 2. Recursos del simulador

## 2.1 Bot Pool

- Número finito de bots
- Atiende RackMissions

---

## 2.2 OS Queue (Consolidation Queue)

- OS esperando ser agrupadas

---

## 2.3 Rack Preparation Queue

- Racks definidos pero no preparados

---

## 2.4 Reception Operator Pool

- n_receiving_operators
- Procesa racks → ready

---

## 2.5 Ready Rack Buffer

- Racks listos para retiro por bots
- Desacopla recepción y transporte

---

## 2.6 Empty Rack Buffer

- Racks vacíos disponibles
- Se reponen cuando bots retornan

---

## 2.7 Exit Resources

- Un recurso por salida
- Cada salida tiene su propia cola
