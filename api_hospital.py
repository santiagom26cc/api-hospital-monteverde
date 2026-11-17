#!/usr/bin/env python3
"""API simulada del Hospital Monteverde (ficticio): órdenes de mantenimiento y equipos biomédicos.

Imita la API de datos.gov.co (Socrata), así que funciona con el mismo extraer.py del curso.
Todo es ficticio: hospital, marcas, proveedores, técnicos y pacientes.

Arrancar (en Cloud Shell, desde cualquier carpeta):
    python3 ~/api-hospital/api_hospital.py &

Conjuntos:
    http://localhost:8080/resource/ordenes.json
    http://localhost:8080/resource/equipos.json

Cómo se comporta:
  - Los datos crecen: cada día a las 00:00 (hora de Colombia) publica lo registrado el día anterior.
  - Máximo 1.000 filas por petición ($limit); para traer más, se pide por páginas con $offset.
  - Todos los valores llegan como texto y los campos vacíos no aparecen en la fila.
  - Parámetros: $select, $where, $order, $limit, $offset y filtros campo=valor.

Variables opcionales al arrancar:
    API_PUERTO=8081          otro puerto si el 8080 está ocupado
    API_FECHA_CORTE=2026-12-01   simula que hoy es esa fecha (para ensayar sin esperar)
    API_CAOS=1               responde a veces 429 y 503, como una API real con carga
    API_LOG=1                muestra cada petición en la terminal

Solo usa la biblioteca estándar de Python: no hay nada que instalar.
"""
import datetime as dt
import gzip
import json
import os
import pathlib
import random
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = pathlib.Path(__file__).resolve().parent
COLOMBIA = dt.timezone(dt.timedelta(hours=-5))
MAX_LIMIT = 1000
PUERTO = int(os.environ.get("API_PUERTO", "8080") or 8080)
HOST = os.environ.get("API_HOST", "127.0.0.1")
CAOS = os.environ.get("API_CAOS", "").strip() not in ("", "0")
LOG = os.environ.get("API_LOG", "").strip() not in ("", "0")
SISTEMA = [":id", ":created_at", ":updated_at"]

ARCHIVO = next((p for p in (AQUI / "hospital.json.gz", AQUI / "datos" / "hospital.json.gz") if p.exists()), None)
if ARCHIVO is None:
    sys.exit(f"No encuentro hospital.json.gz en {AQUI}. Actualiza la API: cd ~/api-hospital && git pull")
with gzip.open(ARCHIVO, "rt", encoding="utf-8") as _f:
    DATOS = json.load(_f)
_cache = {}


def hoy():
    f = os.environ.get("API_FECHA_CORTE", "").strip()
    if f:
        return dt.date.fromisoformat(f)
    return dt.datetime.now(COLOMBIA).date()


def filas(conjunto, corte):
    """Las filas tal como se ven en la fecha de corte: solo lo ya publicado."""
    clave = (conjunto, corte)
    if clave in _cache:
        return _cache[clave]
    c = DATOS["conjuntos"][conjunto]
    lim = corte.isoformat()
    out = []
    for r in c["filas"]:
        campos, primera, ultima = {}, None, None
        for d, u in r["u"]:
            if d <= lim:
                campos.update(u)
                primera = primera or d
                ultima = d
        if primera is None:
            continue
        fila = {":id": r[":id"], ":created_at": primera + "T05:00:00.000Z", ":updated_at": ultima + "T05:00:00.000Z"}
        for k in c["campos"]:
            if campos.get(k) is not None:
                fila[k] = campos[k]
        out.append(fila)
    _cache[clave] = out
    return out


class ErrorSoQL(Exception):
    pass


# ------------------------------------------------------------ $where sencillo: campo op valor, con AND / OR
TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<op><>|!=|>=|<=|=|>|<)|"
                   r"(?P<par>[()])|(?P<id>:?[A-Za-z_][A-Za-z0-9_]*))", re.S)


def tokens(texto):
    pos, out = 0, []
    texto = texto.strip()
    while pos < len(texto):
        m = TOKEN.match(texto, pos)
        if not m or m.end() == pos:
            raise ErrorSoQL(f"No entiendo el $where cerca de: {texto[pos:pos + 20]!r}")
        pos = m.end()
        tipo = m.lastgroup
        val = m.group(tipo)
        if tipo == "str":
            val = val[1:-1].replace("''", "'")
        out.append((tipo, val))
    return out


def compilar_where(texto, columnas):
    tk = tokens(texto)
    i = 0

    def ver():
        return tk[i] if i < len(tk) else (None, None)

    def tomar():
        nonlocal i
        t = ver()
        i += 1
        return t

    def palabra(p):
        t = ver()
        return t[0] == "id" and t[1].upper() == p

    def expr_or():
        izq = expr_and()
        while palabra("OR"):
            tomar()
            der = expr_and()
            izq = (lambda a, b: lambda f: a(f) or b(f))(izq, der)
        return izq

    def expr_and():
        izq = cond()
        while palabra("AND"):
            tomar()
            der = cond()
            izq = (lambda a, b: lambda f: a(f) and b(f))(izq, der)
        return izq

    def cond():
        t = tomar()
        if t == ("par", "("):
            e = expr_or()
            if tomar() != ("par", ")"):
                raise ErrorSoQL("Falta cerrar un paréntesis en el $where")
            return e
        if t[0] != "id":
            raise ErrorSoQL("El $where debe empezar con el nombre de un campo")
        campo = t[1]
        if campo not in columnas:
            raise ErrorSoQL(f"No existe el campo: {campo}")
        if palabra("IS"):
            tomar()
            neg = False
            if palabra("NOT"):
                tomar()
                neg = True
            if not palabra("NULL"):
                raise ErrorSoQL("Después de IS va NULL o NOT NULL")
            tomar()
            return (lambda c, n: lambda f: (f.get(c) is not None) if n else (f.get(c) is None))(campo, neg)
        op = tomar()
        if op[0] != "op":
            raise ErrorSoQL(f"Falta un operador después de {campo}")
        v = tomar()
        if v[0] not in ("str", "num"):
            raise ErrorSoQL("Los valores del $where van entre comillas simples: campo = 'valor'")
        valor = v[1]
        ops = {"=": lambda a, b: a == b, "!=": lambda a, b: a != b, "<>": lambda a, b: a != b,
               ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}
        fn = ops[op[1]]
        # Todos los campos son texto: la comparación es de texto, como en la fuente original.
        return (lambda c, f_, b: lambda f: f.get(c) is not None and f_(f[c], b))(campo, fn, valor)

    if not tk:
        return lambda f: True
    e = expr_or()
    if i != len(tk):
        raise ErrorSoQL(f"Sobra texto en el $where: {' '.join(str(x[1]) for x in tk[i:])}")
    return e


def consultar(conjunto, params):
    corte = hoy()
    datos = filas(conjunto, corte)
    columnas = SISTEMA + DATOS["conjuntos"][conjunto]["campos"]
    especiales = {}
    filtros = []
    for k, v in params:
        if k.startswith("$$"):
            continue                      # $$app_token y similares: se ignoran
        if k.startswith("$"):
            if k not in ("$select", "$where", "$order", "$limit", "$offset"):
                raise ErrorSoQL(f"Parámetro no reconocido: {k}")
            especiales[k] = v
        else:
            if k not in columnas:
                raise ErrorSoQL(f"No existe el campo: {k}")
            filtros.append((k, v))
    res = [f for f in datos if all(f.get(k) == v for k, v in filtros)]
    if "$where" in especiales:
        w = compilar_where(especiales["$where"], columnas)
        res = [f for f in res if w(f)]

    sel = especiales.get("$select", "").strip()
    if re.fullmatch(r"count\(\s*\*\s*\)", sel, re.I):
        return [{"count": str(len(res))}]

    orden = especiales.get("$order", ":id").strip() or ":id"
    for parte in reversed([p.strip() for p in orden.split(",") if p.strip()]):
        m = re.fullmatch(r"(:?[A-Za-z_][A-Za-z0-9_]*)(?:\s+(ASC|DESC))?", parte, re.I)
        if not m or m.group(1) not in columnas:
            raise ErrorSoQL(f"No puedo ordenar por: {parte}")
        campo, desc = m.group(1), (m.group(2) or "").upper() == "DESC"
        con = [f for f in res if f.get(campo) is not None]
        sin = [f for f in res if f.get(campo) is None]
        con.sort(key=lambda f: f[campo], reverse=desc)
        res = con + sin if not desc else sin + con

    try:
        limite = min(int(especiales.get("$limit", MAX_LIMIT)), MAX_LIMIT)
        desde = int(especiales.get("$offset", 0))
    except ValueError:
        raise ErrorSoQL("$limit y $offset deben ser números enteros")
    if limite < 0 or desde < 0:
        raise ErrorSoQL("$limit y $offset no pueden ser negativos")
    res = res[desde:desde + limite]

    if sel and sel not in ("*", ":*,*", ":*, *"):
        pedidos = [s.strip() for s in sel.split(",") if s.strip()]
        for s in pedidos:
            if s not in columnas:
                raise ErrorSoQL(f"No existe el campo: {s}")
        return [{k: f[k] for k in pedidos if k in f} for f in res]
    if sel in (":*,*", ":*, *"):
        return res
    return [{k: v for k, v in f.items() if not k.startswith(":")} for f in res]


class Manejador(BaseHTTPRequestHandler):
    server_version = "HospitalMonteverdeAPI/1.0"

    def log_message(self, formato, *args):
        if LOG:
            sys.stderr.write("  [api] " + (formato % args) + "\n")

    def responder(self, codigo, cuerpo, extra=None):
        datos = json.dumps(cuerpo, ensure_ascii=False, indent=None if isinstance(cuerpo, list) else 2).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Datos-Hasta", (hoy() - dt.timedelta(days=1)).isoformat())
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        ruta = u.path.rstrip("/") or "/"
        if ruta == "/":
            corte = hoy()
            base = f"http://localhost:{PUERTO}/resource"
            return self.responder(200, {
                "api": DATOS["nombre"],
                "datos_hasta": (corte - dt.timedelta(days=1)).isoformat(),
                "como_se_actualiza": "Cada día a las 00:00 (hora de Colombia) publica lo registrado el día anterior",
                "conjuntos": {n: {"url": f"{base}/{n}.json", "filas_hoy": len(filas(n, corte))}
                              for n in DATOS["conjuntos"]},
                "maximo_por_peticion": MAX_LIMIT,
                "aviso": "Datos sintéticos de un hospital ficticio, para aprender. No hay pacientes ni hospitales reales."})
        m = re.fullmatch(r"/resource/([a-z_]+)\.json", ruta)
        if not m or m.group(1) not in DATOS["conjuntos"]:
            return self.responder(404, {"error": True, "code": "dataset.missing",
                                        "message": f"No existe el conjunto {ruta}. Usa /resource/ordenes.json o /resource/equipos.json"})
        if CAOS:
            x = random.random()
            if x < 0.06:
                return self.responder(429, {"error": True, "message": "Demasiadas solicitudes: espera y reintenta"},
                                      {"Retry-After": "2"})
            if x < 0.12:
                return self.responder(503, {"error": True, "message": "Servicio no disponible por el momento"})
        try:
            params = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
            return self.responder(200, consultar(m.group(1), params))
        except ErrorSoQL as e:
            return self.responder(400, {"error": True, "code": "query.soql.invalid", "message": str(e)})


def main():
    try:
        srv = ThreadingHTTPServer((HOST, PUERTO), Manejador)
    except OSError:
        sys.exit(f"El puerto {PUERTO} está ocupado. ¿La API ya está corriendo? Pruébala con: curl -s localhost:{PUERTO}/\n"
                 f"Si es otro programa, arráncala en otro puerto: API_PUERTO=8081 python3 {sys.argv[0]} &")
    corte = hoy()
    print(f"API simulada del Hospital Monteverde (ficticio) en http://localhost:{PUERTO}")
    print(f"Datos publicados hasta el {(corte - dt.timedelta(days=1)).isoformat()}"
          + (" (fecha simulada con API_FECHA_CORTE)" if os.environ.get("API_FECHA_CORTE") else ""))
    for n in DATOS["conjuntos"]:
        print(f"  {n}: http://localhost:{PUERTO}/resource/{n}.json  ({len(filas(n, corte)):,} filas)".replace(",", "."))
    if CAOS:
        print("Modo caos activo: a veces responde 429 o 503.")
    print("Queda corriendo mientras Cloud Shell esté abierto (se apaga solo tras 40 min sin uso). "
          "Para detenerla: kill %1", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
