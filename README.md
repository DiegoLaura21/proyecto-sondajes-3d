# Traza 3D · Visor de sondajes

Aplicación local para visualizar sondajes de exploración. Python valida las tablas y reconstruye cada trayectoria. El navegador dibuja la escena con WebGL 2 y permite cambiar entre ensayes, litología, alteración, atributos personalizados y trazas.

## Abrir el visor

Necesitas Python **3.10 o posterior** y un navegador con WebGL 2. Desde la carpeta del proyecto, ejecuta:

```bash
python app.py
```

En macOS o Linux puedes usar `python3 app.py`. En Windows con el lanzador de Python también puedes usar `py -3 app.py`. El navegador abre [http://127.0.0.1:8765/](http://127.0.0.1:8765/) y carga **Pórfido Alto Horizonte**, un proyecto ficticio de 48 taladros. Mantén la terminal abierta mientras uses la aplicación. Para detenerla, presiona **Ctrl+C**.

```bash
python app.py --puerto 8766 --sin-abrir
```

El servidor escucha solo en `127.0.0.1`. Las tablas se procesan en tu computadora. El visor base usa la biblioteca estándar de Python. La carga de GeoTIFF requiere el complemento opcional descrito abajo. `app.py` inicia el servidor, `sondajes.py` contiene la geometría y validación, `terreno_raster.py` lee los DEM, `demo.py` genera los datos de ejemplo y `web/` contiene la interfaz y el renderizador.

## Explorar la escena

- **Capas.** Cambia el color de las trazas por ensaye, litología o alteración. Los colores de ensaye abarcan P5–P95 de los valores cuantificados del analito en todo el proyecto. Valores fuera del rango usan los colores extremos de la leyenda. El gris indica que el tramo carece de un valor cuantificado o de una clasificación para la capa activa.
- **Atributos.** Selecciona una columna como RQD, recuperación o textura en **Atributos**. Las columnas numéricas usan una escala P5–P95 y las categóricas tienen un color por código. El inspector del tramo incluye los demás atributos cargados.
- **Topografía.** Activa la superficie de referencia y regula su opacidad para distinguir las trazas bajo ella. Los collares se muestran como puntos independientes. La grilla inferior es una referencia visual.
- **Vistas.** Usa 3D, Planta, Norte o Este. Arrastra para orbitar, usa **Shift + arrastre** o el botón secundario para desplazar y gira la rueda para acercar. Con el lienzo enfocado, también funcionan las flechas y las teclas **+** y **−**.
- **Inspección.** Haz clic sobre un tramo para consultar ID, coordenadas del collar, MD, cota, ensaye, litología y alteración. Escribe el ID en el buscador para enfocar directamente el taladro. El MD mostrado pertenece al tramo dibujado. El visor divide la trayectoria donde cambian los registros que se superponen visualmente.
- **Proyectos.** Alterna entre el ejemplo, la escena de carga y las campañas que importes durante la sesión. **Guardar proyecto** descarga un JSON con las tablas originales. Para reabrirlo, elígelo en el campo **Proyecto guardado**. Guarda cada campaña que quieras recuperar después de cerrar la pestaña.

## Importar tus propios datos

1. Exporta los archivos con texto UTF-8, encabezados en la primera fila y punto decimal. Se aceptan coma, punto y coma o tabulador.
2. Verifica que **Collar** y **topografía** estén en el mismo sistema de referencia, datum vertical y unidades. Toda la geometría debe venir en metros. El visor trabaja con las coordenadas recibidas y no reproyecta archivos.
3. En **Importar proyecto**, escribe un nombre. Adjunta Collar, Survey, Assay y las capas opcionales que tengas. Puedes seleccionar varios CSV a la vez en **Atributos por intervalo**. Los archivos de [datos_demo](datos_demo/) sirven de plantilla.
4. Si la importación alerta sobre algún archivo, corrige los datos de origen y vuelve a cargarlo. El proyecto activo se conserva si la validación falla. Revisa las advertencias de orientación en la barra de estado.

| Archivo | Encabezados recomendados | Contenido |
| --- | --- | --- |
| [Collar](datos_demo/collar.csv) | `HoleID,East,North,RL,EOH` | Un registro por ID. Este, norte, cota del collar y profundidad final medida. |
| [Survey](datos_demo/survey.csv) | `HoleID,MD,Azimuth,Dip` | Estaciones por ID. Azimut en grados desde el norte en sentido horario. Dip desde la horizontal, negativo hacia abajo. Un vertical descendente usa −90°. |
| [Assay](datos_demo/assay.csv) | `HoleID,From,To,Cu_pct,Au_gpt` | Intervalos medidos y uno o más analitos. Conserva la unidad en el nombre del analito. Puedes usar otros elementos y nombres. |
| [Lithology](datos_demo/lithology.csv) | `HoleID,From,To,Lithology` | Código o nombre de roca por intervalo. |
| [Alteration](datos_demo/alteration.csv) | `HoleID,From,To,Alteration` | Código o nombre de alteración por intervalo. |
| [Atributos](datos_demo/atributos.csv) | `HoleID,From,To,RQD_pct:numerico,Textura:categorico` | Uno o más CSV con campos y soportes independientes por profundidad. |
| [Topografía ASC](datos_demo/topografia.asc) o [grilla CSV](datos_demo/topografia.csv) | DEM ASCII, GeoTIFF de una banda, `East,North,RL` o malla `.obj` | Elevación del terreno en las mismas coordenadas y datum vertical que Collar. |

Los IDs deben coincidir exactamente entre archivos. Las estaciones Survey pueden llegar desordenadas. Se valida que una profundidad de estación aparezca una sola vez. En cada tabla de intervalos se cumple **0 ≤ From < To ≤ EOH**. Los tramos no pueden traslaparse dentro de una misma tabla y pueden dejar huecos. La cobertura de litología, alteración y ensayes se valida por separado.

El cálculo usa **curvatura mínima** entre estaciones. Si la primera estación queda después del collar, se prolonga su orientación hasta MD 0. Si el Survey termina antes de EOH, se prolonga el rumbo de la última estación. En ambos casos la aplicación emite una advertencia. Cada taladro requiere al menos una estación. Antes de explorar una campaña real, comprueba la convención angular del contratista y revisa estas extensiones. [Seequent, métodos de reconstrucción de trayectorias](https://developer.seequent.com/docs/data-structures/geoscience-objects/schemas/components/desurvey-method/).

Assay acepta valores no negativos. Los calificadores como `<0.01` o `>10` se conservan para el inspector y quedan fuera de la escala de ley. El visor usa las unidades de ensaye del archivo.

### Cargar topografía ráster

1. En tu SIG, elige un **DEM de elevación**. Verifica que el sistema de referencia proyectado, el datum vertical y las unidades coincidan con las coordenadas de Collar. Si tu DEM está en latitud y longitud, reproyéctalo al CRS de la campaña. Recórtalo al área de los sondajes con el margen que quieras visualizar.
2. Exporta como **GeoTIFF (`.tif` o `.tiff`) de una banda** con georreferenciación y NoData internos, o como **DEM Esri ASCII (`.asc`)**. Para probar sin instalar paquetes, selecciona el [ASC de ejemplo](datos_demo/topografia.asc). La lectura ASC admite tanto `XLLCORNER/YLLCORNER` como `XLLCENTER/YLLCENTER`. [Especificación de ráster a ASCII de Esri](https://pro.arcgis.com/en/pro-app/3.5/tool-reference/conversion/raster-to-ascii.htm).
3. Si elegiste GeoTIFF, instala Rasterio en el mismo entorno con que ejecutas el visor y reinicia el servidor.

   ```bash
   python -m pip install -r requirements-geotiff.txt
   python app.py
   ```

4. En **Importar proyecto → Topografía**, adjunta el DEM junto con tus tablas. Al abrir la escena, ajusta **Opacidad del terreno**. Si la extensión horizontal del DEM queda fuera de todos los collares, el visor muestra una advertencia. Si la elevación resulta incoherente, revisa las unidades o el datum vertical en el SIG.

El visor construye triángulos a partir de los centros de las celdas válidas. Cuando un eje supera 220 celdas, reduce la malla manteniendo la proporción de las dimensiones. GeoTIFF usa vecino más cercano y respeta la máscara del ráster muestreado. Los huecos menores que el nuevo paso pueden perderse al reducir. Usa esta superficie como referencia visual. Para una topografía irregular ya triangulada, puedes adjuntar un **OBJ** con vértices `v Este Norte Cota`. También se mantiene la entrada **CSV** para grillas XY regulares. [Rasterio, lectura y remuestreo de mallas](https://rasterio.readthedocs.io/en/stable/topics/resampling.html).

### Agregar atributos propios

1. Crea un CSV con `HoleID,From,To` más una o varias columnas con datos. Un ejemplo de geotecnia y vetillas podría verse así.

   ```csv
   HoleID,From,To,RQD_pct:numerico,Recuperacion_pct:numerico,Textura:categorico
   AH-0001,0,60,82,96,Diseminado
   AH-0001,60,120,48,91,Vetillas
   AH-0002,0,45,71,98,Veta
   ```

2. Usa `:numerico` para medidas o `:categorico` para clases. Si omites el sufijo, el visor infiere tipo numérico cuando los valores presentes son números o límites numéricos. Declara `:categorico` para códigos como `01` y `02` si son etiquetas. Deja celdas vacías para atributos faltantes. En campos numéricos, un límite como `<5` queda visible en el inspector con su calificador.
3. Adjunta uno o varios CSV en **Atributos por intervalo**. Puedes usar una tabla para RQD y otra para densidad, estructuras o intensidad de vetillas aunque sus intervalos tengan longitudes diferentes. Cada tabla exige intervalos sin traslapes por taladro. Usa nombres de atributo únicos en el proyecto.
4. Activa la capa **Atributos** y escoge la columna. Haz clic en un tramo para ver su valor y abre **Otros atributos** para consultar los demás. El JSON de **Guardar proyecto** conserva los CSV de atributos y el terreno ingresado.

La aplicación admite hasta **12 tablas y 50 atributos personalizados** por proyecto. Usa una tabla con varias columnas cuando los atributos compartan los mismos intervalos. Los límites de muestreo adicionales forman tramos en la geometría, así que el costo de dibujo crece con la cantidad de intervalos y taladros.

## Rendimiento y pruebas

La escena de carga contiene **1.500 taladros**, **113.088 tramos** y **10.608 triángulos** de terreno. **Medir FPS en órbita** recorre la escena durante unos tres segundos y muestra la mediana de FPS y el percentil 95 del tiempo entre cuadros. Repite la medición con el navegador en primer plano, mismo tamaño de ventana y la misma calidad. El resultado depende de la GPU, pantalla, navegador y geometría. La medida indica cadencia visible del navegador y no separa el tiempo de CPU del de GPU.

En una corrida de verificación de esa escena en el navegador integrado, con ventana de 1.280 × 720, calidad Adaptable y RQD activo, el visor registró **164 FPS de mediana** y un **p95 de 6,2 ms** entre cuadros.

El renderizador agrupa los tramos en una sola llamada instanciada y usa buffers binarios, sin crear un objeto gráfico independiente para cada intervalo. La escena se redibuja cuando hay una interacción o un cambio. **Adaptable** reduce la resolución durante el movimiento para escenas densas. **Ligera** la mantiene reducida y **Alta** prioriza la nitidez. Si aumenta el costo de dibujar, compara los modos o simplifica la malla de terreno. [MDN, buenas prácticas de WebGL](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices).

El visor admite hasta **15.000 collares**, **1.000.000 de tramos**, **50 columnas analíticas** y **300.000 vértices de topografía**. Esos son límites de importación. La escena incluida de 1.500 taladros es la referencia de prueba. Para proyectos muy extensos, divide por campaña o sector. El visor permite inspeccionar las trayectorias observadas. La continuidad mineralógica entre taladros requiere un modelo geológico aparte.

```bash
python -m unittest -v
python demo.py datos_demo
```

Los tests comprueban trayectoria, coordenadas, límites de intervalos, censuras, extensiones de Survey, atributos con soportes distintos y topografía CSV, OBJ, ASC y GeoTIFF. El caso GeoTIFF se ejecuta cuando Rasterio está disponible. El segundo comando regenera los CSV ficticios y el DEM de ejemplo en ASC.

