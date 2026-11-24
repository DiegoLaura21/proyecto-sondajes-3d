"use strict";

const Grafico = (() => {
  const VERT_TRAMOS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 inicio;
    layout(location=1) in vec3 final;
    layout(location=2) in vec3 color;
    uniform mat4 vista;
    uniform vec2 pantalla;
    uniform float grosor;
    uniform ivec2 seleccionado;
    out vec3 vColor;
    out float lado;
    const vec2 esquinas[6]=vec2[6](vec2(0,-1),vec2(1,-1),vec2(1,1),vec2(0,-1),vec2(1,1),vec2(0,1));
    void main(){
      vec4 a=vista*vec4(inicio,1), b=vista*vec4(final,1);
      float oa=a.z+a.w, ob=b.z+b.w;
      if(oa<0.0 && ob<0.0){gl_Position=vec4(2,2,2,1); vColor=color; lado=0.0; return;}
      if(oa<0.0) a=mix(a,b,oa/(oa-ob));
      if(ob<0.0) b=mix(b,a,ob/(ob-oa));
      vec2 delta=(b.xy/b.w-a.xy/a.w)*pantalla;
      vec2 normal=vec2(-delta.y,delta.x)/max(length(delta),0.01);
      vec2 e=esquinas[gl_VertexID];
      bool hi=gl_InstanceID>=seleccionado.x && gl_InstanceID<seleccionado.y;
      vec4 p=mix(a,b,e.x);
      p.xy+=normal*e.y*(grosor+(hi?1.7:0.0))*p.w/pantalla;
      gl_Position=p;
      vColor=hi?mix(color,vec3(1.,.79,.48),.62):color;
      lado=e.y;
    }`;
  const FRAG_TRAMOS = `#version 300 es
    precision mediump float;
    in vec3 vColor;
    in float lado;
    out vec4 frag;
    void main(){frag=vec4(vColor,1.-smoothstep(.67,1.,abs(lado)));}`;
  const VERT_SIMPLE = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 p;
    uniform mat4 vista;
    uniform float px;
    out vec3 pos;
    void main(){ pos=p; gl_Position=vista*vec4(p,1); gl_PointSize=px; }`;
  const FRAG_SIMPLE = `#version 300 es
    precision highp float;
    in vec3 pos;
    uniform int tipo;
    uniform vec4 color;
    out vec4 frag;
    void main(){
      if(tipo==2){
        float d=length(gl_PointCoord-vec2(.5));
        if(d>.5) discard;
        frag=vec4(mix(color.rgb,vec3(1.,.97,.85),smoothstep(.26,.40,d)*.6),1.-smoothstep(.39,.5,d));
      }else if(tipo==0){
        vec3 n=normalize(cross(dFdx(pos),dFdy(pos)));
        float l=.80+.25*abs(dot(n,normalize(vec3(-.45,-.35,1.0))));
        float t=pos.z/18.;
        float linea=1.-smoothstep(.03,.03+max(.015,fwidth(t)),abs(fract(t+.5)-.5));
        vec3 relieve=mix(color.rgb,vec3(.55,.76,.79),clamp(.40+pos.z/140.,0.,1.)*.42);
        frag=vec4(relieve*l+linea*.12,color.a+linea*.06);
      }else{frag=color;}
    }`;

  function programa(gl, vs, fs) {
    function compilar(tipo, codigo) {
      const shader = gl.createShader(tipo);
      gl.shaderSource(shader, codigo);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(shader));
      return shader;
    }
    const v = compilar(gl.VERTEX_SHADER, vs), f = compilar(gl.FRAGMENT_SHADER, fs);
    const p = gl.createProgram();
    gl.attachShader(p, v);
    gl.attachShader(p, f);
    gl.linkProgram(p);
    gl.deleteShader(v);
    gl.deleteShader(f);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(p));
    return p;
  }
  const pi = Math.PI;
  const sumar = (a, b) => a.map((x, i) => x + b[i]);
  const restar = (a, b) => a.map((x, i) => x - b[i]);
  const escala = (a, f) => a.map(x => x * f);
  const punto = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
  const modulo = a => Math.hypot(...a);
  const unidad = a => escala(a, 1 / Math.max(modulo(a), 1e-12));
  const cruz = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
  function matriz(a, b) {
    const r = new Float32Array(16);
    for (let j=0;j<4;j++) for (let i=0;i<4;i++) {
      r[j*4+i]=a[i]*b[j*4]+a[4+i]*b[j*4+1]+a[8+i]*b[j*4+2]+a[12+i]*b[j*4+3];
    }
    return r;
  }
  function mirar(eye, centro) {
    const z=unidad(restar(eye,centro)), x=unidad(cruz([0,0,1],z)), y=cruz(z,x);
    return {x, y, vista:[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,
      -punto(x,eye),-punto(y,eye),-punto(z,eye),1]};
  }

  const paleta = [[65,86,173],[69,183,177],[241,201,108],[237,120,91]];
  const colores = ["#65bdb9","#d7a163","#ad94d9","#e28480","#7ba4d7","#a1bd74",
    "#e8c6a5","#73bfd7","#a5aab1","#e597c0","#7aa084","#ccb780"];
  function categoria(indice) {
    if (indice < colores.length) return colores[indice];
    const h = (indice * 137.508) % 360;
    return `hsl(${h} 65% 67%)`;
  }
  function rgbCategoria(i) {
    const hex = categoria(i);
    if (hex[0] === "#") return [1,3,5].map(j=>parseInt(hex.slice(j,j+2),16));
    const h = i * 137.508 % 360 / 60;
    const c = (1 - Math.abs(2*.67-1)) * .65;
    const x = c*(1-Math.abs(h%2-1)), m = .67-c/2;
    const color = [[c,x,0],[x,c,0],[0,c,x],[0,x,c],[x,0,c],[c,0,x]][Math.floor(h)];
    return color.map(v=>Math.round((v+m)*255));
  }
  function gradiente(valor, min, max, salida, i) {
    const u=Math.max(0,Math.min(1,(valor-min)/(max-min)))*3;
    const j=Math.min(2,Math.floor(u)), fr=u-j;
    for(let d=0;d<3;d++) salida[i+d]=Math.round(paleta[j][d]*(1-fr)+paleta[j+1][d]*fr);
  }

  class Visor {
    constructor(canvas, alDibujar, alContexto) {
      this.canvas = canvas;
      this.alDibujar = alDibujar;
      this.alContexto = alContexto;
      this.gl = canvas.getContext("webgl2", {alpha:true, antialias:false, depth:true, stencil:false});
      if (!this.gl) throw Error("WebGL 2 no está disponible. Abre el visor en un navegador con aceleración gráfica.");
      this.modo = "auto";
      this.capa = "assay";
      this.analito = 0;
      this.atributo = 0;
      this.capas = {topografia:true, collares:true, grilla:true};
      this.opacidad = .30;
      this.seleccion = [-1,-1];
      this.pendiente = 0;
      this.moviendo = false;
      this.recursos = [];
      this.lista = null;
      this.configurar();
      new ResizeObserver(()=>this.pedir()).observe(canvas);
      canvas.addEventListener("webglcontextlost", e=>{
        e.preventDefault();
        this.perdido=true;
        this.alContexto(false);
      });
      canvas.addEventListener("webglcontextrestored", ()=>{
        this.perdido=false;
        this.recursos=[];
        this.configurar();
        if(this.lista){this.cargarGPU();this.pintar(this.capa,this.analito,this.atributo);}
        this.pedir();
        this.alContexto(true);
      });
    }
    configurar() {
      const gl = this.gl;
      this.inst = programa(gl, VERT_TRAMOS, FRAG_TRAMOS);
      this.base = programa(gl, VERT_SIMPLE, FRAG_SIMPLE);
      const ub=(p,nombres)=>Object.fromEntries(nombres.map(n=>[n,gl.getUniformLocation(p,n)]));
      this.uniBase=ub(this.base,["vista","tipo","color","px"]);
      this.uniTramos=ub(this.inst,["vista","pantalla","grosor","seleccionado"]);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.enable(gl.BLEND);
      gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
      gl.clearColor(0,0,0,0);
    }
    buffer(tipo, datos, uso) {
      const gl=this.gl, b=gl.createBuffer();
      this.recursos.push(["buffer",b]);
      gl.bindBuffer(tipo,b);
      gl.bufferData(tipo,datos,uso||gl.STATIC_DRAW);
      return b;
    }
    va() {
      const v=this.gl.createVertexArray();
      this.recursos.push(["vao",v]);
      this.gl.bindVertexArray(v);
      return v;
    }
    destruir() {
      if(!this.perdido) for(const [tipo, dato] of this.recursos) {
        if(tipo==="buffer") this.gl.deleteBuffer(dato); else this.gl.deleteVertexArray(dato);
      }
      this.recursos=[];
    }
    cargar(lista) {
      this.lista=lista;
      this.seleccion=[-1,-1];
      if(!this.perdido) this.cargarGPU();
      this.encuadrar();
    }
    cargarGPU() {
      const {gl, lista:{meta,datos}}=this;
      this.destruir();
      this.lineas=this.va();
      this.buffer(gl.ARRAY_BUFFER,datos.xyz);
      for(let i=0;i<2;i++){
        gl.enableVertexAttribArray(i);
        gl.vertexAttribPointer(i,3,gl.FLOAT,false,24,i*12);
        gl.vertexAttribDivisor(i,1);
      }
      this.colores=new Uint8Array(meta.tramos*3);
      this.bufferColores=this.buffer(gl.ARRAY_BUFFER,this.colores,gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(2);
      gl.vertexAttribPointer(2,3,gl.UNSIGNED_BYTE,true,3,0);
      gl.vertexAttribDivisor(2,1);
      const p=new Float32Array(meta.sondajes.length*3);
      for(let j=0;j<meta.sondajes.length;j++) for(let d=0;d<3;d++) p[j*3+d]=meta.sondajes[j][d+1]-meta.origen[d];
      this.puntos=this.malla(p);
      this.terreno=meta.triangulos?this.malla(datos.topo,datos.caras):null;
      this.suelo=this.malla(this.crearGrilla(meta));
      gl.bindVertexArray(null);
    }
    malla(p, caras=null){
      const gl=this.gl, va=this.va();
      this.buffer(gl.ARRAY_BUFFER,p);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0,3,gl.FLOAT,false,0,0);
      if(caras) this.buffer(gl.ELEMENT_ARRAY_BUFFER,caras);
      return {va,n:caras?caras.length:p.length/3,indexada:!!caras};
    }
    crearGrilla(meta){
      const span=Math.max(meta.max[0]-meta.min[0],meta.max[1]-meta.min[1],80);
      const paso=10**Math.floor(Math.log10(span/9));
      const salto=paso*Math.ceil(span/(15*paso));
      const xi=Math.floor((meta.min[0]-salto)/salto)*salto, xf=Math.ceil((meta.max[0]+salto)/salto)*salto;
      const yi=Math.floor((meta.min[1]-salto)/salto)*salto, yf=Math.ceil((meta.max[1]+salto)/salto)*salto;
      const z=meta.min[2]-.10*salto,p=[];
      for(let x=xi;x<=xf;x+=salto) p.push(x,yi,z,x,yf,z);
      for(let y=yi;y<=yf;y+=salto) p.push(xi,y,z,xf,y,z);
      return new Float32Array(p);
    }
    pintar(capa, analito, atributo=0) {
      this.capa=capa;
      this.analito=analito;
      this.atributo=atributo;
      if(!this.lista||this.perdido) return;
      const {meta,datos}=this.lista;
      const regla=meta.analitos[analito];
      const infoExtra=capa==="extra"?meta.atributos[atributo]:null;
      const categorias=infoExtra?.categorias ?? (capa==="lith"?meta.litologias:meta.alteraciones);
      const cats=categorias.map((_,i)=>rgbCategoria(i));
      const gris=[101,123,135], traza=[146,177,191];
      for(let i=0;i<meta.tramos;i++){
        const base=i*3;
        let c=gris;
        if(capa==="assay" && regla){
          const indice=datos.capas[base];
          const v=indice>=0?datos.ensayos[indice*meta.analitos.length+analito]:NaN;
          if(Number.isFinite(v)){gradiente(v,regla.min,regla.max,this.colores,base);continue;}
        }else if(infoExtra){
          const fila=datos.extra[i*meta.tablas_extra+infoExtra.tabla];
          const valor=fila>=0?datos.valores_extra[infoExtra.offset+fila]:NaN;
          if(Number.isFinite(valor)){
            if(infoExtra.tipo==="numerico"){
              gradiente(valor,infoExtra.min,infoExtra.max,this.colores,base);
              continue;
            }
            c=cats[valor]||gris;
          }
        }else if(capa==="lith" || capa==="alt"){
          c=cats[datos.capas[base+(capa==="lith"?1:2)]]||c;
        }else if(capa==="trace") c=traza;
        this.colores.set(c,base);
      }
      const gl=this.gl;
      gl.bindBuffer(gl.ARRAY_BUFFER,this.bufferColores);
      gl.bufferSubData(gl.ARRAY_BUFFER,0,this.colores);
      this.pedir();
    }
    encuadrar(){
      const {min,max}=this.lista.meta;
      this.centro=min.map((v,i)=>(v+max[i])/2);
      this.radio=Math.max(15,modulo(restar(max,min))/2);
      this.distancia=this.radio*2.55;
      this.vista("iso");
    }
    vista(v){
      const angulos={iso:[-120,28],planta:[-90,89.95],norte:[90,0.08],este:[0,0.08]};
      [this.az,this.el]=angulos[v].map(x=>x*pi/180);
      this.orto=v!=="iso";
      this.pedir();
    }
    acercar(delta){
      this.distancia=Math.min(this.radio*35,Math.max(this.radio*.035,this.distancia*Math.exp(delta)));
      this.pedir();
    }
    orbitar(dx,dy){
      this.az-=dx*.007;
      this.el=Math.max(-pi*.485,Math.min(pi*.4998,this.el+dy*.006));
      this.pedir();
    }
    paneo(dx,dy){
      const v=this.transformar();
      const f=2*this.distancia*Math.tan(.36)/Math.max(this.canvas.clientHeight,1);
      this.centro=sumar(this.centro,sumar(escala(v.x,-dx*f),escala(v.y,dy*f)));
      this.pedir();
    }
    enfocar(i){
      const h=this.lista.meta.sondajes[i], xyz=this.lista.datos.xyz;
      const primero=h[5]*6, ultimo=(h[5]+h[6]-1)*6+3;
      this.centro=[0,1,2].map(d=>(xyz[primero+d]+xyz[ultimo+d])/2);
      this.distancia=Math.max(45,h[4]*1.9);
      this.pedir();
    }
    transformar(){
      const h=this.distancia*Math.cos(this.el);
      const eye=sumar(this.centro,[h*Math.cos(this.az),h*Math.sin(this.az),this.distancia*Math.sin(this.el)]);
      const {x,y,vista}=mirar(eye,this.centro);
      const aspecto=Math.max(.1,this.canvas.clientWidth/Math.max(1,this.canvas.clientHeight));
      const near=Math.max(.04,this.radio*.0004,this.distancia*.005);
      const far=this.distancia+this.radio*12;
      const f=1/Math.tan(.36), a=this.distancia/f, b=a*aspecto;
      const proy=this.orto?[1/b,0,0,0,0,1/a,0,0,0,0,-2/(far-near),0,0,0,-(far+near)/(far-near),1]:
        [f/aspecto,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0];
      return {x,y,matriz:matriz(proy,vista), metrosPixel:2*a/Math.max(1,this.canvas.clientHeight)};
    }
    ratio(){
      const d=window.devicePixelRatio||1;
      if(this.modo==="ligera") return Math.min(d,.86);
      if(this.modo==="alta") return Math.min(d,1.65);
      return Math.min(d,this.moviendo && this.lista?.meta.tramos>35000 ? .89 : 1.35);
    }
    pedir(){
      if(!this.pendiente) this.pendiente=requestAnimationFrame(()=>{
        this.pendiente=0;
        if(!this.perdido && this.lista) this.dibujar();
      });
    }
    dibujar(){
      const {gl,canvas}=this;
      const r=this.ratio();
      const w=Math.max(1,Math.round(canvas.clientWidth*r)),h=Math.max(1,Math.round(canvas.clientHeight*r));
      if(w!==canvas.width||h!==canvas.height){canvas.width=w;canvas.height=h;}
      gl.viewport(0,0,w,h);
      gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      const t=this.transformar();
      this.transformacion=t;
      gl.useProgram(this.base);
      gl.uniformMatrix4fv(this.uniBase.vista,false,t.matriz);
      if(this.capas.grilla) this.simple(this.suelo,gl.LINES,1,[.42,.61,.67,.24],1);
      gl.useProgram(this.inst);
      gl.uniformMatrix4fv(this.uniTramos.vista,false,t.matriz);
      gl.uniform2f(this.uniTramos.pantalla,w,h);
      gl.uniform1f(this.uniTramos.grosor,(this.lista.meta.tramos>40000?1.9:3.0)*r);
      gl.uniform2iv(this.uniTramos.seleccionado,this.seleccion);
      gl.bindVertexArray(this.lineas);
      gl.drawArraysInstanced(gl.TRIANGLES,0,6,this.lista.meta.tramos);
      gl.useProgram(this.base);
      if(this.terreno && this.capas.topografia){
        gl.depthMask(false);
        this.simple(this.terreno,gl.TRIANGLES,0,[.29,.47,.52,this.opacidad],1);
        gl.depthMask(true);
      }
      if(this.capas.collares) this.simple(this.puntos,gl.POINTS,2,[.99,.83,.63,1],r*(this.lista.meta.tramos>40000?3.7:7));
      gl.bindVertexArray(null);
      this.alDibujar(t);
    }
    simple(malla, modo, tipo, color, px){
      const gl=this.gl;
      gl.bindVertexArray(malla.va);
      gl.uniform1i(this.uniBase.tipo,tipo);
      gl.uniform4fv(this.uniBase.color,color);
      gl.uniform1f(this.uniBase.px,px);
      if(malla.indexada)gl.drawElements(modo,malla.n,gl.UNSIGNED_INT,0);
      else gl.drawArrays(modo,0,malla.n);
    }
    pick(x,y) {
      if(!this.lista||!this.transformacion) return -1;
      const {matriz:m}=this.transformacion;
      const b=this.lista.datos.xyz,w=this.canvas.clientWidth/2,h=this.canvas.clientHeight/2;
      let mejor=-1, dist=64, profundidad=Infinity;
      for(let j=0;j<b.length;j+=6) {
        const ax=b[j],ay=b[j+1],az=b[j+2],bx=b[j+3],by=b[j+4],bz=b[j+5];
        const aw=m[3]*ax+m[7]*ay+m[11]*az+m[15],bw=m[3]*bx+m[7]*by+m[11]*bz+m[15];
        if(aw<=0||bw<=0)continue;
        const x0=w*(1+(m[0]*ax+m[4]*ay+m[8]*az+m[12])/aw);
        const x1=w*(1+(m[0]*bx+m[4]*by+m[8]*bz+m[12])/bw);
        if(x<Math.min(x0,x1)-8||x>Math.max(x0,x1)+8)continue;
        const y0=h*(1-(m[1]*ax+m[5]*ay+m[9]*az+m[13])/aw);
        const y1=h*(1-(m[1]*bx+m[5]*by+m[9]*bz+m[13])/bw);
        if(y<Math.min(y0,y1)-8||y>Math.max(y0,y1)+8)continue;
        const dx=x1-x0,dy=y1-y0;
        const t=Math.min(1,Math.max(0,((x-x0)*dx+(y-y0)*dy)/Math.max(.00001,dx*dx+dy*dy)));
        const d=(x-x0-t*dx)**2+(y-y0-t*dy)**2;
        const z=((1-t)*(m[2]*ax+m[6]*ay+m[10]*az+m[14])/aw+t*(m[2]*bx+m[6]*by+m[10]*bz+m[14])/bw);
        if(z>=-1 && z<=1 && (d<dist-.5 || (d<=dist+.5 && z<profundidad)) && d<=64){
          dist=d;mejor=j/6;profundidad=z;
        }
      }
      return mejor;
    }
  }
  return {Visor,categoria};
})();

