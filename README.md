# API simulada · Hospital Monteverde (ficticio)

Fuente de datos del equipo E3 · Análisis de Datos Intermedio · Estud-IA (Capa 2).

Órdenes de mantenimiento e inventario de equipos biomédicos de un hospital que **no existe**. Los datos son sintéticos: el hospital, las marcas, los proveedores, los técnicos y los pacientes son inventados. Sirven para aprender; no acreditan nada sobre un hospital real.

## Arrancarla en Cloud Shell

```bash
cd ~
git clone https://github.com/santiagom26cc/api-hospital-monteverde.git api-hospital
python3 ~/api-hospital/api_hospital.py &
curl -s localhost:8080/
```

Queda corriendo mientras la terminal esté abierta. Si cierras Cloud Shell, vuelve a correr solo la línea de `python3`.

## Cuidados con Cloud Shell

- **No hace falta dejarla prendida.** Los datos crecen según la fecha del día en que consultas, no según el tiempo que la API lleve corriendo. Arráncala para extraer y listo.
- **Cloud Shell se apaga solo:** después de 40 minutos sin uso y, como máximo, a las 12 horas. Si `extraer.py` dice «sin respuesta» o `Connection refused`, vuelve a arrancar la API. Lo que está en tu carpeta personal (`~/api-hospital`, tu repositorio, `data/raw`) no se borra.
- **Cuota de 50 horas por semana y por cuenta.** Cierra la pestaña de Cloud Shell cuando termines.
- **Si no entras en 120 días,** Google borra tu carpeta personal de Cloud Shell. Lo importante va en tu repositorio.

(Límites de Cloud Shell según la documentación de Google, consultada el 17 de noviembre de 2026.)

## Conjuntos

| Conjunto | Dirección |
|---|---|
| Órdenes de mantenimiento | `http://localhost:8080/resource/ordenes.json` |
| Inventario de equipos | `http://localhost:8080/resource/equipos.json` |

Se consulta igual que datos.gov.co: `$select`, `$where`, `$order`, `$limit`, `$offset` y filtros `campo=valor`. Funciona con el `extraer.py` del curso.

- Los datos crecen: cada día a las 00:00 (hora de Colombia) se publica lo registrado el día anterior.
- Máximo 1.000 filas por petición.
- Todos los valores llegan como texto y los campos vacíos no aparecen en la fila.
- No pide clave.

## Variables opcionales al arrancar

| Variable | Para qué |
|---|---|
| `API_PUERTO=8081` | Otro puerto si el 8080 está ocupado |
| `API_FECHA_CORTE=2026-12-01` | Simula que hoy es esa fecha |
| `API_CAOS=1` | Responde a veces 429 y 503, como una API con carga |
| `API_LOG=1` | Muestra cada petición en la terminal |

La carpeta `datos/` es el «sistema del hospital»: tu fuente es la API, no ese archivo.

Solo usa la biblioteca estándar de Python: no hay nada que instalar.
