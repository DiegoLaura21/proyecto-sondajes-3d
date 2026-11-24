"""Convierte modelos de elevación ASC o GeoTIFF en una malla para WebGL."""

from array import array
import base64
import binascii
from itertools import chain
import io
import math


LADO_MAXIMO = 220


def limitar_ejes(ncols, nrows):
    if ncols < 2 or nrows < 2:
        raise ValueError("El ráster de elevación necesita al menos dos filas y dos columnas.")
    factor = max(1.0, max(ncols, nrows) / LADO_MAXIMO)
    return max(2, math.ceil(ncols / factor)), max(2, math.ceil(nrows / factor))


def malla(filas, columnas, obtener, origen):
    vertices = array("f")
    indices = array("I")
    anterior = []
    for f in range(filas):
        actual = []
        for c in range(columnas):
            p = obtener(f, c)
            if p is None:
                actual.append(None)
                continue
            if any(not math.isfinite(v) or abs(v) > 1e12 for v in p):
                raise ValueError("El ráster contiene coordenadas o cotas fuera de rango.")
            actual.append(len(vertices) // 3)
            vertices.extend(v - o for v, o in zip(p, origen))
        for a, b, c, d in zip(anterior, anterior[1:], actual, actual[1:]):
            triangulos = ((a, b, c), (b, d, c)) if b is not None and c is not None else ((a, b, d), (a, d, c))
            for cara in triangulos:
                if None not in cara:
                    indices.extend(cara)
        anterior = actual
    if not indices:
        raise ValueError("El ráster no tiene triángulos válidos. Revisa la cobertura y los valores NoData.")
    return vertices, indices


def seleccionar(tamano, objetivo):
    return [round(i * (tamano - 1) / (objetivo - 1)) for i in range(objetivo)]


def cargar_asc(texto, origen):
    claves = {"ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter", "cellsize", "nodata_value"}
    archivo = iter(io.StringIO(texto.lstrip("\ufeff")))
    encabezado = {}
    primera_fila = ""
    for linea in archivo:
        partes = linea.split()
        if not partes:
            continue
        clave = partes[0].lower()
        if clave not in claves:
            primera_fila = linea
            break
        if len(partes) != 2 or clave in encabezado:
            raise ValueError(f"Ráster ASC: encabezado inválido o repetido «{clave}».")
        encabezado[clave] = partes[1]
    try:
        nx, ny = int(encabezado["ncols"]), int(encabezado["nrows"])
        paso = float(encabezado["cellsize"])
        esquinas = {"xllcorner", "yllcorner"} & encabezado.keys()
        centros = {"xllcenter", "yllcenter"} & encabezado.keys()
        if len(esquinas) == 2 and not centros:
            x0 = float(encabezado["xllcorner"]) + paso / 2
            y0 = float(encabezado["yllcorner"]) + paso / 2
        elif len(centros) == 2 and not esquinas:
            x0, y0 = float(encabezado["xllcenter"]), float(encabezado["yllcenter"])
        else:
            raise ValueError("Indica XLLCORNER/YLLCORNER o XLLCENTER/YLLCENTER.")
        nodata = float(encabezado.get("nodata_value", "-9999"))
        if not all(math.isfinite(v) for v in (paso, x0, y0)) or paso <= 0:
            raise ValueError("Revisa origen y tamaño de celda.")
    except (KeyError, ValueError) as error:
        raise ValueError(f"Ráster ASC: encabezado inválido. {error}") from error
    sx, sy = limitar_ejes(nx, ny)
    ix, iy = seleccionar(nx, sx), seleccionar(ny, sy)
    requeridos = iter((f * nx + c, f, c) for f in iy for c in ix)
    siguiente = next(requeridos, None)
    valores = {}
    recibidos = 0
    for linea in chain((primera_fila,), archivo):
        for s in linea.split():
            if recibidos >= nx * ny:
                raise ValueError("Ráster ASC: hay más valores de elevación de los que declara el encabezado.")
            if siguiente and recibidos == siguiente[0]:
                _, f, c = siguiente
                try:
                    z = float(s)
                except ValueError as error:
                    raise ValueError(f"Ráster ASC: cota inválida en la fila {f + 1}, columna {c + 1}.") from error
                if z != nodata and math.isfinite(z):
                    valores[f, c] = z
                siguiente = next(requeridos, None)
            recibidos += 1
    if recibidos != nx * ny:
        raise ValueError(f"Ráster ASC: se esperaban {nx * ny} cotas y se encontraron {recibidos}.")

    def obtener(f, c):
        fila, col = iy[f], ix[c]
        z = valores.get((fila, col))
        return None if z is None else (x0 + col * paso, y0 + (ny - 1 - fila) * paso, z)

    puntos, caras = malla(sy, sx, obtener, origen)
    return puntos, caras, {"formato": "DEM ASCII", "original": [nx, ny], "malla": [sx, sy]}


def cargar_geotiff(texto, origen):
    try:
        from numpy.ma import getmaskarray
        from rasterio import Env
        from rasterio.enums import Resampling
        from rasterio.errors import RasterioError
        from rasterio.io import MemoryFile
        from rasterio.transform import Affine
    except ImportError as error:
        raise ValueError(
            "GeoTIFF requiere Rasterio. Ejecuta python -m pip install -r requirements-geotiff.txt, "
            "o exporta el DEM como ASC desde tu SIG."
        ) from error
    try:
        contenido = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("GeoTIFF: el archivo codificado en el proyecto es inválido.") from error

    try:
        with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_GEOREF_SOURCES="INTERNAL"):
            with MemoryFile(contenido) as memoria, memoria.open() as raster:
                if raster.driver != "GTiff" or raster.count != 1:
                    raise ValueError("Usa un GeoTIFF DEM de una banda. Exporta solo la banda de elevación.")
                crs = raster.crs
                if crs is None or not crs.is_projected:
                    raise ValueError("GeoTIFF: usa un CRS proyectado en metros que coincida con Collar.")
                unidad, factor = crs.linear_units_factor
                if not math.isclose(factor, 1, abs_tol=1e-9):
                    raise ValueError(f"GeoTIFF: la unidad horizontal «{unidad}» no es el metro.")
                transformacion = raster.transform
                if transformacion == Affine.identity() or abs(transformacion.determinant) < 1e-15:
                    raise ValueError("GeoTIFF: falta una transformación espacial válida.")
                nx, ny = raster.width, raster.height
                sx, sy = limitar_ejes(nx, ny)
                cotas = raster.read(1, out_shape=(sy, sx), masked=True, resampling=Resampling.nearest)
                mascara = getmaskarray(cotas)
                escala, offset = raster.scales[0], raster.offsets[0]
                identificador = crs.to_string()
    except RasterioError as error:
        raise ValueError(f"No se pudo leer el GeoTIFF: {error}") from error

    def obtener(f, c):
        if mascara[f, c]:
            return None
        z = float(cotas.data[f, c]) * escala + offset
        if not math.isfinite(z):
            return None
        col = (c + .5) * nx / sx
        fila = (f + .5) * ny / sy
        x = transformacion.a * col + transformacion.b * fila + transformacion.c
        y = transformacion.d * col + transformacion.e * fila + transformacion.f
        return x, y, z

    puntos, caras = malla(sy, sx, obtener, origen)
    return puntos, caras, {"formato": "GeoTIFF", "crs": identificador, "original": [nx, ny], "malla": [sx, sy]}

