"""Arranca el visor local de sondajes 3D con la biblioteca estándar de Python."""

import argparse
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit
import webbrowser

from demo import generar
from sondajes import construir, empaquetar


WEB = Path(__file__).resolve().parent / "web"
MAX_CARGA = 160 * 1024 * 1024
TAMANOS = {"demo": 48, "carga": 1500}


@lru_cache(maxsize=2)
def ejemplo(clave):
    proyecto = generar(TAMANOS[clave])
    return empaquetar(*construir(proyecto))


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, puerto):
        super().__init__(("127.0.0.1", puerto), Peticion)
        self.destinos = {f"{host}:{self.server_port}" for host in ("127.0.0.1", "localhost")}


class Peticion(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def local(self):
        host = self.headers.get("Host")
        origen = self.headers.get("Origin")
        return host in self.server.destinos and (not origen or origen == f"http://{host}")

    def datos(self, estado, cuerpo, tipo):
        self.send_response(estado)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(cuerpo)

    def error_json(self, estado, mensaje):
        self.datos(estado, json.dumps({"error": mensaje}, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        if not self.local():
            return self.error_json(403, "El visor solo atiende solicitudes de su propio origen local.")
        ruta = urlsplit(self.path).path
        if ruta in {"/", "/index.html", "/estilo.css", "/visor.js", "/gl.js", "/marca.svg"}:
            return super().do_GET()
        partes = ruta.strip("/").split("/")
        if len(partes) == 3 and partes[:2] == ["api", "ejemplo"] and partes[2] in TAMANOS:
            try:
                return self.datos(200, ejemplo(partes[2]), "application/octet-stream")
            except (BrokenPipeError, ConnectionResetError):
                return
        if ruta == "/api/plantilla":
            cuerpo = json.dumps(generar(), ensure_ascii=False).encode()
            return self.datos(200, cuerpo, "application/json; charset=utf-8")
        return self.error_json(404, "Ruta no disponible.")

    def do_HEAD(self):
        if self.local() and urlsplit(self.path).path in {"/", "/index.html", "/estilo.css", "/visor.js", "/gl.js", "/marca.svg"}:
            return super().do_HEAD()
        self.send_error(404)

    def do_POST(self):
        if not self.local():
            return self.error_json(403, "Origen ajeno al visor local.")
        if urlsplit(self.path).path != "/api/importar":
            return self.error_json(404, "Ruta no disponible.")
        if self.headers.get_content_type() != "application/json":
            return self.error_json(415, "La importación requiere JSON.")
        try:
            largo = int(self.headers.get("Content-Length", "0"))
            if not 0 < largo <= MAX_CARGA:
                return self.error_json(413, "La importación admite hasta 160 MiB de proyecto codificado.")
            entrada = json.loads(self.rfile.read(largo))
            self.datos(200, empaquetar(*construir(entrada)), "application/octet-stream")
        except (BrokenPipeError, ConnectionResetError):
            return
        except (ValueError, OverflowError, RecursionError) as error:
            self.error_json(400, str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8765)
    parser.add_argument("--sin-abrir", action="store_true", help="Evita abrir el navegador automáticamente.")
    args = parser.parse_args()
    try:
        servidor = Servidor(args.puerto)
    except (OSError, OverflowError) as error:
        parser.exit(2, f"No se pudo iniciar el visor local: {error}\n")
    with servidor:
        url = f"http://127.0.0.1:{servidor.server_port}/"
        print(f"Traza 3D · {url}", flush=True)
        if not args.sin_abrir:
            webbrowser.open(url)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

