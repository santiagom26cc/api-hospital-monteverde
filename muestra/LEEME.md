# Muestra de la API · Hospital Monteverde (ficticio)

Para mirar los datos antes de montar la API en Cloud Shell. Todo es sintético: el hospital, los equipos, los técnicos y los pacientes no existen.

| Archivo | Qué es |
|---|---|
| `ordenes_muestra.csv` | 25 órdenes de mantenimiento como tabla |
| `ordenes_muestra.json` | Las mismas 25, tal como las entrega la API |
| `equipos_muestra.csv` | 12 equipos del inventario como tabla |
| `equipos_muestra.json` | Los mismos 12, tal como los entrega la API |

**Cómo se sacó:** la API con datos publicados hasta el 16 de noviembre de 2026. Órdenes: las 20 primeras en el orden de la API (`$order=:id`) y las 5 actualizadas más recientemente (`$order=:updated_at DESC`). Equipos: los 12 primeros.

**Para qué sirve:** ver qué representa una fila, qué campo la identifica, qué campos faltan o llegan escritos distinto, y si con estas columnas se pueden calcular sus indicadores.

**Para qué no sirve:** para contar ni para calcular indicadores. Es una muestra pequeña. La fuente completa se trae con `extraer.py`.

La API también entrega `:id`, `:created_at` y `:updated_at` cuando se piden con `$select=:*,*`, como hace `extraer.py`. En la muestra no aparecen.
