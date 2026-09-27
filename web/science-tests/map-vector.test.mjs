import test from 'node:test';
import assert from 'node:assert/strict';
import {mapVector} from '../src/ocean/mapVector.ts';

function close(actual, expected, tolerance=1e-10) {
  assert.ok(actual !== null);
  actual.forEach((value,i)=>assert.ok(Math.abs(value-expected[i])<tolerance,`${actual} differs from ${expected}`));
}

test('geographic cardinal directions keep their signs on rectangular maps',()=>{
  close(mapVector(1,0,13.5,5,3,750,280),[14,0]);
  close(mapVector(0,1,13.5,5,3,750,280),[0,-14]);
  close(mapVector(-1,0,-60,5,3,200,600),[-14,0]);
  close(mapVector(0,-1,-60,5,3,200,600),[0,14]);
});

test('equal physical scales preserve a known 3:4 horizontal vector at multiple latitudes',()=>{
  for(const latitude of [0,13.5,60,-60]) {
    const width=100*5*Math.cos(latitude*Math.PI/180),height=100*3;
    close(mapVector(3,4,latitude,5,3,width,height),[8.4,-11.2]);
  }
});

test('a twice-as-wide equatorial plotting scale changes the displayed vector direction',()=>{
  // A 1 m east and 1 m north displacement spans twice as many pixels eastward.
  close(mapVector(1,1,0,5,3,1000,300),[28/Math.sqrt(5),-14/Math.sqrt(5)]);
});

test('longitude convergence at 60 degrees doubles zonal angular displacement',()=>{
  // At 60 degrees, one longitude degree covers half the distance of one latitude degree.
  close(mapVector(1,1,60,5,3,500,300),[28/Math.sqrt(5),-14/Math.sqrt(5)]);
});

test('arrows preserve projected bearing when a viewport changes aspect ratio',()=>{
  // Compare to a finite physical step mapped through the independent spherical-coordinate formula.
  const radius=6371008.8,latitude=14,u=.036,v=.070,lonSpan=4.9599609375,latSpan=3;
  const longitudeStep=u/(radius*Math.cos(latitude*Math.PI/180))*180/Math.PI;
  const latitudeStep=v/radius*180/Math.PI;
  for(const [width,height] of [[900,346],[295,240],[225,190]]) {
    const dx=longitudeStep/lonSpan*width,dy=-latitudeStep/latSpan*height;
    const magnitude=Math.hypot(dx,dy);
    close(mapVector(u,v,latitude,lonSpan,latSpan,width,height),[14*dx/magnitude,14*dy/magnitude]);
  }
});

test('normalization keeps glyph length independent of speed',()=>{
  const small=mapVector(.0036,.007,13.5,5,3,600,200),large=mapVector(.36,.7,13.5,5,3,600,200);
  close(small,large);
  assert.ok(Math.abs(Math.hypot(...small)-14)<1e-12);
});

test('absent flow and invalid geographic or plotting inputs do not create arrows',()=>{
  for(const input of [[0,0,13,5,3,600,200],[NaN,1,13,5,3,600,200],[1,1,90,5,3,600,200],[1,1,13,0,3,600,200],[1,1,13,5,3,0,200]]) assert.equal(mapVector(...input),null);
});
