# 3. Flujo de eventos

## 3.1 Llegada de OS

- Se crea OS
- Se envía a cola de consolidación

---

## 3.2 Consolidación

- Se agrupan OS en racks
- Se crea RackMission
- Pasa a cola de preparación

---

## 3.3 Preparación en recepción (inicio)

- Operador toma rack
- Inicia preparación

---

## 3.4 Preparación en recepción (fin)

- Rack queda listo
- Entra a ready buffer

---

## 3.5 Bot busca rack

- Si hay rack → lo toma
- Si no → espera

---

## 3.6 Inicio de misión

- Bot toma rack
- Inicia recorrido

---

## 3.7 Llegada a salida

- Bot solicita servicio
- Puede esperar en cola

---

## 3.8 Liberación en salida

- Se procesan OS
- Bot queda libre para siguiente stop

---

## 3.9 Retorno

- Bot vuelve a recepción
- Deja rack vacío

---

## 3.10 Fin de misión

- Se registran KPIs
