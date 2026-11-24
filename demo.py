"""Proyecto ficticio para explorar el visor o hacer una prueba de carga."""

import argparse
import csv
import io
import math
from pathlib import Path
from random import Random


X0, Y0 = 519800, 8642300


def relieve(x, y):
    loma = 69 * math.exp(-((x - 80) / 440) ** 2 - ((y - 120) / 390) ** 2)
    return 1450 + loma + 18 * math.sin(x / 125 + y / 300) + 10 * math.cos(y / 98)


def texto(encabezado, filas):
    archivo = io.StringIO()
    w = csv.writer(archivo, lineterminator="\n")
    w.writerow(encabezado.split(","))
    w.writerows(filas)
    return archivo.getvalue()


def generar(cantidad=48):
    rng = Random(12511 + cantidad)
    lado = math.ceil(math.sqrt(cantidad * 1.25))
    collar, survey, assay, litologia, alteracion, atributos = [], [], [], [], [], []
    for i in range(cantidad):
        fila, columna = divmod(i, lado)
        x = (columna - (lado - 1) / 2) * 105 + rng.uniform(-19, 19)
        y = (fila - (math.ceil(cantidad / lado) - 1) / 2) * 115 + rng.uniform(-21, 21)
        z = relieve(x, y)
        eoh = rng.randrange(306, 555, 6)
        id_ = f"AH-{i + 1:04}"
        collar.append((id_, round(X0 + x, 2), round(Y0 + y, 2), round(z, 2), eoh))
        az = (113 if columna % 4 != 0 else 269) + rng.uniform(-27, 27)
        dip = rng.uniform(-81, -49)
        for md in [0, *range(60, eoh, 60), eoh]:
            giro = 11 * math.sin(md / 175 + i / 9)
            survey.append((id_, md, round((az + giro) % 360, 3), round(dip + 8 * math.sin(md / 230), 3)))

        contacto = rng.randrange(45, 92)
        intrusivo = contacto + rng.randrange(85, 151)
        brecha = min(eoh - 20, intrusivo + rng.randrange(50, 97))
        ultimos = [0, contacto, intrusivo, brecha, eoh]
        litologia.extend((id_, a, b, roca) for a, b, roca in zip(
            ultimos, ultimos[1:], ["Andesita", "Diorita", "Brecha", "Pórfido"],
        ))
        cambio = rng.randrange(48, 108)
        fin_nucleo = min(eoh - 20, cambio + rng.randrange(105, 201))
        alteracion.extend([
            (id_, 0, cambio, "Propilítica"), (id_, cambio, fin_nucleo, "Fílica"),
            (id_, fin_nucleo, eoh, "Potásica" if (columna + fila) % 3 else "Argílica"),
        ])
        for a in range(0, eoh, 6):
            b = min(eoh, a + 6)
            if (i * 7 + a) % 101 == 0:
                continue
            md = (a + b) / 2
            nucleo = math.exp(-((x + 0.28 * md - 100) / 350) ** 2
                              - ((y - 20) / 330) ** 2 - ((md - 235) / 130) ** 2)
            cu = (0.09 + 0.91 * nucleo) * rng.uniform(0.48, 1.53)
            au = (0.012 + 0.79 * nucleo ** 1.35) * rng.uniform(0.24, 1.8)
            assay.append((id_, a, b, round(cu, 4), round(au, 4) if au >= 0.01 else "<0.01"))
        # Límites que coinciden con estaciones Survey para no fragmentar más la geometría.
        control = Random(99117 + i)
        for a in range(0, eoh, 120):
            b = min(eoh, a + 120)
            rqd = max(8, min(99, round(82 - 28 * (contacto <= a < brecha) + control.uniform(-17, 15), 1)))
            recuperacion = round(min(100, 95 + .06 * (rqd - 55) + control.uniform(-4, 4)), 1)
            veta = ["Diseminado", "Vetillas", "Veta", "Brecha"][(i + a // 120) % 4]
            atributos.append((id_, a, b, rqd, recuperacion, veta))
    min_x = min(r[1] for r in collar) - X0 - 80
    max_x = max(r[1] for r in collar) - X0 + 110
    min_y = min(r[2] for r in collar) - Y0 - 80
    max_y = max(r[2] for r in collar) - Y0 + 110
    intervalo = 28 if cantidad <= 48 else 61
    topo = [(X0 + x, Y0 + y, round(relieve(x, y), 3))
            for y in range(math.floor(min_y), math.ceil(max_y) + intervalo, intervalo)
            for x in range(math.floor(min_x), math.ceil(max_x) + intervalo, intervalo)]
    archivos = {
        "collar": texto("HoleID,East,North,RL,EOH", collar),
        "survey": texto("HoleID,MD,Azimuth,Dip", survey),
        "assay": texto("HoleID,From,To,Cu_pct,Au_gpt", assay),
        "lith": texto("HoleID,From,To,Lithology", litologia),
        "alt": texto("HoleID,From,To,Alteration", alteracion),
        "topo": texto("East,North,RL", topo),
        "atributos": [{
            "nombre": "atributos.csv",
            "contenido": texto(
                "HoleID,From,To,RQD_pct:numerico,Recuperacion_pct:numerico,Textura:categorico", atributos,
            ),
        }],
    }
    nombre = "Pórfido Alto Horizonte" if cantidad <= 48 else "Alto Horizonte · prueba de carga"
    return {"nombre": nombre, "archivos": archivos, "formato_topo": "csv"}


def topografia_asc(csv_topo):
    puntos = {(int(x), int(y)): z for x, y, z in list(csv.reader(io.StringIO(csv_topo)))[1:]}
    xs, ys = sorted({x for x, _ in puntos}), sorted({y for _, y in puntos})
    cabecera = [
        f"NCOLS {len(xs)}", f"NROWS {len(ys)}", f"XLLCENTER {xs[0]}", f"YLLCENTER {ys[0]}",
        f"CELLSIZE {xs[1] - xs[0]}", "NODATA_VALUE -9999",
    ]
    filas = [" ".join(puntos[x, y] for x in xs) for y in reversed(ys)]
    return "\n".join([*cabecera, *filas]) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", type=Path, nargs="?", default=Path("datos_demo"))
    args = parser.parse_args()
    args.destino.mkdir(parents=True, exist_ok=True)
    nombres = {"lith": "lithology", "alt": "alteration", "topo": "topografia"}
    archivos = generar()["archivos"]
    for tabla in archivos["atributos"]:
        (args.destino / tabla["nombre"]).write_text(tabla["contenido"], encoding="utf-8", newline="")
    for k, v in archivos.items():
        if k != "atributos":
            (args.destino / f"{nombres.get(k, k)}.csv").write_text(v, encoding="utf-8", newline="")
    (args.destino / "topografia.asc").write_text(topografia_asc(archivos["topo"]), encoding="utf-8", newline="")

