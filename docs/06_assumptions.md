# 6. Supuestos V1 vs V2

## 6.1 V1

### Demanda

- llegada agregada o histórica

### Consolidación

- reglas simples por segmento

### Layout

- no espacial
- basado en distancias

### Bots

- sin conflictos entre bots

### Recepción

- pool de operadores

### Salidas

- 1 salida = 1 recurso
- cola explícita

---

## 6.2 V2

### Layout

- red espacial
- congestión real

### Salidas

- operadores por bloque
- FIFO físico

### Bots

- tráfico y conflictos

### Recepción

- mayor detalle físico

---

## 6.3 Escalabilidad

El diseño debe permitir:

- cambiar distancias → rutas
- salida → bloque
- tiempos agregados → distribuciones
