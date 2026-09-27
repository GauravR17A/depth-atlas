"""Native wider-region extraction with byte-bounded caches and explicit limits.

Only pinned local source IDs are accepted. No user URL becomes a network request
or file path. Hash checks precede cache hits. Display selection never changes the
native analysis/export grid. Limits are per process, not distributed quotas.
"""
from __future__ import annotations
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
from threading import BoundedSemaphore, RLock

import numpy as np
from science.contracts import UnsupportedData
from science.wider_contracts import WiderQuery, WiderPack, WIDER_METHOD, MAX_NATIVE_VALUES, MAX_PACK_BYTES

SPECS = {
    'godas-2022': {
        'title':'GODAS wider ocean fields', 'kind':'model_analysis', 'version':'NOAA GODAS bias-corrected monthly archive, 2022',
        'provider':'NOAA NCEP / Physical Sciences Laboratory', 'vertical_name':'Depth', 'vertical_units':'m',
        'reference':'https://psl.noaa.gov/data/gridded/data.godas.html',
        'citation':'Data provided by NOAA PSL, Boulder, Colorado, USA. NCEP Global Ocean Data Assimilation System (GODAS).',
        'licence':'NOAA public data; retain provider acknowledgement.',
        'variables':{
            'potential_temperature':{'source':'pottmp','label':'Potential temperature','units':'°C','scale':1.,'offset':-273.15,'range':[260,310],'paint':[-2,32],'definition':'Source potential temperature in kelvin converted to degrees Celsius. Not in-situ temperature.'},
            'source_salinity':{'source':'salt','label':'Source salinity','units':'g/kg','scale':1000.,'offset':0.,'range':[0,.1],'paint':[28,38],'definition':'Source salinity mass fraction (kg/kg) multiplied by 1000. Not a computed TEOS-10 Absolute Salinity or practical-salinity diagnostic.'},
        },
        'limitations':['Only September and October 2022 and native 5-459 m levels are packaged here, not live conditions.','Source latitude coverage excludes polar regions. Land, ice or missing support remain missing; the source has no separate ice flag in these fields.','Monthly fields are not directly matched to instantaneous in-situ observations. Earlier Drift, Heat, Expedition and Evolution methods are not enabled for arbitrary new regions.'],
    },
    'gobai-v2.2': {
        'title':'GOBAI-O2 external oxygen product', 'kind':'ml_derived', 'version':'GOBAI-O2 v2.2; NCEI archive release 4.4',
        'provider':'Sharp et al. / NOAA NCEI', 'vertical_name':'Pressure', 'vertical_units':'dbar',
        'reference':'https://doi.org/10.25921/z72m-yz67',
        'citation':'Sharp, J. D., Fassbender, A. J., Carter, B. R., Johnson, G. C., Schultz, C., and Dunne, J. P. GOBAI-O2, NCEI accession 0259304, product v2.2, archive 4.4. doi:10.25921/z72m-yz67.',
        'licence':'CC0 1.0 Universal, as supplied in GOBAI-O2-v2.2-license.txt. Provider citation is retained.',
        'model_version':'External GOBAI-O2 v2.2 machine-learning reconstruction. This app does not train or run the producer model.',
        'training_reference':'BGC-Argo and GLODAP observations; https://doi.org/10.5281/zenodo.8071469',
        'validation_reference':'https://doi.org/10.5194/essd-15-4481-2023',
        'uncertainty_definition':'Provider total uncertainty: measurement, gridding and algorithm sources combined in quadrature. Not a confidence percentage or an app-generated probability. The linked 2023 paper describes v2.1 methods; supplied values are the separately pinned v2.2 product.',
        'variables':{
            'oxygen':{'source':'oxy','label':'Dissolved oxygen','units':'µmol/kg','scale':1.,'offset':0.,'paint':[0,350],'definition':'External monthly machine-learning estimate of dissolved oxygen, not an individual sensor measurement.'},
            'oxygen_uncertainty':{'source':'uncer','label':'Provider oxygen uncertainty','units':'µmol/kg','scale':1.,'offset':0.,'paint':[0,35],'definition':'Original provider total uncertainty field, retained separately from oxygen concentration.'},
        },
        'limitations':['Only September and October 2022 are packaged here. The wider original product period is not silently exposed.','The native vertical coordinate is pressure in dbar, not metres. It is shown in slices, sections and profiles; metre-based 3D rendering is unavailable.','Oxygen estimates and provider uncertainty are not independent validation of the training observations. Land, ice or missing values are not filled by the app.'],
    },
}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


class ByteCache:
    def __init__(self,max_bytes,max_items):
        self.max_bytes=max_bytes;self.max_items=max_items;self.entries=OrderedDict();self.bytes=0;self.lock=RLock()
    def get(self,key):
        with self.lock:
            if key not in self.entries:return None
            self.entries.move_to_end(key);return self.entries[key][0]
    def put(self,key,value,size):
        with self.lock:
            old=self.entries.pop(key,None)
            if old:self.bytes-=old[1]
            if size>self.max_bytes:return
            while self.entries and (self.bytes+size>self.max_bytes or len(self.entries)>=self.max_items):
                _,(_,cost)=self.entries.popitem(last=False);self.bytes-=cost
            self.entries[key]=(value,size);self.bytes+=size


class WiderStore:
    def __init__(self,root:Path):
        self.root=root
        self.native=ByteCache(40*1024*1024,3)
        self.responses=ByteCache(12*1024*1024,12)
        self.slots=BoundedSemaphore(4)
        self.load_lock=RLock()

    @contextmanager
    def capacity(self):
        if not self.slots.acquire(blocking=False):
            raise UnsupportedData('regional_capacity','Four regional operations are already running on this server instance. Retry after they finish.')
        try:yield
        finally:self.slots.release()

    def source(self,dataset):
        if dataset not in SPECS:raise UnsupportedData('unsupported_source','Choose a listed wider source.')
        path=self.root/dataset/'source.json'
        if not path.is_file():raise UnsupportedData('source_unavailable','This prepared source is unavailable.')
        body=path.read_bytes()
        if len(body)>200_000:raise UnsupportedData('case_integrity_error','Source metadata exceeds its bound.')
        from adapters.registry import ADAPTERS
        source=ADAPTERS.load('godas-monthly-subset' if dataset=='godas-2022' else 'gobai-oxygen',path);axes=source['axes']
        lat=np.asarray(axes['lat'],dtype=np.float64);lon=np.asarray(axes['lon'],dtype=np.float64);levels=np.asarray(axes['depth' if dataset=='godas-2022' else 'pres'],dtype=np.float64)
        for axis in [lat,levels]:
            if axis.ndim!=1 or not 2<=len(axis)<=500 or not np.all(np.isfinite(axis)) or not np.all(np.diff(axis)>0):raise UnsupportedData('unsupported_grid','Only finite strictly increasing rectilinear axes are supported.')
        steps=np.mod(np.diff(lon),360)
        if lon.ndim!=1 or not 2<=len(lon)<=500 or not np.all(np.isfinite(lon)) or not np.all(steps>0) or float(steps.sum())>=360 or not -90<=lat[0]<lat[-1]<=90:raise UnsupportedData('unsupported_grid','Source coordinates must be rectilinear with one eastward longitude cycle.')
        return source,hashlib.sha256(body).hexdigest(),(levels,lat,lon)

    def dataset(self,key):
        source,digest,axes=self.source(key);spec=SPECS[key];levels,lat,lon=axes
        times=sorted({f['time'] for f in source['files']})
        intervals=[]
        for t in times:
            d=datetime.fromisoformat(t.replace('Z','+00:00'));start=f'{d.year:04}-{d.month:02}-01T00:00:00Z';end=f'{d.year+(d.month==12):04}-{d.month%12+1:02}-01T00:00:00Z';intervals.append([start,end])
        return {'id':key,**spec,'source_sha256':digest,'source_longitude_convention':'0 to 360' if np.all(lon>=0) else 'Cyclic -180 to 180, native storage starts at 20.5 degrees east','latitude_range':[float(lat[0]),float(lat[-1])],'level_range':[float(levels[0]),float(levels[-1])],'levels':levels.tolist(),'times':times,'intervals':intervals,'shape':[len(levels),len(lat),len(lon)],'instrument_availability':'No observation library is supplied for arbitrary regional requests. Original profiles remain available in the five curated cases.','retrieved_at':source['retrieved_at']}

    def catalog(self):
        datasets=[self.dataset(k) for k in SPECS if (self.root/k/'source.json').is_file()]
        return {'schema_version':'p15-1','method':WIDER_METHOD,'datasets':datasets,'limits':{'native_values':MAX_NATIVE_VALUES,'longitude_degrees':90,'latitude_degrees':40,'display_axis':40,'preview_axis':12,'native_cache_bytes':self.native.max_bytes,'response_cache_bytes':self.responses.max_bytes,'concurrent_operations_per_instance':4,'pack_bytes':MAX_PACK_BYTES},'presets':[{'id':'north-atlantic','label':'North Atlantic','bounds':[-65,25,-45,40]},{'id':'south-atlantic','label':'South Atlantic','bounds':[-35,-35,-15,-20]},{'id':'southern-indian','label':'Southern Indian Ocean','bounds':[60,-55,80,-40]},{'id':'dateline','label':'Across the date line','bounds':[170,-5,-170,5]},{'id':'indian','label':'Central Indian Ocean','bounds':[60,-10,80,5]}]}

    def selection(self,q):
        source,digest,(z,y,x)=self.source(q.dataset);spec=SPECS[q.dataset]
        if q.variable not in spec['variables']:raise UnsupportedData('unsupported_variable','This variable is not supplied by the selected source.')
        if not y[0]<=q.south<q.north<=y[-1]:raise UnsupportedData('outside_coverage','Latitude bounds exceed this source. Polar coverage is not implied.')
        if q.level_min<z[0] or q.level_max>z[-1]:raise UnsupportedData('outside_coverage','The vertical interval must lie within the source range.')
        width=(q.east-q.west)%360;unwrapped=q.west+np.mod(x-q.west,360)
        xi=np.flatnonzero(unwrapped<=q.west+width+1e-10);xi=xi[np.argsort(unwrapped[xi])]
        yi=np.flatnonzero((y>=q.south)&(y<=q.north));zi=np.flatnonzero((z>=q.level_min)&(z<=q.level_max))
        if min(len(xi),len(yi),len(zi))<1:raise UnsupportedData('empty_subset','No native coordinate falls within the requested bounds.')
        if min(len(xi),len(yi))<2:raise UnsupportedData('empty_subset','Choose an area containing at least two native coordinates on each horizontal axis.')
        count=len(xi)*len(yi)*len(zi)
        if count>MAX_NATIVE_VALUES:raise UnsupportedData('subset_too_large',f'This selection contains {count:,} native values; the limit is {MAX_NATIVE_VALUES:,}. Reduce the area or vertical interval.')
        times=sorted({f['time'] for f in source['files']})
        if q.time_index>=len(times):raise UnsupportedData('unsupported_time','Select a listed source month.')
        record=next((f for f in source['files'] if f['source_variable']==spec['variables'][q.variable]['source'] and f['time']==times[q.time_index]),None)
        if not record:raise UnsupportedData('unsupported_variable','This variable and month are unavailable.')
        return source,digest,(z[zi],y[yi],unwrapped[xi]),(zi,yi,xi),record

    def preview(self,q):
        _,digest,axes,indices,record=self.selection(q)
        return {'schema_version':'p15-1','method':WIDER_METHOD,'query':q.model_dump(),'source_sha256':digest,'shape':[len(a) for a in axes],'native_values':math.prod(len(a) for a in axes),'actual_bounds':[float(axes[2][0]),float(axes[1][0]),float(axes[2][-1]),float(axes[1][-1])],'actual_levels':[float(axes[0][0]),float(axes[0][-1])],'time':record['time'],'estimated_native_json_bytes':math.prod(len(a) for a in axes)*24,'instrument_availability':'No observations bundled for this regional selection.','crosses_dateline':q.east<q.west}

    def _array(self,q,record):
        path=self.root/q.dataset/record['path']
        if path.parent.resolve()!=(self.root/q.dataset).resolve() or not record['path'].endswith('.f32.gz'):raise UnsupportedData('case_integrity_error','Source path failed validation.')
        try:packed=path.read_bytes()
        except OSError as exc:raise UnsupportedData('source_unavailable','The prepared regional field is unavailable. Try again after the source is restored.') from exc
        if hashlib.sha256(packed).hexdigest()!=record['sha256']:raise UnsupportedData('case_integrity_error','Regional source failed its integrity check.')
        key=(q.dataset,record['sha256']);cached=self.native.get(key)
        if cached is not None:return cached
        with self.load_lock:
            cached=self.native.get(key)
            if cached is not None:return cached
            shape=tuple(record['shape']);expected=math.prod(shape)*4
            if len(shape)!=3 or expected>20_000_000:raise UnsupportedData('case_integrity_error','Native array exceeds its declared bound.')
            with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:raw=stream.read(expected+1)
            if len(raw)!=expected:raise UnsupportedData('case_integrity_error','Native byte length is inconsistent.')
            values=np.frombuffer(raw,dtype='<f4').reshape(shape);values.flags.writeable=False
            self.native.put(key,values,values.nbytes);return values

    def _subset(self,q):
        source,digest,axes,indices,record=self.selection(q)
        # Validate source bytes before every response-cache hit.
        native=self._array(q,record)
        key=(digest,record['sha256'],canonical(q.model_dump()),WIDER_METHOD)
        cached=self.responses.get(key)
        if cached is not None:return json.loads(cached)
        z,y,x=axes;zi,yi,xi=indices
        limit=12 if q.resolution=='preview' else 40
        def take(n,k):return np.unique(np.rint(np.linspace(0,n-1,min(n,k))).astype(int))
        iz=take(len(z),8) if q.resolution=='preview' else np.arange(len(z))
        iy=take(len(y),limit) if q.resolution!='native' else np.arange(len(y))
        ix=take(len(x),limit) if q.resolution!='native' else np.arange(len(x))
        selected=native[np.ix_(zi[iz],yi[iy],xi[ix])].astype(np.float64)
        spec=SPECS[q.dataset]['variables'][q.variable]
        valid=np.isfinite(selected)&(selected!=float(np.float32(9.969209968386869e36)))
        if 'range' in spec:valid&=(selected>=spec['range'][0])&(selected<=spec['range'][1])
        if np.any(valid&(np.abs(selected)>1e10)):raise UnsupportedData('case_integrity_error','Unrecognised source fill or invalid quantity.')
        values=selected*spec['scale']+spec['offset'];flat=values.ravel();mask=valid.ravel()
        result={'schema_version':'p15-1','method':WIDER_METHOD,'query':q.model_dump(),'dataset':self.dataset(q.dataset),'source_sha256':digest,'file_sha256':record['sha256'],'source_record':record,'shape':list(values.shape),'levels':z[iz].tolist(),'latitude':y[iy].tolist(),'longitude':x[ix].tolist(),'source_indices':{'level':zi[iz].tolist(),'latitude':yi[iy].tolist(),'longitude':xi[ix].tolist()},'native_shape':[len(a) for a in axes],'values':[float(v) if ok else None for v,ok in zip(flat,mask)],'valid_count':int(mask.sum()),'units':spec['units'],'kind':SPECS[q.dataset]['kind'],'time':record['time'],'processing':['Original coordinate selection; no interpolation or missing-value replacement.',f"Source transformation: value * {spec['scale']} + {spec['offset']} in float64.",'Source longitudes are unwrapped eastward from the requested west bound; source indices retain the original storage positions.','Preview/display decimates only coordinates; native export and point profiles retain all selected source levels and positions.']}
        encoded=canonical(result).encode();self.responses.put(key,encoded,len(encoded));return result

    def subset(self,q):
        with self.capacity():return self._subset(q)

    def profile(self,request):
        q=request.query.model_copy(update={'resolution':'native'})
        with self.capacity():
            result=self._subset(q);lon=q.west+(request.longitude-q.west)%360
            if not result['longitude'][0]<=lon<=result['longitude'][-1] or not result['latitude'][0]<=request.latitude<=result['latitude'][-1]:raise UnsupportedData('outside_coverage','The selected point is outside the native regional grid.')
            x=min(range(len(result['longitude'])),key=lambda i:abs(result['longitude'][i]-lon));y=min(range(len(result['latitude'])),key=lambda i:abs(result['latitude'][i]-request.latitude));ny,nx=result['shape'][1:]
            return {'schema_version':'p15-1','method':WIDER_METHOD,'source_sha256':result['source_sha256'],'variable':q.variable,'units':result['units'],'vertical_units':result['dataset']['vertical_units'],'longitude':result['longitude'][x],'latitude':result['latitude'][y],'levels':result['levels'],'values':[result['values'][(z*ny+y)*nx+x] for z in range(result['shape'][0])],'source_indices':{'longitude':result['source_indices']['longitude'][x],'latitude':result['source_indices']['latitude'][y],'level':result['source_indices']['level']},'selection':'Nearest native coordinate inside selected bounds; no interpolation.'}

    def pack(self,q):
        with self.capacity():
            q=q.model_copy(update={'resolution':'native'});data=self._subset(q)
            uncertainty=self._subset(q.model_copy(update={'variable':'oxygen_uncertainty'})) if q.variable=='oxygen' else None
            payload=canonical({'field':data,'uncertainty':uncertainty})
            if len(payload.encode())>MAX_PACK_BYTES:raise UnsupportedData('subset_too_large','Portable pack exceeds 4 MB. Reduce the selected region.')
            return WiderPack(payload_text=payload,sha256=hashlib.sha256(payload.encode()).hexdigest()).model_dump()

    def replay(self,pack):
        if hashlib.sha256(pack.payload_text.encode()).hexdigest()!=pack.sha256:raise UnsupportedData('invalid_pack','Pack checksum does not match.')
        try:payload=json.loads(pack.payload_text);q=WiderQuery.model_validate(payload['field']['query'])
        except (KeyError,ValueError,TypeError) as exc:raise UnsupportedData('invalid_pack','Pack contains unsupported settings.') from exc
        current=self.pack(q)
        if current['sha256']!=pack.sha256:raise UnsupportedData('source_mismatch','Recalculation differs from the saved source, method or results. The original pack remains unchanged.')
        return {'matched':True,'method':WIDER_METHOD,'sha256':pack.sha256}


def regional_csv(pack):
    data=json.loads(pack['payload_text'])['field'];buf=io.StringIO();w=csv.writer(buf,lineterminator='\n')
    w.writerow(['source_longitude_index','source_latitude_index','source_level_index','longitude_unwrapped_deg_east','latitude_deg_north','vertical_coordinate',data['dataset']['vertical_units'],data['query']['variable'],data['units']])
    i=0
    for z,level in enumerate(data['levels']):
        for y,lat in enumerate(data['latitude']):
            for x,lon in enumerate(data['longitude']):
                w.writerow([data['source_indices']['longitude'][x],data['source_indices']['latitude'][y],data['source_indices']['level'][z],lon,lat,level,data['dataset']['vertical_units'],data['values'][i],data['units']]);i+=1
    return buf.getvalue()
