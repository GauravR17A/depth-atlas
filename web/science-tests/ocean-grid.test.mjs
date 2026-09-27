import { transitionValue } from '../src/ocean/motion.ts';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bracket, sample, projection, sliceMesh, isoMesh, speed, rangeError, fraction, nearest, depthWindow, coverage, cutawayPlanes, cutawayFaces } from '../src/ocean/grid.ts';

const close=(actual,expected,tolerance=1e-8)=>assert.ok(Math.abs(actual-expected)<tolerance,`${actual} != ${expected}`);

test('depth windows retain original levels, masks and values without inventing an endpoint',()=>{
  const g=grid(),before=JSON.stringify(g);g.values[1]=null;
  const window=depthWindow(g,50);assert.deepEqual(window.depth_m,[0,20]);assert.equal(window.values[1],null);assert.equal(window.shape[0],2);
  assert.deepEqual(window.values,g.values.slice(0,12));assert.equal(g.depth_m.length,3);g.values[1]=208;assert.equal(JSON.stringify(g),before);
});

test('coverage distinguishes partial samples from completely absent depth levels',()=>{
  const g=grid();g.values[0]=null;for(let i=12;i<18;i++)g.values[i]=null;
  assert.deepEqual(coverage(g),{counts:[5,6,0],empty:[100],partial:[0],deepest:20});
});

test('cutaway walls use actual coordinate planes and unmodified source values',()=>{
  const g={longitude:[85,86,88,90],latitude:[10,11,13,16],depth_m:[0,20,100],shape:[3,4,4],values:[]};
  for(const z of g.depth_m)for(const y of g.latitude)for(const x of g.longitude)g.values.push(2*x+3*y+.5*z);
  const copy=[...g.values],cut=cutawayPlanes(g,200),faces=cutawayFaces(g,200),p=projection(g,200);assert.ok(faces.scalars.length>0);
  for(let i=0;i<faces.scalars.length;i++){
    const xyz=faces.positions.slice(i*3,i*3+3),[lon,lat,z]=p.inverse(xyz);close(faces.scalars[i],2*lon+3*lat+.5*z);
    assert.ok(Math.abs(lon-88)<1e-8||Math.abs(lat-13)<1e-8);assert.ok(xyz[0]>=cut.worldX-1e-8&&xyz[2]>=cut.worldZ-1e-8);
  }
  assert.deepEqual(g.values,copy);
});

test('missing section hatching partitions incomplete cells and never supplies scientific values',()=>{
  const g=grid(),complete=sliceMesh(g,'section',0,50);g.values[0]=null;
  const valid=sliceMesh(g,'section',0,50),missing=sliceMesh(g,'section',0,50,true);
  assert.ok(missing.scalars.length>0);assert.equal(valid.scalars.length+missing.scalars.length,complete.scalars.length);
  assert.equal(g.values[0],null);
});
function grid(depth=[0,20,100]) {
  const g={longitude:[85,86,88],latitude:[12,14],depth_m:depth,shape:[depth.length,2,3],values:[]};
  for(const z of depth)for(const y of g.latitude)for(const x of g.longitude)g.values.push(2*x+3*y+.5*z);
  return g;
}
test('irregular axes bracket physical positions, including the final coordinate',()=>{
  assert.deepEqual(bracket([0,20,100],60),[1,.5]);assert.deepEqual(bracket([0,20,100],100),[1,1]);assert.equal(bracket([0,20,100],101),null);
});
test('trilinear interpolation reproduces an independent affine field on irregular axes',()=>{
  close(sample(grid(),87,13,60),243);close(sample(grid(),88,14,100),268);assert.equal(sample(grid(),84,13,60),null);
});
test('masked contributors stay missing; zero-weight missing neighbours do not contaminate a native point',()=>{
  const g=grid();g.values[0]=null;assert.equal(sample(g,85.5,13,10),null);close(sample(g,86,12,0),208);
});
test('projection preserves geographic orientation and metre depths at a declared exaggeration',()=>{
  const g=grid(),p=projection(g,50),surface=p.point(86,13,0),deep=p.point(86,13,100);
  close(surface[1],0);close(deep[1],-100*50*10/(3*6371008.8*Math.PI/180*Math.cos(13*Math.PI/180)));
  assert.ok(p.point(88,13,0)[0]>surface[0]);assert.ok(p.point(86,14,0)[2]<surface[2]);
  p.inverse(deep).forEach((v,i)=>close(v,[86,13,100][i]));
});
test('vertical exaggeration changes geometry only, with correct unequal interval ratios',()=>{
  const g=grid(),before=[...g.values],p=projection(g,50),q=projection(g,1);
  close(p.point(85,12,100)[1]/p.point(85,12,20)[1],5);close(p.point(85,12,100)[1]/q.point(85,12,100)[1],50);assert.deepEqual(g.values,before);
});
test('horizontal slice has its exact source depth and excludes missing quads',()=>{
  const g=grid(),mesh=sliceMesh(g,'slice',1,50),y=projection(g,50).point(85,12,20)[1];assert.equal(mesh.scalars.length,12);
  for(let i=1;i<mesh.positions.length;i+=3)close(mesh.positions[i],y);
  g.values[6]=null;assert.equal(sliceMesh(g,'slice',1,50).scalars.length,6);
});
test('vertical section includes actual irregular depth levels',()=>{
  const g=grid(),mesh=sliceMesh(g,'section',1,1),p=projection(g,1);
  const depths=new Set(mesh.positions.filter((_,i)=>i%3===1));assert.equal(depths.size,3);
  for(const depth of g.depth_m)assert.ok([...depths].some(y=>Math.abs(y-p.point(85,14,depth)[1])<1e-10));
});
test('isosurface of a depth field lies at the independently known physical depth',()=>{
  const g=grid();g.values=g.depth_m.flatMap(z=>Array(6).fill(z));const before=[...g.values];
  const mesh=isoMesh(g,37,50),p=projection(g,50);assert.ok(mesh.scalars.length>0);
  for(let i=0;i<mesh.positions.length;i+=3){const [lon,lat,depth]=p.inverse(mesh.positions.slice(i,i+3));close(depth,37);assert.ok(lon>=85-1e-8&&lon<=88+1e-8&&lat>=12-1e-8&&lat<=14+1e-8);}
  assert.ok(mesh.scalars.every(v=>v===37));assert.deepEqual(g.values,before);
});
test('isosurface does not bridge a missing cell or invent an out-of-range surface',()=>{
  const g=grid([0,100]);g.values=g.depth_m.flatMap(z=>Array(6).fill(z));assert.equal(isoMesh(g,101,10).positions.length,0);
  g.values[1]=null;assert.equal(isoMesh(g,50,10).positions.length,0);
});
test('current speed preserves masks and rejects mixed timestamps',()=>{
  const base={...grid(),case_id:'test',time:'2024-01-01T00:00:00Z',manifest_sha256:'abc',processing:[]};
  const u={...base,values:base.values.map(()=>3)},v={...base,values:base.values.map(()=>4)};
  v.values[0]=null;const result=speed(u,v);assert.equal(result.values[0],null);assert.equal(result.values[1],5);assert.equal(result.units,'m/s');
  assert.throws(()=>speed(u,{...v,time:'2024-01-02T00:00:00Z'}));
});
test('log colour mapping uses the geometric midpoint and rejects invalid domains',()=>{
  const p={min:1,max:100,log:true,palette:'thermal',opacity:1};close(fraction(10,p),.5);assert.equal(fraction(0,p),null);
  assert.ok(rangeError({...p,min:0}));assert.ok(rangeError({...p,min:101}));assert.ok(rangeError({...p,max:NaN}));assert.equal(rangeError(p),null);
});
test('native picking uses nearest coordinates without interpolating source values',()=>{
  assert.equal(nearest([0,20,100],65),2);assert.equal(nearest([85,86,88],87.6),2);assert.equal(nearest([12,14],13),0);
});

test('display transition is bounded, reversible and snaps with reduced motion',()=>{
  const opening=Array.from({length:11},(_,i)=>transitionValue(0,1,i*46,460));
  assert.equal(opening[0],0);assert.equal(opening.at(-1),1);
  assert.ok(opening.every((v,i)=>v>=0&&v<=1&&(i===0||v>=opening[i-1])));
  close(transitionValue(.4,0,230,460),.2);assert.equal(transitionValue(.4,0,460,460),0);
  assert.equal(transitionValue(0,1,0,0),1);assert.equal(transitionValue(0,1,-1,460),0);
});
