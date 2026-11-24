"""Verifica la geometría y la validación de las entradas del visor."""

import base64
from importlib.util import find_spec
import math
import struct
import unittest

from demo import generar, topografia_asc
from sondajes import Trayectoria, construir, empaquetar
from terreno_raster import cargar_asc


def basico():
    return {
        "nombre": "Verificación",
        "formato_topo": "csv",
        "archivos": {
            "collar": "HoleID,East,North,RL,EOH\nA,500000,8900000,1500,100",
            "survey": "HoleID,MD,Azimuth,Dip\nA,0,0,-90\nA,100,0,-90",
            "assay": "HoleID,From,To,Cu_pct,Au_gpt\nA,0,22,0.1,<0.01\nA,35,50,0.3,0.2",
            "lith": "HoleID,From,To,Lithology\nA,10,44,Brecha",
            "alt": "HoleID,From,To,Alteration\nA,44,100,Fílica",
        },
    }


class GeometriaTest(unittest.TestCase):
    def test_arco_horizontal_y_posicion_intermedia(self):
        arco = Trayectoria((0, 0, 0), [(0, 0, 0), (100, 90, 0)])
        radio = 100 / (math.pi / 2)
        x, y, z = arco.punto(100)
        self.assertAlmostEqual(x, radio)
        self.assertAlmostEqual(y, radio)
        self.assertAlmostEqual(z, 0)
        x, y, _ = arco.punto(50)
        self.assertAlmostEqual(x, radio * (1 - math.cos(math.pi / 4)))
        self.assertAlmostEqual(y, radio * math.sin(math.pi / 4))

    def test_tramos_sin_ensayo_y_censuras(self):
        meta, b = construir(basico())
        self.assertEqual(meta["origen"], [500000, 8900000, 1500])
        self.assertEqual(list(b["md"]), [0, 10, 10, 22, 22, 35, 35, 44, 44, 50, 50, 100])
        self.assertEqual(list(b["capas"][::3]), [0, 0, -1, 1, 1, -1])
        self.assertEqual(list(b["capas"][1::3]), [-1, 0, 0, 0, -1, -1])
        self.assertEqual(list(b["capas"][2::3]), [-1, -1, -1, -1, 0, 0])
        self.assertAlmostEqual(b["xyz"][-1], -100)
        self.assertTrue(math.isnan(b["ensayos"][1]))
        self.assertEqual(meta["calificadores"]["0:1"], "<0.01")

    def test_expandir_orientacion_con_aviso(self):
        p = basico()
        p["archivos"]["survey"] = "HoleID;MD;Azimuth;Dip\nA;20;90;-30"
        meta, buffers = construir(p)
        self.assertEqual(meta["total_advertencias"], 2)
        self.assertAlmostEqual(buffers["xyz"][-3], 100 * math.cos(math.pi / 6), places=4)
        self.assertAlmostEqual(buffers["xyz"][-1], -50)

    def test_rechazar_superposicion_e_id_desconocido(self):
        for fila, causa in (("A,20,40,1,0", "superpuestos"), ("Z,51,52,1,0", "ausente en Collar")):
            with self.subTest(fila=fila):
                p = basico()
                p["archivos"]["assay"] += "\n" + fila
                with self.assertRaisesRegex(ValueError, causa):
                    construir(p)

    def test_topografia_csv_obj_y_empaquetado(self):
        p = basico()
        p["archivos"]["topo"] = "East,North,RL\n500000,8900000,1500\n500010,8900000,1501\n500000,8900010,1502\n500010,8900010,1503"
        meta, b = construir(p)
        self.assertEqual(meta["triangulos"], 2)
        self.assertEqual(list(b["topo"][:3]), [0, 0, 0])
        paquete = empaquetar(meta, b)
        self.assertEqual(paquete[:4], b"TS3D")
        n = struct.unpack_from("<I", paquete, 4)[0]
        self.assertEqual(len(paquete), 8 + (n + 3) // 4 * 4 + 4 * sum(map(len, b.values())))
        p["formato_topo"] = "obj"
        p["archivos"]["topo"] = "v 500000 8900000 1500\nv 500010 8900000 1501\nv 500000 8900010 1502\nf -3 -2 -1"
        self.assertEqual(construir(p)[0]["triangulos"], 1)

    def test_proyecto_sintetico(self):
        meta, b = construir(generar())
        self.assertEqual(len(meta["sondajes"]), 48)
        self.assertEqual(meta["tramos"] * 6, len(b["xyz"]))
        self.assertEqual(meta["tramos"] * 3, len(b["capas"]))
        self.assertEqual(meta["total_advertencias"], 0)

    def test_dem_asc_norte_esquina_y_nodata(self):
        encabezado = "NCOLS 3\nNROWS 2\nXLLCORNER 500000\nYLLCORNER 8900000\nCELLSIZE 10\nNODATA_VALUE -9999\n"
        puntos, caras, info = cargar_asc(
            encabezado + "1512 1513 -9999\n1500 1501 1502\n", (500000, 8900000, 1500)
        )
        self.assertEqual(list(puntos[:6]), [5, 15, 12, 15, 15, 13])
        self.assertEqual(len(puntos) // 3, 5)
        self.assertEqual(len(caras) // 3, 3)
        self.assertEqual(info["malla"], [3, 2])
        with self.assertRaisesRegex(ValueError, "se esperaban 6 cotas"):
            cargar_asc(encabezado + "1 2 3", (0, 0, 0))

    def test_dem_asc_grande_reduce_resolucion(self):
        proyecto = generar()
        csv = proyecto["archivos"]["topo"]
        proyecto["archivos"]["topo"] = topografia_asc(csv)
        proyecto["formato_topo"] = "asc"
        meta, _ = construir(proyecto)
        self.assertEqual(meta["topografia"]["formato"], "DEM ASCII")
        self.assertEqual(meta["triangulos"], construir(generar())[0]["triangulos"])
        columnas = 442
        encabezado = f"NCOLS {columnas}\nNROWS 3\nXLLCENTER 0\nYLLCENTER 0\nCELLSIZE 10\n"
        puntos, _, info = cargar_asc(encabezado + ("4 " * columnas + "\n") * 3, (0, 0, 0))
        self.assertEqual(info["malla"], [220, 2])
        self.assertEqual(max(puntos[::3]), (columnas - 1) * 10)

    def test_atributos_multiples_soportes_y_codigos(self):
        proyecto = basico()
        proyecto["archivos"]["atributos"] = [
            {"nombre": "mecanica.csv", "contenido":
             "HoleID,From,To,RQD:numerico,Codigo:categorico\nA,0,15,85,01\nA,20,40,<15,02"},
            {"nombre": "vetas.csv", "contenido": "HoleID,From,To,Veta\nA,25,55,Cuarzo"},
        ]
        meta, b = construir(proyecto)
        self.assertEqual(meta["tablas_extra"], 2)
        self.assertEqual([a["tipo"] for a in meta["atributos"]], ["numerico", "categorico", "categorico"])
        self.assertEqual(meta["atributos"][1]["categorias"], ["01", "02"])
        self.assertEqual(meta["calificadores_extra"]["0:1"], "<15")
        self.assertEqual(len(b["extra"]), 2 * meta["tramos"])
        cortes = list(b["md"][::2])
        self.assertEqual(list(b["extra"][2 * cortes.index(25):2 * cortes.index(25) + 2]), [1, 0])
        self.assertEqual(list(b["extra"][2 * cortes.index(15):2 * cortes.index(15) + 2]), [-1, -1])
        proyecto["archivos"]["atributos"][1]["contenido"] += "\nA,54,70,Otra"
        with self.assertRaisesRegex(ValueError, "superpuestos"):
            construir(proyecto)

    @unittest.skipUnless(find_spec("rasterio"), "Rasterio opcional")
    def test_geotiff_georeferenciado_y_nodata(self):
        import numpy as np
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin

        transformacion = from_origin(499995, 8900015, 10, 10)
        with MemoryFile() as memoria:
            with memoria.open(driver="GTiff", height=2, width=2, count=1, dtype="float32",
                              transform=transformacion, crs="EPSG:32718", nodata=-9999) as raster:
                raster.write(np.array([[1500, 1501], [1502, -9999]], dtype="float32"), 1)
            geo = base64.b64encode(memoria.read()).decode()
        p = basico()
        p.update(formato_topo="geotiff")
        p["archivos"]["topo"] = geo
        meta, b = construir(p)
        self.assertEqual(meta["topografia"]["crs"], "EPSG:32718")
        self.assertEqual(meta["triangulos"], 1)
        self.assertEqual(list(b["topo"][:3]), [0, 10, 0])


if __name__ == "__main__":
    unittest.main()

