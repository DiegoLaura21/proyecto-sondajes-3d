"use strict";

const $ = id => document.getElementById(id);
const num = new Intl.NumberFormat("es-PE", {maximumFractionDigits:2});
const leyNum = new Intl.NumberFormat("es-PE", {maximumSignificantDigits:5});
const proyectos = new Map();
const svgNS = "http://www.w3.org/2000/svg";
let motor, proyectoActual = "", sondajeActual = -1, tramoActual = -1;
let modo = "assay", peticion = 0, activo = null, medir = null, ultimoCompas = 0;
let numeroProyecto = 0;

function nodo(etiqueta, clase, texto) {
  const e = document.createElement(etiqueta);
  if (clase) e.className = clase;
  if (texto !== undefined) e.textContent = texto;
  return e;
}

function mostrarMensaje(texto) {
  const e = $("mensaje");
  e.textContent = texto;
  e.hidden = !texto;
}

function estado(texto, tipo = "lito") {
  $("estado").replaceChildren(nodo("i", "punto " + tipo), document.createTextNode(texto));
}

function desempaquetar(buffer) {
  const inicio = new Uint8Array(buffer, 0, 4);
  if (new TextDecoder().decode(inicio) !== "TS3D") throw Error("El visualizador recibió una escena inválida.");
  const largo = new DataView(buffer).getUint32(4, true);
  const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 8, largo)));
  const datos = {};
  let offset = 8 + Math.ceil(largo / 4) * 4;
  const tipos = {f:Float32Array,i:Int32Array,I:Uint32Array};
  for (const [k, n, t] of meta.buffers) {
    datos[k] = new tipos[t](buffer, offset, n);
    offset += n * 4;
  }
  if(offset !== buffer.byteLength) throw Error("El tamaño de la escena no coincide con su cabecera.");
  return {meta, datos};
}

async function recibir(url, opciones) {
  const respuesta = await fetch(url, opciones);
  if (!respuesta.ok) {
    let mensaje = "No se pudo cargar la escena.";
    try { mensaje = (await respuesta.json()).error || mensaje; } catch {}
    throw Error(mensaje);
  }
  return desempaquetar(await respuesta.arrayBuffer());
}

function opcionesSelect(e, valores) {
  e.replaceChildren(...valores.map(([value, texto])=>new Option(texto, value)));
}

function prepararInterfaz(escena, clave) {
  const {meta} = escena;
  proyectoActual = clave;
  $("proyectos").value = clave;
  $("titulo-escena").textContent = meta.nombre;
  $("origen-escena").textContent = clave === "demo" ? "Caso sintético" : clave === "carga" ? "Prueba de carga" : "Proyecto importado";
  $("n-taladros").textContent = num.format(meta.sondajes.length);
  $("n-metros").textContent = num.format(meta.metros);
  $("n-tramos").textContent = num.format(meta.tramos);
  const topo=meta.topografia;
  const reduccion=topo.malla && topo.malla.some((v,i)=>v!==topo.original[i]);
  const dimensiones=reduccion ? " · malla " + topo.malla.join(" × ") : "";
  $("metricas").textContent = topo.formato
    ? "WebGL 2 · " + topo.formato + dimensiones + " · " + num.format(meta.triangulos) + " triángulos"
    : "WebGL 2 · sin topografía";
  $("advertencias").hidden = !meta.total_advertencias;
  $("advertencias").textContent = num.format(meta.total_advertencias) + " advertencias";
  $("lista-advertencias").replaceChildren(...meta.advertencias.map(t=>nodo("li", "", t)));
  if(meta.total_advertencias > meta.advertencias.length) {
    $("lista-advertencias").append(nodo("li","","Se muestran las primeras " + meta.advertencias.length + " advertencias."));
  }
  // Evita crear miles de nodos de sugerencias en las escenas grandes. Se pueden buscar todos los ID.
  opcionesSelect($("lista-taladros"), meta.sondajes.slice(0, 120).map(h=>[h[0],h[0]]));
  opcionesSelect($("analitos"), meta.analitos.map((a,i)=>[i,a.nombre]));
  opcionesSelect($("atributos"), meta.atributos.map((a,i)=>[i,a.nombre]));
  $("buscar-id").value = "";
  $("busqueda-error").hidden = true;
  $("topografia").disabled = !meta.triangulos;
  $("topografia").checked = !!meta.triangulos;
  motor.capas.topografia = !!meta.triangulos;
  $("fila-opacidad").hidden = !meta.triangulos;
  $("resultado-medicion").textContent = "";
  $("guardar").disabled = clave === "carga";
  $("medir").disabled = false;
  for (const boton of $("capas").querySelectorAll("[data-capa]")) {
    const key=boton.dataset.capa;
    boton.disabled=(key==="lith"&&!meta.litologias.length)||(key==="alt"&&!meta.alteraciones.length)
      ||(key==="extra"&&!meta.atributos.length)
      ||(key==="assay"&&!meta.analitos.length);
  }
  ocultarDetalle();
  motor.cargar(escena);
  vistaActiva("iso");
  capa(meta.analitos.length ? "assay" : "trace");
  mostrarMensaje("");
  estado("Escena lista");
}

async function cargar(clave, origen = null) {
  if(!motor) return;
  const numero = ++peticion;
  if (activo) activo.abort();
  detenerMedicion(false);
  activo = new AbortController();
  mostrarMensaje("Validando datos y preparando la escena…");
  estado("Procesando geometría", "ensayo");
  $("medir").disabled=true;
  const proyecto = origen || proyectos.get(clave);
  try {
    const opciones = proyecto ? {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(proyecto),
      signal:activo.signal,
    } : {signal:activo.signal};
    const escena=await recibir(proyecto ? "/api/importar" : "/api/ejemplo/"+clave, opciones);
    if(numero!==peticion) return false;
    if(origen) {
      proyectos.set(clave, origen);
      $("proyectos").add(new Option(escena.meta.nombre, clave));
    }
    prepararInterfaz(escena, clave);
    return true;
  } catch(error) {
    if(numero!==peticion || error.name==="AbortError") return false;
    $("proyectos").value=proyectoActual || "demo";
    $("medir").disabled=!proyectoActual;
    mostrarMensaje(proyectoActual || $("dialogo").open ? "" : error.message);
    estado(proyectoActual ? "Escena anterior conservada" : "Escena no disponible", "ensayo");
    throw error;
  }
}

function capa(nueva) {
  if(!motor?.lista)return;
  modo=nueva;
  for(const b of $("capas").querySelectorAll("[data-capa]")) b.setAttribute("aria-pressed", String(b.dataset.capa===modo));
  $("fila-analito").hidden = modo!=="assay";
  $("fila-atributo").hidden = modo!=="extra";
  motor.pintar(modo, Number($("analitos").value), Number($("atributos").value));
  leyenda();
  if(sondajeActual>=0)detalle(sondajeActual,tramoActual,false);
}

function leyenda() {
  const e=$("leyenda"), {meta}=motor.lista;
  const extra=modo==="extra"?meta.atributos[Number($("atributos").value)]:null;
  e.replaceChildren();
  if(modo==="assay" || extra?.tipo==="numerico"){
    const info=extra || meta.analitos[Number($("analitos").value)];
    e.append(nodo("strong","",info.nombre),nodo("div","rampa"));
    const extremos=nodo("div","rango");
    extremos.append(nodo("span","",leyNum.format(info.min)),nodo("span","",leyNum.format(info.max)));
    e.append(extremos,nodo("span","nota-leyenda",info.n ? "P5–P95 · gris sin valor cuantificado" : "Sin valores cuantificados"));
  }else if(modo==="trace"){
    e.append(nodo("strong","","Trayectoria"),nodo("span","nota-leyenda","Curvatura mínima · profundidad medida"));
  }else{
    e.append(nodo("strong","",extra?.nombre || (modo==="lith"?"Litología":"Alteración")));
    const ul=nodo("ul");
    const cats=extra?.categorias || (modo==="lith"?meta.litologias:meta.alteraciones);
    for(const [i,nombre] of cats.entries()){
      const item=nodo("li"), punto=nodo("i");
      punto.style.backgroundColor=Grafico.categoria(i);
      item.append(punto,document.createTextNode(nombre));
      ul.append(item);
    }
    e.append(ul,nodo("span","nota-leyenda","Gris · sin clasificación"));
  }
}

function vistaActiva(v) {
  for (const b of $("vistas").querySelectorAll("[data-vista]")) b.setAttribute("aria-pressed",String(b.dataset.vista===v));
}

function ocultarDetalle() {
  tramoActual=-1;
  sondajeActual=-1;
  $("inspector").hidden=true;
  if(motor){motor.seleccion=[-1,-1];motor.pedir();}
}

function textoAtributo(info, i, segmento, meta, datos) {
  const fila=datos.extra[segmento*meta.tablas_extra+info.tabla];
  if(fila<0)return "Sin dato";
  const valor=datos.valores_extra[info.offset+fila];
  if(!Number.isFinite(valor))return meta.calificadores_extra[i+":"+fila]||"Sin dato";
  return info.tipo==="categorico" ? info.categorias[valor] : leyNum.format(valor);
}

function detalle(i, segmento, seleccionar=true) {
  const {meta, datos}=motor.lista;
  const h=meta.sondajes[i];
  const fila=h[5];
  sondajeActual=i;
  tramoActual=segmento;
  if(seleccionar){motor.seleccion=[fila,fila+h[6]];motor.pedir();}
  $("inspector").hidden=false;
  $("detalle-id").textContent=h[0];
  const props=[
    ["Este collar",num.format(h[1])+" m"],["Norte collar",num.format(h[2])+" m"],
    ["Cota collar",num.format(h[3])+" m"],["EOH",num.format(h[4])+" m"],
  ];
  const adicionales=[];
  if(segmento>=0){
    const p=segmento*3;
    const analito=Number($("analitos").value);
    const ensayo=datos.capas[p], li=datos.capas[p+1], al=datos.capas[p+2];
    const nombre=meta.analitos[analito]?.nombre;
    const valor=ensayo>=0?datos.ensayos[ensayo*meta.analitos.length+analito]:NaN;
    const texto=Number.isFinite(valor)?leyNum.format(valor):meta.calificadores[ensayo+":"+analito]||"Sin dato";
    const cota=(datos.xyz[segmento*6+2]+datos.xyz[segmento*6+5])/2+meta.origen[2];
    props.push(["MD del tramo",num.format(datos.md[segmento*2])+"–"+num.format(datos.md[segmento*2+1])+" m"],
      ["Cota media",num.format(cota)+" m"],["Litología",meta.litologias[li]||"Sin dato"],
      ["Alteración",meta.alteraciones[al]||"Sin dato"]);
    if(nombre) props.push([nombre,texto]);
    for(const [j,info] of meta.atributos.entries()){
      const dato=[info.nombre,textoAtributo(info,j,segmento,meta,datos)];
      if(modo==="extra" && Number($("atributos").value)===j) props.push(dato);
      else adicionales.push(dato);
    }
  }
  $("detalle").replaceChildren(...props.flatMap(([k,v])=>[nodo("dt","",k),nodo("dd","",v)]));
  $("otros-atributos").hidden=!adicionales.length;
  $("detalle-atributos").replaceChildren(...adicionales.flatMap(([k,v])=>[nodo("dt","",k),nodo("dd","",v)]));
}

function seleccionarTramo(segmento) {
  if(segmento<0){ocultarDetalle();return;}
  const sondajes=motor.lista.meta.sondajes;
  let inf=0,sup=sondajes.length-1;
  while(inf<sup) {
    const j=Math.ceil((inf+sup)/2);
    if(sondajes[j][5]<=segmento)inf=j;
    else sup=j-1;
  }
  detalle(inf,segmento);
}

function orientar(t) {
  const ahora=performance.now();
  if(ahora-ultimoCompas<75) return;
  ultimoCompas=ahora;
  const svg=$("brujula");
  const items=[["E","#e9ad6e"],["N","#70c1b8"],["Z","#a2b7e4"]].map(([nombre,color],i)=>[nombre,color,t.x[i],t.y[i]]);
  svg.replaceChildren();
  for(const [nombre,color,x,y] of items){
    if(Math.hypot(x,y)<.14)continue;
    const linea=document.createElementNS(svgNS,"line"), texto=document.createElementNS(svgNS,"text");
    linea.setAttribute("x1",42);linea.setAttribute("y1",36);
    linea.setAttribute("x2",42+24*x);linea.setAttribute("y2",36-24*y);
    linea.setAttribute("stroke",color);linea.setAttribute("stroke-width","1.7");
    texto.setAttribute("x",39+32*x);texto.setAttribute("y",40-32*y);
    texto.setAttribute("fill",color);texto.setAttribute("font-size","10");
    texto.textContent=nombre;
    svg.append(linea,texto);
  }
  const meta = Math.max(.001,t.metrosPixel*85);
  const p=10**Math.floor(Math.log10(meta));
  const escala=meta/p>=5?5*p:meta/p>=2?2*p:p;
  $("escala-valor").textContent = escala>=1000?num.format(escala/1000)+" km":leyNum.format(escala)+" m";
  $("escala-linea").style.width=Math.round(escala/t.metrosPixel)+"px";
}

function alDibujar(t) {
  orientar(t);
  if(medir) medir.fotogramas.push(performance.now());
}

function alContexto(recuperado) {
  if(!recuperado) detenerMedicion(false);
  mostrarMensaje(recuperado?"":"La GPU interrumpió la escena. El visor intentará recuperarla.");
  estado(recuperado?"Escena recuperada":"Contexto gráfico interrumpido", recuperado?"lito":"ensayo");
}

function detenerMedicion(informar) {
  if(!medir) return;
  const {fotogramas,solicitud}=medir;
  medir=null;
  cancelAnimationFrame(solicitud);
  motor.moviendo=false;
  motor.pedir();
  $("medir").disabled=false;
  if(!informar){$("resultado-medicion").textContent="";return;}
  const valores=fotogramas.slice(1).map((v,i)=>v-fotogramas[i]).slice(4);
  if(valores.length<4){$("resultado-medicion").textContent="Muestra insuficiente. Mantén esta pestaña visible.";return;}
  valores.sort((a,b)=>a-b);
  const med=valores[Math.floor(valores.length/2)], p95=valores[Math.ceil(.95*valores.length)-1];
  $("resultado-medicion").textContent=num.format(1000/med)+" FPS mediana · p95 "+num.format(p95)+" ms por cuadro.";
}

function iniciarMedicion() {
  if(!motor?.lista || medir)return;
  $("medir").disabled=true;
  $("resultado-medicion").textContent="Midiendo tres segundos en órbita…";
  motor.moviendo=true;
  vistaActiva(null);
  const inicio=performance.now();
  medir={fotogramas:[],solicitud:0};
  function avanzar(ahora){
    if(!medir)return;
    if(ahora-inicio>=3200){detenerMedicion(true);return;}
    motor.orbitar(2.5,0);
    medir.solicitud=requestAnimationFrame(avanzar);
  }
  medir.solicitud=requestAnimationFrame(avanzar);
}

try {
  motor = new Grafico.Visor($("lienzo"),alDibujar,alContexto);
} catch(error) {
  mostrarMensaje(error.message);
  estado("WebGL 2 no disponible","ensayo");
  $("importar").disabled=true;
  $("proyectos").disabled=true;
}

$("proyectos").addEventListener("change",async e=>{
  try{await cargar(e.target.value);}catch(error){mostrarMensaje(error.message);}
});
$("capas").addEventListener("click",e=>{
  const b=e.target.closest("[data-capa]");
  if(b&&!b.disabled)capa(b.dataset.capa);
});
$("analitos").addEventListener("change",()=>capa("assay"));
$("atributos").addEventListener("change",()=>capa("extra"));
for(const id of ["topografia","collares","grilla"]){
  $(id).addEventListener("change",e=>{if(motor){motor.capas[id]=e.target.checked;motor.pedir();}});
}
$("opacidad").addEventListener("input",e=>{
  $("valor-opacidad").textContent=e.target.value+"%";
  if(motor){motor.opacidad=Number(e.target.value)/100;motor.pedir();}
});
$("calidad").addEventListener("change",e=>{if(motor){motor.modo=e.target.value;motor.pedir();}});
$("vistas").addEventListener("click",e=>{
  if(!motor?.lista)return;
  const b=e.target.closest("[data-vista]");
  if(b){motor.vista(b.dataset.vista);vistaActiva(b.dataset.vista);}
});
$("encuadrar").addEventListener("click",()=>{if(motor?.lista){motor.encuadrar();vistaActiva("iso");}});
$("enfocar").addEventListener("click",()=>{if(sondajeActual>=0)motor.enfocar(sondajeActual);});
$("cerrar-detalle").addEventListener("click",ocultarDetalle);
$("medir").addEventListener("click",iniciarMedicion);
$("buscar").addEventListener("submit",e=>{
  e.preventDefault();
  if(!motor?.lista)return;
  const clave=$("buscar-id").value.trim().toUpperCase();
  if(!clave)return;
  const s=motor.lista.meta.sondajes;
  let i=s.findIndex(h=>h[0].toUpperCase()===clave);
  if(i<0)i=s.findIndex(h=>h[0].toUpperCase().includes(clave));
  const aviso=$("busqueda-error");
  aviso.hidden=i>=0;
  if(i<0){aviso.textContent="No se encontró ese ID.";return;}
  detalle(i,-1);
  motor.enfocar(i);
});

const canvas=$("lienzo");
let arrastre=null;
canvas.addEventListener("pointerdown",e=>{
  if(!motor?.lista || !e.isPrimary || ![0,1,2].includes(e.button))return;
  detenerMedicion(false);
  canvas.setPointerCapture(e.pointerId);
  arrastre={x:e.clientX,y:e.clientY,origenX:e.clientX,origenY:e.clientY,pan:e.shiftKey||e.button!==0};
  motor.moviendo=true;
});
canvas.addEventListener("pointermove",e=>{
  if(!arrastre || !e.isPrimary)return;
  const dx=e.clientX-arrastre.x,dy=e.clientY-arrastre.y;
  if(!dx&&!dy)return;
  if(arrastre.pan||e.shiftKey)motor.paneo(dx,dy);
  else {motor.orbitar(dx,dy);vistaActiva(null);}
  arrastre.x=e.clientX;arrastre.y=e.clientY;
});
function soltar(e) {
  if(!arrastre || !e.isPrimary)return;
  if(e.type==="pointerup" && !arrastre.pan && Math.hypot(arrastre.origenX-e.clientX,arrastre.origenY-e.clientY)<4){
    const r=canvas.getBoundingClientRect();
    seleccionarTramo(motor.pick(e.clientX-r.left,e.clientY-r.top));
  }
  arrastre=null;
  motor.moviendo=false;
  motor.pedir();
}
canvas.addEventListener("pointerup",soltar);
canvas.addEventListener("pointercancel",soltar);
canvas.addEventListener("lostpointercapture",soltar);
canvas.addEventListener("wheel",e=>{
  if(!motor?.lista)return;
  e.preventDefault();
  motor.acercar(Math.max(-.55,Math.min(.55,e.deltaY*(e.deltaMode===1?.025:.0014))));
},{passive:false});
canvas.addEventListener("contextmenu",e=>e.preventDefault());
canvas.addEventListener("keydown",e=>{
  if(!motor?.lista)return;
  const flechas={ArrowLeft:[-19,0],ArrowRight:[19,0],ArrowUp:[0,-19],ArrowDown:[0,19]};
  if(flechas[e.key]){e.preventDefault();e.shiftKey?motor.paneo(...flechas[e.key]):motor.orbitar(...flechas[e.key]);vistaActiva(null);}
  else if(e.key==="+"||e.key==="="||e.key==="-"){e.preventDefault();motor.acercar(e.key==="-"?.16:-.16);}
  else if(e.key==="Escape")ocultarDetalle();
});

function descargar(texto, nombre) {
  const url=URL.createObjectURL(new Blob([texto],{type:"application/json;charset=utf-8"}));
  const a=nodo("a");
  a.href=url;a.download=nombre;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function ejemploJSON() {
  const r=await fetch("/api/plantilla");
  if(!r.ok)throw Error("No se pudo descargar el ejemplo.");
  return r.text();
}

function leerBase64(archivo) {
  return new Promise((resolver,rechazar)=>{
    const lector=new FileReader();
    lector.onload=()=>resolver(lector.result.slice(lector.result.indexOf(",")+1));
    lector.onerror=()=>rechazar(Error("No se pudo leer el archivo GeoTIFF."));
    lector.readAsDataURL(archivo);
  });
}

$("importar").addEventListener("click",()=>{
  $("error-importar").hidden=true;
  $("dialogo").showModal();
});
$("cerrar-importar").addEventListener("click",()=>$("dialogo").close());
$("cerrar-advertencias").addEventListener("click",()=>$("dialogo-advertencias").close());
$("advertencias").addEventListener("click",()=>$("dialogo-advertencias").showModal());
$("plantilla").addEventListener("click",async()=>{
  try{descargar(await ejemploJSON(),"alto_horizonte_ejemplo.json");}
  catch(error){$("error-importar").textContent=error.message;$("error-importar").hidden=false;}
});
$("guardar").addEventListener("click",async()=>{
  try{
    const p=proyectos.get(proyectoActual);
    const nombre=p?motor.lista.meta.nombre.replace(/[^\p{L}\d_-]+/gu,"_"):"alto_horizonte_ejemplo";
    descargar(p?JSON.stringify(p):await ejemploJSON(),nombre+".json");
  }catch(error){mostrarMensaje(error.message);}
});
$("form-importar").addEventListener("submit",async e=>{
  e.preventDefault();
  const salida=$("error-importar"),boton=$("procesar");
  boton.disabled=true;
  salida.hidden=true;
  const paquete=$("paquete").files[0];
  try{
    let p;
    if(paquete){
      if(paquete.size>160*1024*1024)throw Error("El archivo de proyecto supera 160 MiB.");
      p=JSON.parse(await paquete.text());
    }else{
      const nombre=$("nombre").value.trim();
      if(!nombre)throw Error("Escribe el nombre del proyecto.");
      const archivos={};
      let tamano=0,formato_topo="csv";
      function contar(f){
        tamano+=f.size;
        if(tamano>100*1024*1024)throw Error("Los archivos de proyecto superan 100 MiB.");
      }
      for(const input of $("form-importar").querySelectorAll("[data-archivo]")){
        const f=input.files[0], k=input.dataset.archivo;
        if(!f)continue;
        contar(f);
        if(k==="topo"){
          const extension=f.name.split(".").pop().toLowerCase();
          formato_topo={tif:"geotiff",tiff:"geotiff",asc:"asc",obj:"obj"}[extension]||"csv";
        }
        archivos[k]=k==="topo" && formato_topo==="geotiff" ? await leerBase64(f) : await f.text();
      }
      archivos.atributos=[];
      const tablas=$("archivos-atributos").files;
      if(tablas.length>12)throw Error("Puedes adjuntar hasta 12 tablas CSV de atributos.");
      for(const f of tablas){
        contar(f);
        archivos.atributos.push({nombre:f.name,contenido:await f.text()});
      }
      if(!archivos.collar || !archivos.survey || !archivos.assay)throw Error("Adjunta Collar, Survey y Assay.");
      p={nombre, archivos, formato_topo};
    }
    if(!p || typeof p!=="object" || Array.isArray(p))throw Error("El JSON no contiene un proyecto válido.");
    if(await cargar("proyecto-"+(++numeroProyecto),p)){
      $("dialogo").close();
      $("form-importar").reset();
    }
  } catch(error) {
    salida.textContent=error instanceof SyntaxError?"El archivo JSON no es válido.":error.message;
    salida.hidden=false;
  } finally {boton.disabled=false;}
});

if(motor)cargar("demo").catch(error=>mostrarMensaje(error.message));

