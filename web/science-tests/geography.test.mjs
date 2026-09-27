import test from 'node:test';
import assert from 'node:assert/strict';
import { geoMercator } from 'd3-geo';
import { longitudeContext, longitudeLabel, latitudeLabel, longitudeOnAxis } from '../src/geography.ts';

test('Pacific native longitude labels preserve the same physical location', () => {
  assert.equal(longitudeLabel(220.5, 1), '139.5° W');
  assert.equal(longitudeLabel(-139.5, 1), '139.5° W');
  assert.equal(longitudeLabel(180, 1), '180.0°');
  assert.equal(latitudeLabel(-5, 1), '5.0° S');
  assert.equal(longitudeLabel(87.625, 3), '87.625° E');
});

test('dateline instrument positions remain close in a rotated map', () => {
  const context = longitudeContext([179, -179]);
  assert.equal(context.center, -180);
  assert.equal(context.halfSpan, 1);
  const projection = geoMercator().rotate([-context.center, 0]).center([0, 0]).scale(1000).translate([360, 195]);
  const west = projection([179, 0]), east = projection([-179, 0]);
  assert.ok(Math.abs(east[0] - west[0] - 2 * Math.PI / 180 * 1000) < 1e-10);
  assert.ok(west[0] > 0 && east[0] < 720);
});

test('Indian Ocean and signed longitude conventions share the same map context', () => {
  const indian = longitudeContext([85, 87, 90]);
  assert.ok(Math.abs(indian.center - 262 / 3) < 1e-12);
  assert.ok(Math.abs(indian.halfSpan - 8 / 3) < 1e-12);
  assert.deepEqual(longitudeContext([179, 181]), longitudeContext([179, -179]));
  assert.deepEqual(longitudeContext([]), { center: 0, halfSpan: 0 });
});

test('signed Argo positions map to the equivalent Pacific source column without moving Indian positions',()=>{
 assert.ok(Math.abs(longitudeOnAxis(-139.7,[140.5,279.5])-220.3)<1e-12);
 assert.equal(longitudeOnAxis(87.625,[85,90]),87.625);
});

test('nearby decimal Argo coordinates do not unwrap into different worlds at a rounded gap boundary',()=>{
 const longitudes=[-139.687,-140.093,-140.031];
 const context=longitudeContext(longitudes),mean=longitudes.reduce((sum,value)=>sum+value,0)/longitudes.length;
 assert.ok(Math.abs(context.center-mean)<1e-10);
 assert.ok(context.halfSpan<0.3);
 const projection=geoMercator().rotate([-context.center,0]).center([0,0]).scale(2000).translate([360,195]);
 const xs=longitudes.map(longitude=>projection([longitude,0])[0]);
 assert.ok(xs.every(x=>x>345&&x<375));
 const single=longitudeContext([-139.687,-139.687]);
 assert.ok(Math.abs(single.center+139.687)<1e-10);
 assert.equal(single.halfSpan,0);
});
