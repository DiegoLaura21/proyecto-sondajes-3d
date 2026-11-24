"""Importación y geometría de un proyecto de sondajes en coordenadas E, N y cota."""

from array import array
from bisect import bisect_right
import csv
import io
import json
import math
import re
import struct
import sys
import unicodedata

from terreno_raster import cargar_asc, cargar_geotiff


ALIAS = {
    "id": ("holeid", "bhid", "drillholeid", "sondaje", "taladro", "id"),
    "x": ("east", "easting", "x", "este"),
    "y": ("north", "northing", "y", "norte"),
    "z": ("rl", "z", "elevation", "elev", "cota"),
    "eoh": ("eoh", "totaldepth", "depth", "profundidad", "length", "longitud"),
    "md": ("md", "depth", "profundidad", "at"),
    "az": ("azimuth", "azimut", "azi"),
    "dip": ("dip", "inclinacion"),
    "from": ("from", "desde", "start"),
    "to": ("to", "hasta", "end"),
    "lith": ("lithology", "lith", "litologia", "rock", "code", "codigo"),
    "alt": ("alteration", "alteracion", "alt", "code", "codigo"),
}
MAX_SEGMENTOS = 1_000_000


def normal(s):
    sin_acentos = unicodedata.normalize("NFKD", s.strip().lstrip("\ufeff"))
    return re.sub(r"[^a-z0-9]", "", sin_acentos.lower())


def tabla(texto, nombre, campos):
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError(f"{nombre}: falta un archivo con encabezados.")
    primera = texto.lstrip("\ufeff").splitlines()[0]
    separador = max((",", ";", "\t"), key=primera.count)
    lector = csv.reader(io.StringIO(texto.lstrip("\ufeff")), delimiter=separador, strict=True)
    try:
        crudos = [c.strip() for c in next(lector)]
        ids = [normal(c) for c in crudos]
        if not all(ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{nombre}: los encabezados deben ser únicos y no vacíos.")
        indices = {}
        for campo in campos:
            coincidencias = [i for i, llave in enumerate(ids) if llave in ALIAS[campo]]
            if len(coincidencias) != 1:
                raise ValueError(f"{nombre}: se requiere una columna inequívoca para {ALIAS[campo][0]}.")
            indices[campo] = coincidencias[0]
        filas = []
        for fila in lector:
            if not fila or not any(c.strip() for c in fila):
                continue
            if len(fila) != len(ids):
                raise ValueError(f"{nombre}, línea {lector.line_num}: cantidad de columnas incorrecta.")
            filas.append((lector.line_num, [c.strip() for c in fila]))
        return crudos, indices, filas
    except csv.Error as error:
        raise ValueError(f"{nombre}, línea {lector.line_num}: {error}") from error


def numero(texto, campo):
    try:
        n = float(texto)
    except ValueError as error:
        raise ValueError(f"{campo}: se esperaba un número, se recibió «{texto}».") from error
    if not math.isfinite(n) or abs(n) > 1e12:
        raise ValueError(f"{campo}: número fuera de rango.")
    return n


def rumbo(az, dip):
    a, d = math.radians(az), math.radians(dip)
    return math.cos(d) * math.sin(a), math.cos(d) * math.cos(a), math.sin(d)


def angulo(a, b):
    return math.acos(max(-1, min(1, sum(x * y for x, y in zip(a, b)))))


def integrar(pos, a, b, distancia, beta):
    factor = 1 if beta < 1e-8 else 2 * math.tan(beta / 2) / beta
    return tuple(p + distancia * (u + v) * factor / 2 for p, u, v in zip(pos, a, b))


class Trayectoria:
    def __init__(self, collar, estaciones):
        self.mds = [p[0] for p in estaciones]
        self.dirs = [rumbo(*p[1:]) for p in estaciones]
        self.puntos = [collar]
        self.angulos = []
        for i in range(1, len(estaciones)):
            a, b = self.dirs[i - 1:i + 1]
            beta = angulo(a, b)
            if beta > math.pi - 1e-6:
                raise ValueError("Una inversión de 180° entre estaciones no define un arco único.")
            self.angulos.append(beta)
            self.puntos.append(integrar(self.puntos[-1], a, b, self.mds[i] - self.mds[i - 1], beta))

    def punto(self, md):
        i = min(max(0, bisect_right(self.mds, md) - 1), len(self.mds) - 2)
        delta = md - self.mds[i]
        if delta <= 0:
            return self.puntos[i]
        a, b = self.dirs[i:i + 2]
        beta = self.angulos[i]
        if beta < 1e-8:
            return integrar(self.puntos[i], a, a, delta, 0)
        t = delta / (self.mds[i + 1] - self.mds[i])
        s = math.sin(beta)
        u, v = math.sin((1 - t) * beta) / s, math.sin(t * beta) / s
        intermedio = tuple(x * u + y * v for x, y in zip(a, b))
        return integrar(self.puntos[i], a, intermedio, delta, t * beta)

    def quiebres(self):
        for i, beta in enumerate(self.angulos):
            n = max(1, math.ceil(beta / math.radians(3.0)))
            a, b = self.mds[i:i + 2]
            yield a
            for j in range(1, n):
                yield a + (b - a) * j / n
        yield self.mds[-1]


def collares(texto):
    _, c, filas = tabla(texto, "Collar", ["id", "x", "y", "z", "eoh"])
    if not filas or len(filas) > 15000:
        raise ValueError("Collar debe contener entre 1 y 15.000 taladros.")
    resultado = {}
    for n, f in filas:
        k = f[c["id"]]
        if not k or k in resultado:
            raise ValueError(f"Collar, línea {n}: ID vacío o duplicado «{k}».")
        p = tuple(numero(f[c[e]], f"Collar {k} {e}") for e in ("x", "y", "z", "eoh"))
        if not .001 <= p[-1] <= 50000:
            raise ValueError(f"Collar {k}: EOH debe estar entre 0,001 y 50.000 m.")
        resultado[k] = p
    return resultado


def surveys(texto, collar):
    _, c, filas = tabla(texto, "Survey", ["id", "md", "az", "dip"])
    resultado = {k: [] for k in collar}
    advertencias = []
    for n, f in filas:
        k = f[c["id"]]
        if k not in collar:
            raise ValueError(f"Survey, línea {n}: taladro «{k}» ausente en Collar.")
        md, az, dip = (numero(f[c[e]], f"Survey {k} {e}") for e in ("md", "az", "dip"))
        if not 0 <= md <= collar[k][3] or not 0 <= az <= 360 or not -90 <= dip <= 90:
            raise ValueError(f"Survey {k}, línea {n}: MD, azimut o dip fuera de rango.")
        resultado[k].append((md, az % 360, dip))
    for k, puntos in resultado.items():
        puntos.sort()
        if not puntos:
            raise ValueError(f"Survey: «{k}» no tiene estaciones. Agrega una orientación medida o excluye ese collar.")
        if len({p[0] for p in puntos}) != len(puntos):
            raise ValueError(f"Survey {k}: existe más de una estación en el mismo MD.")
        if puntos[0][0] > 0:
            puntos.insert(0, (0, *puntos[0][1:]))
            advertencias.append(f"{k}: primera orientación extendida al collar.")
        eoh = collar[k][3]
        if puntos[-1][0] < eoh:
            puntos.append((eoh, *puntos[-1][1:]))
            advertencias.append(f"{k}: última orientación extendida hasta EOH.")
        if all(p[2] > 0 for p in puntos):
            advertencias.append(f"{k}: todas las estaciones apuntan hacia arriba. Revisa la convención de dip.")
    return resultado, advertencias


def intervalos(texto, collar, tipo):
    c = {}
    filas = []
    nombres = []
    if texto:
        campos = ["id", "from", "to"] + ([] if tipo == "assay" else [tipo])
        nombres, c, filas = tabla(texto, tipo, campos)
    columnas = [(i, n) for i, n in enumerate(nombres) if i not in c.values()] if tipo == "assay" else []
    if tipo == "assay" and not columnas:
        raise ValueError("Assay requiere al menos una columna analítica además de HoleID, From y To.")
    if len(columnas) > 50:
        raise ValueError("Assay admite hasta 50 columnas analíticas. Retira metadatos del archivo.")
    tramos = {k: [] for k in collar}
    etiquetas = []
    codigos = {}
    datos = array("f")
    calificadores = {}
    for linea, f in filas:
        k = f[c["id"]]
        if k not in collar:
            raise ValueError(f"{tipo}, línea {linea}: taladro «{k}» ausente en Collar.")
        a, b = (numero(f[c[e]], f"{tipo} {k} {e}") for e in ("from", "to"))
        if not 0 <= a < b <= collar[k][3]:
            raise ValueError(f"{tipo} {k}, línea {linea}: debe cumplirse 0 ≤ From < To ≤ EOH.")
        if tipo == "assay":
            indice = len(datos) // len(columnas)
            for j, (i, nombre) in enumerate(columnas):
                texto_valor = f[i]
                try:
                    valor = float(texto_valor)
                    if not math.isfinite(valor) or not 0 <= valor <= 1e12:
                        raise ValueError
                except ValueError:
                    valor = math.nan
                    if texto_valor:
                        calificadores[f"{indice}:{j}"] = texto_valor[:120]
                datos.append(valor)
        else:
            valor = f[c[tipo]]
            indice = -1
            if valor:
                if valor not in codigos:
                    codigos[valor] = len(etiquetas)
                    etiquetas.append(valor)
                indice = codigos[valor]
        tramos[k].append((a, b, indice))
    for k, items in tramos.items():
        items.sort()
        if any(b[0] < a[1] for a, b in zip(items, items[1:])):
            raise ValueError(f"{tipo} {k}: hay intervalos superpuestos.")
    return tramos, etiquetas, [n for _, n in columnas], datos, calificadores


def percentil(ordenados, p):
    i = (len(ordenados) - 1) * p
    a = int(i)
    return ordenados[a] + (ordenados[min(a + 1, len(ordenados) - 1)] - ordenados[a]) * (i - a)


def rango_color(valores):
    datos = sorted(x for x in valores if math.isfinite(x))
    rango = [percentil(datos, .05), percentil(datos, .95)] if datos else [0, 1]
    if rango[0] == rango[1]:
        ancho = max(abs(rango[0]) * .05, .001)
        rango = [rango[0] - ancho, rango[1] + ancho]
    return {"min": rango[0], "max": rango[1], "n": len(datos)}


def numero_atributo(texto):
    """Distingue un número de un límite declarado, sin usar el límite como valor real."""
    muestra = re.fullmatch(r"([<>]=?)?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", texto)
    if muestra:
        valor = float(muestra[2])
        if math.isfinite(valor) and abs(valor) <= 1e12:
            return valor, bool(muestra[1])
    return None, False


def atributos_extra(archivos, collar):
    if not isinstance(archivos, list) or len(archivos) > 12:
        raise ValueError("Atributos: adjunta hasta 12 tablas CSV por proyecto.")
    capas = []
    valores = array("f")
    calificadores = {}
    tramos = []
    llaves = set()
    for j, entrada in enumerate(archivos):
        if not isinstance(entrada, dict) or not isinstance(entrada.get("nombre"), str):
            raise ValueError("Atributos: cada tabla requiere un nombre y contenido CSV.")
        archivo = entrada["nombre"]
        columnas, c, filas = tabla(entrada.get("contenido"), archivo, ["id", "from", "to"])
        extras = [(i, nombre) for i, nombre in enumerate(columnas) if i not in c.values()]
        if not extras or len(capas) + len(extras) > 50:
            raise ValueError("Cada tabla necesita al menos un atributo. El proyecto admite hasta 50.")
        mapa = {k: [] for k in collar}
        for fila_idx, (linea, campos) in enumerate(filas):
            k = campos[c["id"]]
            if k not in collar:
                raise ValueError(f"{archivo}, línea {linea}: taladro «{k}» ausente en Collar.")
            a, b = (numero(campos[c[e]], f"{archivo} {k} {e}") for e in ("from", "to"))
            if not 0 <= a < b <= collar[k][3]:
                raise ValueError(f"{archivo} {k}, línea {linea}: debe cumplirse 0 ≤ From < To ≤ EOH.")
            mapa[k].append((a, b, fila_idx))
        for k, items in mapa.items():
            items.sort()
            if any(b[0] < a[1] for a, b in zip(items, items[1:])):
                raise ValueError(f"{archivo} {k}: hay intervalos superpuestos.")
        tramos.append(mapa)
        for i, encabezado in extras:
            nombre, separador, sufijo = encabezado.partition(":")
            nombre = nombre.strip()
            llave = normal(nombre)
            if not llave or llave in llaves:
                raise ValueError(f"Atributos: nombre vacío o repetido «{nombre}».")
            llaves.add(llave)
            tipo = normal(sufijo)
            if separador and tipo not in {"numerico", "categorico"}:
                raise ValueError(f"{archivo}: usa {nombre}:numerico o {nombre}:categorico.")
            columna = [campos[i] for _, campos in filas]
            if not tipo:
                presentes = [s for s in columna if s]
                tipo = "numerico" if presentes and all(numero_atributo(s)[0] is not None for s in presentes) else "categorico"
            info = {"nombre": nombre, "tipo": tipo, "tabla": j, "offset": len(valores)}
            if tipo == "numerico":
                numero_capa = len(capas)
                muestras = array("f")
                for k, texto in enumerate(columna):
                    valor, limitado = numero_atributo(texto)
                    if texto and valor is None:
                        raise ValueError(f"{archivo}, línea {filas[k][0]}: «{texto}» no es numérico en {nombre}.")
                    if limitado:
                        calificadores[f"{numero_capa}:{k}"] = texto
                    muestras.append(valor if valor is not None and not limitado else math.nan)
                info.update(rango_color(muestras))
                valores.extend(muestras)
            else:
                codigos = {}
                for texto in columna:
                    valores.append(codigos.setdefault(texto, len(codigos)) if texto else math.nan)
                info["categorias"] = list(codigos)
                info["n"] = sum(bool(v) for v in columna)
            capas.append(info)
    return tramos, capas, valores, calificadores


def malla_topo(texto, formato, origen):
    if not texto:
        return array("f"), array("I")
    vertices = array("f")
    indices = array("I")

    def punto(p):
        if len(vertices) >= 900000:
            raise ValueError("Topografía: máximo 300.000 vértices. Simplifica la malla.")
        i = len(vertices) // 3
        vertices.extend(u - v for u, v in zip(p, origen))
        return i

    if formato == "obj":
        for n, linea in enumerate(texto.splitlines(), start=1):
            campos = linea.split("#", 1)[0].split()
            if not campos:
                continue
            if campos[0] == "v":
                if len(campos) < 4:
                    raise ValueError(f"OBJ, línea {n}: vértice incompleto.")
                punto([numero(x, f"OBJ línea {n}") for x in campos[1:4]])
            elif campos[0] == "f":
                cara = []
                total = len(vertices) // 3
                for vert in campos[1:]:
                    num = int(vert.split("/")[0])
                    idx = num - 1 if num > 0 else total + num
                    if num == 0 or not 0 <= idx < total:
                        raise ValueError(f"OBJ, línea {n}: índice de vértice inválido.")
                    cara.append(idx)
                if len(cara) < 3:
                    raise ValueError(f"OBJ, línea {n}: cara incompleta.")
                for i in range(1, len(cara) - 1):
                    indices.extend((cara[0], cara[i], cara[i + 1]))
                if len(indices) > 1800000:
                    raise ValueError("Topografía: máximo 600.000 triángulos. Simplifica la malla.")
    elif formato == "csv":
        _, c, filas = tabla(texto, "Topografía", ["x", "y", "z"])
        puntos = {}
        for n, f in filas:
            p = tuple(numero(f[c[e]], f"Topografía línea {n}") for e in ("x", "y", "z"))
            if p[:2] in puntos:
                raise ValueError(f"Topografía, línea {n}: punto XY duplicado.")
            puntos[p[:2]] = punto(p)
        xs, ys = sorted({a for a, _ in puntos}), sorted({b for _, b in puntos})
        for eje in (xs, ys):
            if len(eje) < 2 or any(not math.isclose(b - a, eje[1] - eje[0], rel_tol=1e-5, abs_tol=1e-7)
                                  for a, b in zip(eje, eje[1:])):
                raise ValueError("Topografía CSV: se requiere una grilla XY regular. Para una malla irregular usa OBJ.")
        if len(xs) * len(ys) > 600000:
            raise ValueError("Topografía: la grilla es demasiado extensa para este visor.")
        for y0, y1 in zip(ys, ys[1:]):
            for x0, x1 in zip(xs, xs[1:]):
                a, b, c, d = (puntos.get(p) for p in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)))
                if None not in (a, b, c):
                    indices.extend((a, b, c))
                if None not in (b, c, d):
                    indices.extend((b, d, c))
    else:
        raise ValueError("Topografía: formato no admitido. Usa CSV o OBJ.")
    if not indices:
        raise ValueError("Topografía: no hay caras válidas para dibujar.")
    return vertices, indices


def construir(proyecto):
    if not isinstance(proyecto, dict):
        raise ValueError("El proyecto debe ser un objeto JSON.")
    archivos = proyecto.get("archivos")
    if not isinstance(archivos, dict):
        raise ValueError("El proyecto debe contener un bloque archivos.")
    for llave in ("collar", "survey", "assay", "lith", "alt", "topo"):
        if llave in archivos and not isinstance(archivos[llave], str):
            raise ValueError(f"{llave}: se esperaba el contenido textual del archivo.")
    nombre = proyecto.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > 100:
        raise ValueError("Escribe un nombre de proyecto de hasta 100 caracteres.")
    collar = collares(archivos.get("collar"))
    medida, advertencias = surveys(archivos.get("survey"), collar)
    a, _, elementos, ensayos, cual = intervalos(archivos.get("assay"), collar, "assay")
    l, litologias, _, _, _ = intervalos(archivos.get("lith"), collar, "lith")
    t, alteraciones, _, _, _ = intervalos(archivos.get("alt"), collar, "alt")
    adicionales, atributos, valores_extra, cual_extra = atributos_extra(archivos.get("atributos", []), collar)
    origen = [(min(p[i] for p in collar.values()) + max(p[i] for p in collar.values())) / 2 for i in range(3)]
    superficie = archivos.get("topo")
    formato = proyecto.get("formato_topo", "csv")
    if superficie and formato in ("asc", "geotiff"):
        cargar_raster = cargar_asc if formato == "asc" else cargar_geotiff
        topo, indices, info_topo = cargar_raster(superficie, origen)
    else:
        topo, indices = malla_topo(superficie, formato, origen)
        info_topo = {"formato": "OBJ" if formato == "obj" else "Grilla CSV"} if indices else {}
    xyz, md, capas = array("f"), array("f"), array("i")
    extra = array("i")
    metadatos = []
    minimo = [math.inf] * 3
    maximo = [-math.inf] * 3
    for k, c in collar.items():
        try:
            trayectoria = Trayectoria(tuple(val - centro for val, centro in zip(c, origen)), medida[k])
        except ValueError as error:
            raise ValueError(f"Survey {k}: {error}") from error
        grupos = [a[k], l[k], t[k], *(tabla[k] for tabla in adicionales)]
        cortes = sorted(set(trayectoria.quiebres()).union(
            d for grupo in grupos for desde, hasta, _ in grupo for d in (desde, hasta)
        ))
        inicio = len(md) // 2
        indices_tramo = [0] * len(grupos)
        anterior = trayectoria.punto(cortes[0])
        for izq, der in zip(cortes, cortes[1:]):
            if der - izq < 1e-8:
                continue
            if len(md) // 2 >= MAX_SEGMENTOS:
                raise ValueError("El proyecto supera 1.000.000 de tramos. Divídelo por campaña o área.")
            siguiente = trayectoria.punto(der)
            xyz.extend(anterior + siguiente)
            md.extend((izq, der))
            medio = (izq + der) / 2
            for i, grupo in enumerate(grupos):
                j = indices_tramo[i]
                while j < len(grupo) and grupo[j][1] <= medio:
                    j += 1
                indices_tramo[i] = j
                destino = capas if i < 3 else extra
                destino.append(grupo[j][2] if j < len(grupo) and grupo[j][0] <= medio < grupo[j][1] else -1)
            for dim in range(3):
                minimo[dim] = min(minimo[dim], anterior[dim], siguiente[dim])
                maximo[dim] = max(maximo[dim], anterior[dim], siguiente[dim])
            anterior = siguiente
        metadatos.append([k, *c, inicio, len(md) // 2 - inicio])
    estadisticas = [{"nombre": n, **rango_color(ensayos[i::len(elementos)])} for i, n in enumerate(elementos)]
    for estadistica in estadisticas:
        estadistica["min"] = max(0, estadistica["min"])
    if info_topo:
        rect = [(min(topo[d::3]), max(topo[d::3])) for d in range(2)]
        if not any(all(rect[d][0] <= p[d] - origen[d] <= rect[d][1] for d in range(2)) for p in collar.values()):
            advertencias.append("La extensión horizontal de la topografía no contiene collares. Revisa CRS, unidades y cobertura.")
    meta = {
        "nombre": nombre, "origen": origen, "min": minimo, "max": maximo,
        "sondajes": metadatos, "metros": sum(c[3] for c in collar.values()),
        "tramos": len(md) // 2, "analitos": estadisticas, "litologias": litologias, "alteraciones": alteraciones,
        "calificadores": cual, "advertencias": advertencias[:60], "total_advertencias": len(advertencias),
        "triangulos": len(indices) // 3, "topografia": info_topo,
        "atributos": atributos, "tablas_extra": len(adicionales), "calificadores_extra": cual_extra,
    }
    return meta, {"xyz": xyz, "md": md, "capas": capas, "ensayos": ensayos,
                  "topo": topo, "caras": indices, "extra": extra, "valores_extra": valores_extra}


def empaquetar(meta, buffers):
    meta = {**meta, "buffers": [[k, len(v), "f" if v.typecode == "f" else v.typecode] for k, v in buffers.items()]}
    cabecera = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode()
    relleno = (-len(cabecera)) % 4
    partes = [b"TS3D", struct.pack("<I", len(cabecera)), cabecera, b" " * relleno]
    for valores in buffers.values():
        if valores.itemsize != 4:
            raise RuntimeError("Esta plataforma no admite buffers de 32 bits del visor.")
        if sys.byteorder != "little":
            valores.byteswap()
        partes.append(valores.tobytes())
    return b"".join(partes)

