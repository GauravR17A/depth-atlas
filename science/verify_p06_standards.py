"""Independent source and protocol checks using netCDF4, xarray, OWSLib and pydap.

No application store, grid adapter or product calculator is used for numerical expectations.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import netCDF4
import numpy as np
import requests
import xarray as xr
from owslib.wms import WebMapService
from owslib.wcs import WebCoverageService
from pydap.client import open_url
from PIL import Image

from science.check_cf_exchange import check_exchange

ROOT=Path(__file__).resolve().parents[1]
SOURCES={'temperature':'water_temp','salinity':'salinity','eastward_velocity':'water_u','northward_velocity':'water_v'}


def source_fields(path):
    with netCDF4.Dataset(path) as ds:
        fields={}
        for name,original in SOURCES.items():
            v=ds[original];v.set_auto_maskandscale(False);raw=v[:]
            missing=~np.isfinite(raw)
            for key in ['_FillValue','missing_value']:
                if key in v.ncattrs(): missing|=np.isin(raw,np.atleast_1d(v.getncattr(key)))
            if 'valid_range' in v.ncattrs(): missing|=(raw<v.valid_range[0])|(raw>v.valid_range[1])
            if 'valid_min' in v.ncattrs(): missing|=raw<v.valid_min
            if 'valid_max' in v.ncattrs(): missing|=raw>v.valid_max
            fields[name]=np.where(missing,np.nan,raw.astype('f8')*float(v.scale_factor)+float(v.add_offset))
        fields['horizontal_kinetic_energy']=.5*(fields['eastward_velocity']**2+fields['northward_velocity']**2)
        coords={name:ds[name][:].copy() for name in ['time','depth','lat','lon']}
    return coords,fields


def verify(base, prefix='p06', case_id='bay-bengal-2024-01'):
    evidence=ROOT/'docs/evidence'; evidence.mkdir(exist_ok=True)
    artifacts=evidence/(prefix+'-protocol');artifacts.mkdir(exist_ok=True)
    checks=[];requests_made=[]
    def check(name,value,**details):
        checks.append(dict(check=name,passed=bool(value),**details))
        if not value: print('FAILED:',name,details,flush=True)
    def equal(name,actual,expected,tolerance=1e-12):
        a=np.asarray(np.ma.filled(actual,np.nan),dtype='f8');e=np.asarray(expected,dtype='f8')
        mask_match=a.shape==e.shape and np.array_equal(np.isnan(a),np.isnan(e))
        difference=float(np.max(np.abs(a[np.isfinite(e)]-e[np.isfinite(e)]))) if mask_match and np.isfinite(e).any() else None
        check(name,mask_match and np.allclose(a,e,rtol=0,atol=tolerance,equal_nan=True),shape=list(e.shape),missing=int(np.isnan(e).sum()),max_absolute_error=difference,tolerance=tolerance)
    pack=ROOT/'casepacks/standards';record=json.loads((pack/('manifest.json' if case_id=='bay-bengal-2024-01' else case_id+'.json')).read_text())
    file=pack/record['file']
    check('exchange checksum',hashlib.sha256(file.read_bytes()).hexdigest()==record['sha256'])
    cf=check_exchange(file);check('scoped CF interpretation',cf['passed'])
    from science.case_recipes import RECIPES
    acquisition=json.loads((ROOT/RECIPES[case_id]['raw']/'acquisition.json').read_text())
    sources=sorted([f for f in acquisition['files'] if f['archive_kind']=='packed_source_subset_reconstructed_as_netcdf'],key=lambda f:f['time'])
    references=[]
    with xr.open_dataset(file,engine='netcdf4') as exchange:
        for ti,source in enumerate(sources):
            path=ROOT/source['path'];check('source fingerprint '+str(ti),hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'])
            coords,fields=source_fields(path);references.append((coords,fields))
            for target,original in [('latitude','lat'),('longitude','lon'),('depth','depth')]: equal('native '+target+' '+str(ti),exchange[target].values,coords[original])
            check('time decode '+str(ti),str(exchange.time.values[ti])[:19]==source['time'][:19])
            for variable in fields: equal('source to exchange '+variable+' '+str(ti),exchange[variable].values[ti:ti+1],fields[variable])
    dataset='ocean/'+record['file'];wms_url=base+'/wms/'+dataset;wcs_url=base+'/wcs/'+dataset;dap_url=base+'/dodsC/'+dataset
    for name,url,params in [('wms',wms_url,dict(service='WMS',version='1.3.0',request='GetCapabilities')),('wcs',wcs_url,dict(service='WCS',version='1.0.0',request='GetCapabilities'))]:
        r=requests.get(url,params=params,timeout=60);r.raise_for_status();(artifacts/(name+'-capabilities.xml')).write_bytes(r.content);requests_made.append(r.url)
    wms=WebMapService(wms_url,version='1.3.0');wcs=WebCoverageService(wcs_url,version='1.0.0')
    check('WMS and WCS advertised fields',set(record['variables']).issubset(wms.contents) and set(record['variables']).issubset(wcs.contents))
    coords,fields=references[1];lat=coords['lat'];lon=coords['lon'];depth=coords['depth'];stamp=sources[1]['time']
    bbox=wms['temperature'].boundingBoxWGS84
    check('WMS bounds enclose native cells',bbox[0]<=lon[0] and bbox[2]>=lon[-1] and bbox[1]<=lat[0] and bbox[3]>=lat[-1])
    images={}
    for crs in ['CRS:84','EPSG:4326']:
        r=wms.getmap(layers=['temperature'],styles=['raster/default'],srs=crs,bbox=bbox,size=(len(lon),len(lat)),format='image/png',transparent=True,time=stamp,elevation=100,colorscalerange='0,30',numcolorbands=250)
        content=r.read();(artifacts/('temperature-100m-'+crs.replace(':','-')+'.png')).write_bytes(content)
        im=np.asarray(Image.open(io.BytesIO(content)).convert('RGBA'));images[crs]=im
        check('WMS image '+crs,im.shape==(len(lat),len(lon),4) and np.unique(im.reshape(-1,4),axis=0).shape[0]>2)
    check('WMS geographic axis order',np.array_equal(images['CRS:84'],images['EPSG:4326']))
    z=int(np.where(depth==100)[0][0])
    for x,y in [(0,0),(min(10,len(lon)-1),min(10,len(lat)-1)),(len(lon)//2,len(lat)//2),(len(lon)-1,len(lat)-1)]:
        params=dict(service='WMS',version='1.3.0',request='GetFeatureInfo',layers='temperature',query_layers='temperature',styles='raster/default',crs='CRS:84',bbox=','.join(map(str,bbox)),width=len(lon),height=len(lat),i=x,j=len(lat)-1-y,time=stamp,elevation=100,info_format='text/xml')
        r=requests.get(wms_url,params=params,timeout=60);r.raise_for_status();requests_made.append(r.url);root=ET.fromstring(r.content)
        actual=float(root.findtext('.//value'));equal(f'WMS pixel value {x},{y}',[actual],[fields['temperature'][0,z,y,x]])
        equal(f'WMS pixel coordinate {x},{y}',[float(root.findtext('longitude')),float(root.findtext('latitude'))],[lon[x],lat[y]],tolerance=.0001)
    for variable in record['variables']:
        for level in [100,5000]:
            r=wcs.getCoverage(identifier=variable,bbox=(float(lon[2]),float(lat[2]),float(lon[-3]),float(lat[-3])),time=[stamp],format='NetCDF3',vertical=level)
            body=r.read();(artifacts/f'{variable}-{level}m.nc').write_bytes(body)
            with netCDF4.Dataset('wcs',memory=body) as ds:
                ys=[int(np.argmin(abs(lat-v))) for v in ds['latitude'][:]];xs=[int(np.argmin(abs(lon-v))) for v in ds['longitude'][:]];zs=[int(np.argmin(abs(depth-v))) for v in ds['depth'][:]]
                equal(f'WCS {variable} latitude {level}',ds['latitude'][:],lat[ys],tolerance=.0001);equal(f'WCS {variable} longitude {level}',ds['longitude'][:],lon[xs],tolerance=.0001);equal(f'WCS {variable} depth {level}',ds['depth'][:],[level])
                actual_time=netCDF4.num2date(ds['time'][:],ds['time'].units,getattr(ds['time'],'calendar','standard'))[0].strftime('%Y-%m-%dT%H:%M:%SZ')
                check(f'WCS {variable} time {level}',actual_time==stamp)
                expected=fields[variable][:,zs,:,:][:,:,ys,:][:,:,:,xs]
                equal(f'WCS {variable} values and masks {level}',ds[variable][:],expected)
    dap=open_url(dap_url,protocol='dap2')
    for variable in record['variables']:
        selection=dap[variable][1:2,0:40:3,10:18:2,10:22:3]
        values=np.asarray(selection.data,dtype='f8')
        values=np.where(values==dap[variable].attributes.get('_FillValue'),np.nan,values)
        equal('OPeNDAP strided '+variable,values,fields[variable][:,0:40:3,10:18:2,10:22:3])
    equal('OPeNDAP longitude stride',dap['longitude'][10:22:3].data,lon[10:22:3])
    equal('OPeNDAP irregular depth stride',dap['depth'][0:40:3].data,depth[0:40:3])
    r=requests.get(wms_url,params=dict(service='WMS',version='1.3.0',request='GetMap',layers='unknown',crs='CRS:84',bbox='85,12,90,15',width=len(lon),height=len(lat),format='image/png'),timeout=30)
    check('WMS unsupported layer returns an exception',b'Exception' in r.content and not r.content.startswith(b'\x89PNG'))
    report=dict(phase='P06',base_url=base,implementation='THREDDS 5.9 / Tomcat 10.1.60 / Temurin Java 17.0.20.1',exchange=record,cf=cf,checks=checks,request_examples=requests_made,passed=all(c['passed'] for c in checks),limitations=['Local service, not a public THREDDS deployment.','Scoped CF interpretation and protocol requests, not universal OGC/CF certification.','WMS pixel coordinates and WCS coordinates use the service regular-grid envelope; tested source-coordinate tolerance 0.0001 degree. WCS maximum longitude change measured at 0.0000826928 degree. Use the native file or OPeNDAP for exact coordinates.'])
    (evidence/(prefix+'-protocol-verification.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],checks=len(checks),failures=[c for c in checks if not c['passed']]),indent=2))
    return report['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8096/thredds');parser.add_argument('--prefix',default='p06');parser.add_argument('--case',default='bay-bengal-2024-01');args=parser.parse_args()
    raise SystemExit(0 if verify(args.base.rstrip('/'),args.prefix,args.case) else 1)
