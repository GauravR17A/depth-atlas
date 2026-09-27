"""Request-scoped, cancellable drift calculations and bounded warm-result cache."""
from collections import OrderedDict
from datetime import datetime, timedelta
from functools import lru_cache
import math
from threading import Lock
import numpy as np
from science.contracts import UnsupportedData
from science.drift_contracts import METHOD
from science.drift import VelocityField, integrate, METHODS, LIMITATIONS, OUTPUT_SECONDS

class DriftStore:
    def __init__(self,cases):
        self.cases=cases
        self.cache=OrderedDict()
        self.lock=Lock()

    def validate(self,case_id,query):
        m,digest=self.cases.require(case_id);c=m.coordinates
        if not {'eastward_velocity','northward_velocity'} <= set(m.case.variables):
            raise UnsupportedData('unsupported_velocity','Drift requires both historical current components. This case supplies potential temperature only.')
        if query.depth_index>=len(c.depth_m) or c.depth_m[query.depth_index]>1000:
            raise UnsupportedData('unsupported_depth','Drift supports native depths from 0 to 1000 metres.')
        if query.start_time_index>=len(c.times):
            raise UnsupportedData('unsupported_time','Choose an available historical starting snapshot.')
        end=self.seconds(case_id)[query.start_time_index]+query.duration_hours*3600
        if end>self.seconds(case_id)[-1]:
            raise UnsupportedData('forcing_exhausted','This duration exceeds the supplied currents. Choose an earlier start or shorter duration; the run has not been shortened.')
        bounds=[c.longitude[0],c.latitude[0],c.longitude[-1],c.latitude[-1]]
        def point(x,y):
            return math.isfinite(x) and math.isfinite(y) and bounds[0]<=x<=bounds[2] and bounds[1]<=y<=bounds[3]
        def box(b):
            return b[0]<b[2] and b[1]<b[3] and point(b[0],b[1]) and point(b[2],b[3])
        r=query.release
        if not (point(r.longitude,r.latitude) if r.kind=='point' else box(r.bounds)):
            raise UnsupportedData('outside_coverage','Choose a release point or nonempty release box inside the selected study area.')
        if query.target_bounds is not None and not box(query.target_bounds):
            raise UnsupportedData('invalid_target','Choose a nonempty target box inside the selected study area.')
        return m,digest

    def seconds(self,case_id):
        m,_=self.cases.require(case_id)
        dates=[datetime.fromisoformat(t.replace('Z','+00:00')) for t in m.coordinates.times]
        return [(d-dates[0]).total_seconds() for d in dates]

    @lru_cache(maxsize=4)
    def field(self,case_id,depth_index):
        m,_=self.cases.require(case_id);c=m.coordinates
        for name,standard in [('eastward_velocity','eastward_sea_water_velocity'),('northward_velocity','northward_sea_water_velocity')]:
            spec=next((v for v in m.variables if v.id==name),None)
            if spec is None or spec.units!='m/s' or spec.standard_name!=standard:
                raise UnsupportedData('unsupported_velocity','The drift adapter requires declared eastward/northward currents in m/s.')
        shape=(len(c.depth_m),len(c.latitude),len(c.longitude))
        fields=[np.stack([np.asarray(self.cases._read_array(case_id,'analytical',name,t)).reshape(shape)[depth_index].copy()
                          for t in range(len(c.times))]) for name in ('eastward_velocity','northward_velocity')]
        return VelocityField(c.longitude,c.latitude,self.seconds(case_id),*fields)

    def context(self,case_id,depth_index,time_index):
        m,digest=self.cases.require(case_id);c=m.coordinates
        if not 0<=depth_index<len(c.depth_m) or c.depth_m[depth_index]>1000:
            raise UnsupportedData('unsupported_depth','Drift supports native depths from 0 to 1000 metres.')
        if not 0<=time_index<len(c.times):raise UnsupportedData('unsupported_time','Choose an available source snapshot.')
        field=self.field(case_id,depth_index)
        xi=sorted(set(range(0,len(c.longitude),4))|{len(c.longitude)-1})
        yi=sorted(set(range(0,len(c.latitude),4))|{len(c.latitude)-1})
        def values(data):return [float(v) if np.isfinite(v) else None for v in data[time_index][np.ix_(yi,xi)].ravel()]
        return dict(case_id=case_id,manifest_sha256=digest,depth_m=c.depth_m[depth_index],model_time=c.times[time_index],
                    bounds=[c.longitude[0],c.latitude[0],c.longitude[-1],c.latitude[-1]],longitude=[c.longitude[i] for i in xi],
                    latitude=[c.latitude[i] for i in yi],u=values(field.u),v=values(field.v),shape=[len(yi),len(xi)])

    def stream(self,case_id,query):
        m,digest=self.validate(case_id,query);key=(METHOD,digest,query.model_dump_json())
        with self.lock:
            cached=self.cache.get(key)
            if cached:self.cache.move_to_end(key)
        if cached:
            yield dict(type='progress',completed_steps=cached['total_steps'],total_steps=cached['total_steps'])
            yield dict(type='result',result=cached)
            return
        field=self.field(case_id,query.depth_index)
        start=self.seconds(case_id)[query.start_time_index]
        for event in integrate(field,query,start):
            if event['type']=='progress':yield event
            else:
                start_time=m.coordinates.times[query.start_time_index]
                end_time=(datetime.fromisoformat(start_time.replace('Z','+00:00'))+timedelta(hours=query.duration_hours)).isoformat().replace('+00:00','Z')
                result=dict(schema_version='1',kind='drift_run',method_version=METHOD,case_id=case_id,manifest_sha256=digest,simulated=True,
                            query=query.model_dump(mode='json'),depth_m=m.coordinates.depth_m[query.depth_index],start_time=start_time,end_time=end_time,
                            forcing_times=m.coordinates.times,bounds=[field.longitude[0],field.latitude[0],field.longitude[-1],field.latitude[-1]],
                            background=self.context(case_id,query.depth_index,query.start_time_index),output_interval_seconds=math.lcm(OUTPUT_SECONDS,query.dt_seconds),
                            completed_steps=event['completed_steps'],total_steps=event['total_steps'],particles=event['particles'],summary=event['summary'],
                            methods=METHODS,limitations=LIMITATIONS)
                with self.lock:
                    self.cache[key]=result
                    while len(self.cache)>4:self.cache.popitem(last=False)
                yield dict(type='result',result=result)

    def run(self,case_id,query):
        for event in self.stream(case_id,query):
            if event['type']=='result':return event['result']
        raise RuntimeError('Drift calculation ended without a result.')
