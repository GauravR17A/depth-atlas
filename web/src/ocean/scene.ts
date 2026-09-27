import { longitudeLabel } from '../geography';
import * as T from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { isoMesh, palettes, projection, sliceMesh, cutawayFaces, cutawayPlanes, offset, type Paint, type Point, type ViewMode, type Surface } from './grid';
import { transitionValue } from './motion';
import type { ScalarDisplayGrid as Subset } from './grid';

export type SceneOptions = {
  data: Subset; east?: Subset; north?: Subset; mode: ViewMode; paint: Paint;
  depthIndex: number; sectionIndex: number; iso: number; exaggeration: number;
  quality: 'auto' | 'balanced'; probe: Point; cutaway: boolean; reducedMotion: boolean; active: boolean; pickEnabled: boolean;
  observations?:{id:string;label:string;position:Point}[];onInstrument?:(id:string)=>void;
};
export type SceneStats = { kind: string; vertices: number; samples: number; drawMs: number; pixelRatio: number };
const vertexShader = `out vec3 worldPoint; void main(){ worldPoint=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`;
const paletteShader = `
uniform vec3 colors[6]; uniform int colorCount; uniform float low; uniform float high; uniform bool logarithmic;
float normalizeValue(float v){ return clamp(logarithmic ? (log(v)-log(low))/(log(high)-log(low)) : (v-low)/(high-low),0.0,1.0); }
vec3 paint(float v){ float f=normalizeValue(v)*float(colorCount-1); int i=min(colorCount-2,int(floor(f))); return mix(colors[i],colors[i+1],f-float(i)); }
`;
function paintUniforms(p: Paint) {
  const stops = palettes[p.palette].map(hex => new T.Vector3(...([1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255) as Point)));
  return { colors: { value: [...stops, ...Array(6-stops.length).fill(stops.at(-1))] }, colorCount: { value: stops.length }, low: { value: p.min }, high: { value: p.max }, logarithmic: { value: p.log }, opacity: { value: p.opacity } };
}
function volume(g: Subset, exaggeration: number, p: Paint, steps: number,cutaway:boolean) {
  const project = projection(g, exaggeration);
  const xs = g.longitude.map(lon=>project.point(lon,g.latitude[0],0)[0]);
  const ys = g.latitude.map(lat=>-project.point(g.longitude[0],lat,0)[2]);
  const zs = g.depth_m.map(depth=>-project.point(g.longitude[0],g.latitude[0],depth)[1]);
  const texture = new T.Data3DTexture(new Float32Array(g.values.map(v=>v??-1e20)),xs.length,ys.length,zs.length);
  texture.format=T.RedFormat; texture.type=T.FloatType; texture.needsUpdate=true;
  const boundsMin=new T.Vector3(xs[0],-zs.at(-1)!,-ys.at(-1)!), boundsMax=new T.Vector3(xs.at(-1)!, -zs[0], -ys[0]);
  const size=boundsMax.clone().sub(boundsMin), center=boundsMin.clone().add(boundsMax).multiplyScalar(.5);
  const axis = (name:string,n:number) => `uniform float ${name}[${n}]; vec2 find${name}(float q){int a=0; int b=${n-1}; for(int i=0;i<6;i++){ if(b-a<=1)break;int m=(a+b)/2;if(${name}[m]<=q)a=m;else b=m;}return vec2(float(a),clamp((q-${name}[a])/(${name}[a+1]-${name}[a]),0.0,1.0));}`;
  const fragmentShader=`
precision highp sampler3D;
in vec3 worldPoint; out vec4 outColor;
uniform sampler3D field; uniform int sampleCount; uniform vec3 boxMin; uniform vec3 boxMax; uniform float opacity; uniform bool cutOpen; uniform vec2 cutAt; uniform float cutY;
${paletteShader}
${axis('xs',xs.length)} ${axis('ys',ys.length)} ${axis('zs',zs.length)}
float sampleField(vec3 point){
 vec2 x=findxs(point.x), y=findys(-point.z), z=findzs(-point.y); float value=0.0;
 for(int k=0;k<2;k++)for(int j=0;j<2;j++)for(int i=0;i<2;i++){
  float w=(i==0?1.0-x.y:x.y)*(j==0?1.0-y.y:y.y)*(k==0?1.0-z.y:z.y);
  if(w<1e-7)continue; float v=texelFetch(field,ivec3(int(x.x)+i,int(y.x)+j,int(z.x)+k),0).r;
  if(v< -1e19)return -1e20; value+=v*w;
 } return value;
}
void main(){
 vec3 ray=normalize(worldPoint-cameraPosition); vec3 safeRay=vec3(abs(ray.x)<1e-7?1e-7:ray.x,abs(ray.y)<1e-7?1e-7:ray.y,abs(ray.z)<1e-7?1e-7:ray.z);
 vec3 a=(boxMin-cameraPosition)/safeRay,b=(boxMax-cameraPosition)/safeRay;
 vec3 nearT=min(a,b),farT=max(a,b); float start=max(0.0,max(nearT.x,max(nearT.y,nearT.z))),finish=min(farT.x,min(farT.y,farT.z));
 if(finish<=start)discard; float dt=(finish-start)/float(sampleCount); vec4 total=vec4(0.0);
 for(int i=0;i<${steps};i++){
  if(i>=sampleCount)break;
  vec3 pos=cameraPosition+ray*(start+(float(i)+0.5)*dt);
  if(cutOpen&&pos.x>cutAt.x&&pos.z>cutAt.y&&pos.y>cutY)continue;
  float v=sampleField(pos);
  if(v< -1e19 || (logarithmic&&v<=0.0))continue;
  float alpha=1.0-exp(-opacity*dt*0.8);
  float light=0.92+0.08*(pos.y-boxMin.y)/(boxMax.y-boxMin.y);
  total.rgb+=(1.0-total.a)*alpha*paint(v)*light; total.a+=(1.0-total.a)*alpha;
  if(total.a>0.985)break;
 }
 if(total.a<0.002)discard; outColor=vec4(total.rgb/max(total.a,1e-6),total.a);
}`;
  const geometry=new T.BoxGeometry(size.x,size.y,size.z);geometry.translate(center.x,center.y,center.z);
  const cut=cutawayPlanes(g,exaggeration);
  const material=new T.ShaderMaterial({glslVersion:T.GLSL3,vertexShader,fragmentShader,uniforms:{...paintUniforms(p),field:{value:texture},sampleCount:{value:steps},xs:{value:xs},ys:{value:ys},zs:{value:zs},boxMin:{value:boundsMin},boxMax:{value:boundsMax},cutOpen:{value:cutaway},cutY:{value:cutaway?boundsMin.y:boundsMax.y},cutAt:{value:new T.Vector2(cut.worldX,cut.worldZ)}},side:T.BackSide,transparent:true,depthWrite:false});
  const mesh=new T.Mesh(geometry,material);mesh.renderOrder=2;
  return {mesh,texture};
}
function surface(shape:Surface,p:Paint,lit:boolean) {
  const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(shape.positions,3));geometry.setAttribute('scalar',new T.Float32BufferAttribute(shape.scalars,1));geometry.computeVertexNormals();
  const material=new T.ShaderMaterial({glslVersion:T.GLSL3,uniforms:{...paintUniforms(p),revealEnabled:{value:false},revealY:{value:0}},side:T.DoubleSide,transparent:p.opacity<1,depthWrite:p.opacity>=1,
    vertexShader:`attribute float scalar; out float value; out vec3 normalView; out float worldY; void main(){worldY=position.y;value=scalar;normalView=normalize(normalMatrix*normal);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader:`in float value; in vec3 normalView; in float worldY; uniform bool revealEnabled; uniform float revealY; out vec4 outColor; uniform float opacity;${paletteShader}void main(){if(revealEnabled&&worldY<revealY)discard;if(logarithmic&&value<=0.0)discard;float shade=${lit?'0.62+0.38*abs(dot(normalize(normalView),normalize(vec3(.4,.6,1.0))))':'1.0'};outColor=vec4(paint(value)*shade,opacity);}`,
  });
  return new T.Mesh(geometry,material);
}
function missingSurface(shape:Surface){
  const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(shape.positions,3));
  const material=new T.ShaderMaterial({side:T.DoubleSide,transparent:true,depthWrite:false,uniforms:{revealEnabled:{value:false},revealY:{value:0}},
    vertexShader:'varying float worldY; void main(){worldY=position.y;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader:'varying float worldY; uniform bool revealEnabled; uniform float revealY; void main(){if(revealEnabled&&worldY<revealY)discard;float stripe=step(1.4,mod(gl_FragCoord.x+gl_FragCoord.y,11.0));gl_FragColor=vec4(mix(vec3(.39,.47,.51),vec3(.10,.16,.20),stripe),.85);}'
  });
  const mesh=new T.Mesh(geometry,material);mesh.renderOrder=3;return mesh;
}
function label(text:string,position:Point,size=.48) {
  const canvas=document.createElement('canvas');canvas.width=512;canvas.height=80;
  const ctx=canvas.getContext('2d')!;ctx.font='500 30px sans-serif';ctx.fillStyle='#aac5d0';ctx.textAlign='center';ctx.fillText(text,256,48);
  const texture=new T.CanvasTexture(canvas), material=new T.SpriteMaterial({map:texture,transparent:true,depthTest:false});
  const sprite=new T.Sprite(material);sprite.position.set(...position);sprite.scale.set(size*6.4,size,1);sprite.userData.texture=texture;return sprite;
}
export class OceanScene {
  readonly renderer:T.WebGLRenderer;
  readonly camera=new T.PerspectiveCamera(37,1,.05,200);
  readonly scene=new T.Scene();
  readonly controls:OrbitControls;
  private content=new T.Group(); private observer:ResizeObserver; private raf=0; private dirty=true; private disposed=false;
  private options?:SceneOptions; private textures:T.Texture[]=[]; private geometry?:T.Object3D; private drag?:[number,number]; private badFrames=0;
  private cutVolume?:T.Mesh<T.BoxGeometry,T.ShaderMaterial>; private cutFaces?:T.Group;
  private marker?:T.Mesh; private probePlane?:T.Line;
  private lastSize=[0,0];
  private cutPixelRatio?:number;
  private cutProgress=0; private cutMotion?:{from:number;to:number;started:number}; private rebuilds=0;
  private previousDraw=0; private settledFrames=0;
  private measured:SceneStats={kind:'loading',vertices:0,samples:0,drawMs:0,pixelRatio:1};
  private observationLayer=document.createElement('div');private observationSignature='';
  constructor(private host:HTMLElement,private onPick:(p:Point)=>void,private onFailure:(reason:string)=>void,private onStats:(s:SceneStats)=>void) {
    const canvas=document.createElement('canvas');
    const context=canvas.getContext('webgl2',{alpha:true,antialias:true,powerPreference:'default'});
    if(!context)throw new Error('WebGL2 is unavailable. The Basic view keeps depth and data inspection available.');
    this.renderer=new T.WebGLRenderer({canvas,context,alpha:true,antialias:true});
    this.renderer.setClearColor(0x081824,1); this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));
    this.renderer.debug.onShaderError=()=>this.onFailure('The graphics driver could not compile the ocean view. Basic view is available.');
    canvas.setAttribute('aria-label','Interactive 3D ocean field');canvas.setAttribute('role','img');
    this.host.appendChild(canvas);this.scene.add(this.content);
    this.observationLayer.className='observation-overlay';this.observationLayer.setAttribute('aria-label','Instrument locations on the model domain');this.host.appendChild(this.observationLayer);
    this.controls=new OrbitControls(this.camera,canvas);this.controls.enableDamping=true;this.controls.dampingFactor=.12;this.controls.minDistance=6;this.controls.maxDistance=40;this.controls.enablePan=false;
    this.controls.addEventListener('change',this.changed);canvas.addEventListener('webglcontextlost',this.lost);
    canvas.addEventListener('pointerdown',this.down);canvas.addEventListener('pointerup',this.up);
    this.observer=new ResizeObserver(()=>{const {width,height}=host.getBoundingClientRect();if(width&&height&&(width!==this.lastSize[0]||height!==this.lastSize[1])){this.lastSize=[width,height];this.renderer.setSize(width,height);this.camera.aspect=width/height;this.camera.updateProjectionMatrix();this.reset();}});this.observer.observe(host);
    this.reset();this.loop();
  }
  private changed=()=>{this.dirty=true;};
  private lost=(event:Event)=>{event.preventDefault();this.onFailure('The browser released the 3D graphics context. Data remain available in Basic view.');};
  private down=(event:PointerEvent)=>{this.drag=[event.clientX,event.clientY];};
  private up=(event:PointerEvent)=>{
    if(!this.drag || Math.hypot(event.clientX-this.drag[0],event.clientY-this.drag[1])>5 || !this.options||!this.options.pickEnabled||this.cutMotion)return;
    const o=this.options, rect=this.renderer.domElement.getBoundingClientRect();
    const ray=new T.Raycaster();ray.setFromCamera(new T.Vector2(2*(event.clientX-rect.left)/rect.width-1,1-2*(event.clientY-rect.top)/rect.height),this.camera);
    const project=projection(o.data,o.exaggeration);let point:T.Vector3|null=null;
    if((o.mode==='iso'||o.mode==='volume'&&o.cutaway)&&this.geometry)point=ray.intersectObject(this.geometry,true)[0]?.point??null;
    else if(o.mode==='section') {const z=project.point(o.data.longitude[0],o.data.latitude[o.sectionIndex],0)[2];point=ray.ray.intersectPlane(new T.Plane(new T.Vector3(0,0,1),-z),new T.Vector3());}
    if(!point&&o.mode!=='iso'&&o.mode!=='section'){const y=project.point(o.data.longitude[0],o.data.latitude[0],o.data.depth_m[o.depthIndex])[1];point=ray.ray.intersectPlane(new T.Plane(new T.Vector3(0,1,0),-y),new T.Vector3());}
    if(!point)return;const p=project.inverse(point.toArray() as Point),g=o.data;
    if(p[0]>=g.longitude[0]&&p[0]<=g.longitude.at(-1)!&&p[1]>=g.latitude[0]&&p[1]<=g.latitude.at(-1)!&&p[2]>=-1e-6&&p[2]<=g.depth_m.at(-1)!+1e-6)this.onPick(p);
  };
  private loop=(timestamp=performance.now())=>{
    if(this.disposed)return;this.raf=requestAnimationFrame(this.loop);if(this.options?.active===false){this.previousDraw=0;return;}this.controls.update();
    const frameMs=this.previousDraw?timestamp-this.previousDraw:0;
    this.previousDraw=0;
    // Measure the frame following a draw even when the camera is now stationary.
    // Ignoring that frame would miss slow GPUs whenever rendering is demand-driven.
    if(frameMs>0&&!this.cutMotion&&!document.hidden&&this.options?.quality==='auto'&&this.settledFrames>5){
      const threshold=this.renderer.getPixelRatio()>.7?55:100;
      this.badFrames=frameMs>threshold?this.badFrames+1:Math.max(0,this.badFrames-1);
      if(this.badFrames>=4){
        this.badFrames=0;this.settledFrames=0;
        if(this.renderer.getPixelRatio()>.7){this.renderer.setPixelRatio(.7);this.dirty=true;}
        else {this.onFailure('This device is drawing 3D slowly. Basic view keeps the same source values available. You can retry Balanced 3D.');return;}
      }
    }
    if(this.cutMotion){
      this.cutProgress=transitionValue(this.cutMotion.from,this.cutMotion.to,performance.now()-this.cutMotion.started,460);
      if(Math.abs(this.cutProgress-this.cutMotion.to)<1e-8){this.cutProgress=this.cutMotion.to;this.cutMotion=undefined;}
      this.applyCut();this.dirty=true;
    }
    if(!this.dirty||document.hidden)return;this.dirty=false;
    this.previousDraw=timestamp;this.settledFrames++;
    const start=performance.now();this.renderer.render(this.scene,this.camera);const elapsed=performance.now()-start;this.drawObservations();
    this.measured={...this.measured,drawMs:elapsed,pixelRatio:this.renderer.getPixelRatio()};
    this.host.dataset.cutProgress=this.cutProgress.toFixed(4);this.host.dataset.transitioning=String(Boolean(this.cutMotion));
    this.host.dataset.rebuilds=String(this.rebuilds);this.host.dataset.textures=String(this.renderer.info.memory.textures);
    this.host.dataset.rendered=this.measured.kind;this.host.dataset.vertices=String(this.measured.vertices);
    this.host.dataset.drawMs=elapsed.toFixed(2);this.host.dataset.pixelRatio=String(this.measured.pixelRatio);
    this.host.dataset.camera=JSON.stringify(this.camera.position.toArray());this.host.dataset.target=JSON.stringify(this.controls.target.toArray());
    this.onStats(this.measured);
    // CPU submission and browser frame interval are distinct diagnostics.
    this.host.dataset.frameMs=frameMs.toFixed(2);
  };
  private applyCut(){
    if(!this.options||!this.cutVolume)return;
    const uniforms=this.cutVolume.material.uniforms;
    // A brief movement preview reduces ray work, then restores full quality.
    // Native inspection is disabled only while the cut is moving.
    uniforms.sampleCount.value=this.cutMotion?64:160;
    if(this.cutMotion&&this.cutPixelRatio===undefined){this.cutPixelRatio=this.renderer.getPixelRatio();this.renderer.setPixelRatio(Math.min(this.cutPixelRatio,.75));}
    if(!this.cutMotion&&this.cutPixelRatio!==undefined){this.renderer.setPixelRatio(this.cutPixelRatio);this.cutPixelRatio=undefined;this.settledFrames=0;}
    const y=uniforms.boxMax.value.y+(uniforms.boxMin.value.y-uniforms.boxMax.value.y)*this.cutProgress;
    uniforms.cutOpen.value=this.cutProgress>0;uniforms.cutY.value=y;
    if(this.cutFaces){this.cutFaces.visible=this.cutProgress>0;this.cutFaces.traverse(object=>{
      const material=(object as T.Mesh).material as T.ShaderMaterial|undefined;
      if(material?.uniforms){material.uniforms.revealEnabled.value=true;material.uniforms.revealY.value=y;}
    });}
  }
  private changeCut(o:SceneOptions){
    const target=o.cutaway?1:0;
    if(o.reducedMotion){this.cutProgress=target;this.cutMotion=undefined;}
    else if(this.cutMotion?.to!==target&&this.cutProgress!==target)this.cutMotion={from:this.cutProgress,to:target,started:performance.now()};
    this.applyCut();this.dirty=true;
  }
  private moveProbe(o:SceneOptions){
    const p=projection(o.data,o.exaggeration);
    if(this.marker){this.marker.visible=o.probe[2]<=o.data.depth_m.at(-1)!;this.marker.position.set(...p.point(...o.probe));}
    if(this.probePlane)this.probePlane.position.y=p.point(o.data.longitude[0],o.data.latitude[0],o.data.depth_m[o.depthIndex])[1];
  }
  private drawObservations(){
    const o=this.options;if(!o)return;
    const markers=o.observations??[],signature=JSON.stringify(markers);
    if(signature!==this.observationSignature){
      this.observationSignature=signature;this.observationLayer.replaceChildren();
      markers.forEach((p,i)=>{const b=document.createElement('button');b.className='observation-pin';b.textContent=String(i+1);b.title=p.label;b.setAttribute('aria-label',`Inspect ${p.label}`);b.onclick=e=>{e.stopPropagation();this.options?.onInstrument?.(p.id);};this.observationLayer.appendChild(b);});
    }
    const project=projection(o.data,o.exaggeration),w=this.host.clientWidth,h=this.host.clientHeight;
    markers.forEach((p,i)=>{const b=this.observationLayer.children[i] as HTMLButtonElement;const v=new T.Vector3(...project.point(...p.position));v.y+=.12;v.project(this.camera);const visible=v.z>=-1&&v.z<=1&&Math.abs(v.x)<=1&&Math.abs(v.y)<=1;b.hidden=!visible;b.style.left=`${(v.x+1)*w/2}px`;b.style.top=`${(1-v.y)*h/2}px`;});
  }
  private clear(){
    if(this.cutPixelRatio!==undefined){this.renderer.setPixelRatio(this.cutPixelRatio);this.cutPixelRatio=undefined;}
    this.content.traverse(object=>{
      const obj=object as T.Mesh;obj.geometry?.dispose();
      const materials=Array.isArray(obj.material)?obj.material:[obj.material];materials.forEach(m=>m?.dispose());
      object.userData.texture?.dispose();
    });this.content.clear();this.textures.forEach(t=>t.dispose());this.textures=[];this.geometry=undefined;this.cutVolume=undefined;this.cutFaces=undefined;this.marker=undefined;this.probePlane=undefined;
  }
  update(o:SceneOptions){
    const previous=this.options;
    const sameGeometry=previous&&previous.data===o.data&&previous.east===o.east&&previous.north===o.north&&previous.mode===o.mode&&previous.paint===o.paint&&previous.exaggeration===o.exaggeration&&previous.iso===o.iso&&previous.sectionIndex===o.sectionIndex&&(o.mode==='volume'||previous.depthIndex===o.depthIndex);
    if(sameGeometry){this.options=o;this.moveProbe(o);this.changeCut(o);return;}
    const fit=!this.options||this.options.exaggeration!==o.exaggeration||this.options.data.depth_m.at(-1)!==o.data.depth_m.at(-1);
    this.options=o;this.clear();this.rebuilds++;this.cutMotion=undefined;this.cutProgress=o.cutaway?1:0;const g=o.data,project=projection(g,o.exaggeration);
    const min=project.point(g.longitude[0],g.latitude.at(-1)!,g.depth_m.at(-1)!);
    const max=project.point(g.longitude.at(-1)!,g.latitude[0],g.depth_m[0]);
    const size=new T.Vector3(...max).sub(new T.Vector3(...min)),center=new T.Vector3(...min).add(new T.Vector3(...max)).multiplyScalar(.5);
    const box=new T.BoxGeometry(size.x,size.y,size.z);box.translate(center.x,center.y,center.z);
    const outline=new T.LineSegments(new T.EdgesGeometry(box),new T.LineBasicMaterial({color:0x86abbc,transparent:true,opacity:.48}));box.dispose();this.content.add(outline);
    for(const depth of Array.from({length:6},(_,i)=>g.depth_m[0]+i*(g.depth_m.at(-1)!-g.depth_m[0])/5)){
      const y=project.point(g.longitude[0],g.latitude[0],depth)[1];this.content.add(label(`${depth.toLocaleString(undefined,{maximumFractionDigits:1})} m`,[min[0]-.8,y,max[2]+.4],.9));
      const points=[new T.Vector3(min[0],y,min[2]),new T.Vector3(max[0],y,min[2]),new T.Vector3(max[0],y,max[2])];
      this.content.add(new T.Line(new T.BufferGeometry().setFromPoints(points),new T.LineBasicMaterial({color:0x234756,transparent:true,opacity:.45})));
    }
    this.content.add(label(longitudeLabel(g.longitude[0]),[min[0],.55,max[2]+.15],.9),label(longitudeLabel(g.longitude.at(-1)!),[max[0],.55,max[2]+.15],.9),label('N',[min[0]-.4,.45,min[2]-.2],.9));
    let vertices=0;
    if(o.mode==='volume'){
      const v=volume(g,o.exaggeration,o.paint,160,o.cutaway);this.content.add(v.mesh);this.textures.push(v.texture);vertices=36;
      this.cutVolume=v.mesh;
      const faces=surface(cutawayFaces(g,o.exaggeration),o.paint,false);faces.renderOrder=3;
      const group=new T.Group();group.add(faces,missingSurface(cutawayFaces(g,o.exaggeration,true)));this.cutFaces=group;this.geometry=group;this.content.add(group);this.applyCut();
      const y=0;
      const points=[[min[0],y,min[2]],[max[0],y,min[2]],[max[0],y,max[2]],[min[0],y,max[2]],[min[0],y,min[2]]].map(p=>new T.Vector3(...p));
      const plane=new T.Line(new T.BufferGeometry().setFromPoints(points),new T.LineBasicMaterial({color:0xd8eee4,transparent:true,opacity:.9,depthTest:false}));plane.renderOrder=4;this.probePlane=plane;this.content.add(plane);
    }else{
      const shape=o.mode==='iso'?isoMesh(g,o.iso,o.exaggeration):sliceMesh(g,o.mode==='section'?'section':'slice',o.mode==='section'?o.sectionIndex:o.depthIndex,o.exaggeration);
      const mesh=surface(shape,o.paint,o.mode==='iso');this.geometry=mesh;this.content.add(mesh);vertices=shape.scalars.length;
      if(o.mode==='section')this.content.add(missingSurface(sliceMesh(g,'section',o.sectionIndex,o.exaggeration,true)));
      if(o.mode==='currents'&&o.east&&o.north){
        const arrowLength=.35; // Equal-length direction glyphs; the slice colour encodes speed.
        for(let y=0;y<g.latitude.length;y+=3)for(let x=0;x<g.longitude.length;x+=3){
          const index=offset(g,x,y,o.depthIndex),u=o.east.values[index],v=o.north.values[index];if(u===null||v===null)continue;
          const magnitude=Math.hypot(u,v);if(magnitude<1e-7)continue;
          const p=project.point(g.longitude[x],g.latitude[y],g.depth_m[o.depthIndex]);p[1]+=.025;
          const arrow=new T.ArrowHelper(new T.Vector3(u/magnitude,0,-v/magnitude),new T.Vector3(...p),arrowLength,0xe8faf2,.12,.09);this.content.add(arrow);
        }
      }
    }
    {const marker=new T.Mesh(new T.SphereGeometry(.065,12,8),new T.MeshBasicMaterial({color:0xffffff,depthTest:false}));marker.position.set(...project.point(...o.probe));marker.renderOrder=5;this.marker=marker;this.content.add(marker);}
    this.moveProbe(o);
    this.controls.target.set(0,center.y,0);this.controls.update();
    if(fit)this.reset();
    this.measured={...this.measured,kind:o.mode,vertices,samples:g.values.length};this.dirty=true;
  }
  reset(){
    if(!this.options){this.camera.position.set(10,6.8,12.4);this.controls.target.set(0,-1.8,0);}
    else{
      const {data:g,exaggeration}=this.options,project=projection(g,exaggeration);
      const min=project.point(g.longitude[0],g.latitude.at(-1)!,g.depth_m.at(-1)!),max=project.point(g.longitude.at(-1)!,g.latitude[0],0);
      const target=new T.Vector3(0,(min[1]+max[1])/2,0),direction=new T.Vector3(10,9,12.4).normalize();
      const forward=direction.clone().negate(),right=new T.Vector3().crossVectors(forward,new T.Vector3(0,1,0)).normalize(),up=new T.Vector3().crossVectors(right,forward);
      const tanV=Math.tan(this.camera.fov*Math.PI/360)*.9,tanH=tanV*this.camera.aspect;let distance=6;
      // Include the physical box and its axis labels at every viewport aspect ratio.
      for(const x of [min[0]-1.8,max[0]+.5])for(const y of [min[1]-.35,max[1]+.7])for(const z of [min[2]-.8,max[2]+.8]){
        const p=new T.Vector3(x,y,z).sub(target);distance=Math.max(distance,Math.abs(p.dot(right))/tanH-p.dot(forward),Math.abs(p.dot(up))/tanV-p.dot(forward));
      }
      this.controls.maxDistance=Math.max(40,distance*2);this.controls.target.copy(target);this.camera.position.copy(target).addScaledVector(direction,distance);
    }
    this.controls.update();this.dirty=true;
  }
  rotate(direction:number){const offset=this.camera.position.clone().sub(this.controls.target);offset.applyAxisAngle(new T.Vector3(0,1,0),direction*.18);this.camera.position.copy(this.controls.target).add(offset);this.controls.update();this.dirty=true;}
  zoom(factor:number){const offset=this.camera.position.clone().sub(this.controls.target).multiplyScalar(factor);this.camera.position.copy(this.controls.target).add(offset);this.controls.update();this.dirty=true;}
  dispose(){this.disposed=true;cancelAnimationFrame(this.raf);this.observer.disconnect();const canvas=this.renderer.domElement;canvas.removeEventListener('webglcontextlost',this.lost);canvas.removeEventListener('pointerdown',this.down);canvas.removeEventListener('pointerup',this.up);this.controls.removeEventListener('change',this.changed);this.controls.dispose();this.clear();this.renderer.dispose();this.renderer.forceContextLoss();canvas.remove();this.observationLayer.remove();}
}
