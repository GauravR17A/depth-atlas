"""Bounded fixed-depth advection, explicit source interpolation and boundaries."""
import math
import numpy as np
from science.contracts import UnsupportedData
from science.vendor.parcels_rk4 import rk4_step

METRES_PER_DEGREE = 1852.0 * 60.0
OUTPUT_SECONDS = 1800

def cosine_degrees(latitude):
    """Fixed-order binary64 Taylor evaluation; supported absolute latitude <=30.

    Truncation at x^20 has error <2e-27 on this interval. Floating-point
    roundoff remains and is independently checked; no platform libm cosine.
    """
    x = np.asarray(latitude, dtype=np.float64) * (math.pi / 180.0)
    z = x*x
    result = np.zeros_like(z) + 1.0 / math.factorial(20)
    for n in range(9, -1, -1):
        result = result*z + ((-1.0)**n) / math.factorial(2*n)
    return result

class VelocityField:
    def __init__(self, longitude, latitude, times, u, v):
        self.longitude = np.asarray(longitude, dtype=np.float64)
        self.latitude = np.asarray(latitude, dtype=np.float64)
        self.times = np.asarray(times, dtype=np.float64)
        self.u, self.v = np.asarray(u, dtype=np.float64), np.asarray(v, dtype=np.float64)
        expected = (len(self.times), len(self.latitude), len(self.longitude))
        if (min(expected)<2 or self.u.shape != expected or self.v.shape != expected
            or any(not np.isfinite(a).all() or not (np.diff(a)>0).all() for a in (self.longitude,self.latitude,self.times))
            or np.abs(self.latitude).max()>30):
            raise ValueError('Drift requires ascending finite rectilinear coordinates, at least two snapshots and latitude within 30 degrees of the equator.')
        valid = np.isfinite(self.u) & np.isfinite(self.v)
        self.valid_cells = valid[:,:-1,:-1] & valid[:,1:,:-1] & valid[:,:-1,1:] & valid[:,1:,1:]

    def time_bracket(self, time):
        if not self.times[0] <= time <= self.times[-1]:
            raise UnsupportedData('forcing_exhausted', 'The requested duration exceeds the supplied historical current data.')
        lo = min(int(np.searchsorted(self.times, time, side='right')-1),len(self.times)-2)
        f = (time-self.times[lo])/(self.times[lo+1]-self.times[lo])
        return lo, f

    def indices(self, points):
        x = np.clip(np.searchsorted(self.longitude,points[:,0],side='right')-1,0,len(self.longitude)-2)
        y = np.clip(np.searchsorted(self.latitude,points[:,1],side='right')-1,0,len(self.latitude)-2)
        return x,y

    def sample(self, time, points):
        points = np.asarray(points,dtype=np.float64).reshape(-1,2)
        ti,ft = self.time_bracket(time)
        outside = (~np.isfinite(points).all(axis=1) | (points[:,0]<self.longitude[0]) | (points[:,0]>self.longitude[-1])
                   | (points[:,1]<self.latitude[0]) | (points[:,1]>self.latitude[-1]))
        x,y = self.indices(points)
        fx=(points[:,0]-self.longitude[x])/(self.longitude[x+1]-self.longitude[x])
        fy=(points[:,1]-self.latitude[y])/(self.latitude[y+1]-self.latitude[y])
        valid = (self.valid_cells[ti,y,x] if ft==0 else self.valid_cells[ti+1,y,x] if ft==1 else self.valid_cells[ti,y,x]&self.valid_cells[ti+1,y,x])
        values=[]
        for data in (self.u,self.v):
            def at(k):
                a=data[k,y,x]*(1-fx)+data[k,y,x+1]*fx
                b=data[k,y+1,x]*(1-fx)+data[k,y+1,x+1]*fx
                return a*(1-fy)+b*fy
            value=at(ti) if ft==0 else at(ti+1) if ft==1 else at(ti)*(1-ft)+at(ti+1)*ft
            values.append(value)
        status=np.where(outside,1,np.where(valid,0,2)).astype(np.int8)
        uv=np.column_stack(values)/METRES_PER_DEGREE
        uv[:,0] = uv[:,0]/cosine_degrees(points[:,1])
        return np.where((status==0)[:,None],uv,0.0),status

    def segment_status(self, start_time, end_time, a, b):
        """Conservatively require every cell in the endpoint rectangle to be wet.

        Checks the whole temporal interpolation bracket too. This may stop
        earlier than an exact coast intersection; it cannot tunnel a dry cell.
        """
        first=max(0,int(np.searchsorted(self.times,start_time,side='right')-1))
        last=min(len(self.times)-1,int(np.searchsorted(self.times,end_time,side='left')))
        ax,ay=self.indices(a);bx,by=self.indices(b)
        status=np.zeros(len(a),dtype=np.int8)
        for i in range(len(a)):
            wet=self.valid_cells[first:last+1,min(ay[i],by[i]):max(ay[i],by[i])+1,min(ax[i],bx[i]):max(ax[i],bx[i])+1]
            if not wet.all():status[i]=2
        return status

def release_points(query):
    r=query.release
    if r.kind=='point':return np.tile([r.longitude,r.latitude],(query.particle_count,1)).astype(np.float64)
    state=query.seed
    values=[]
    for _ in range(2*query.particle_count):
        state=(1664525*state+1013904223)&0xffffffff
        values.append((state+.5)/4294967296.0)
    normalized=np.array(values).reshape(-1,2)
    w,s,e,n=r.bounds
    return normalized*np.array([e-w,n-s])+np.array([w,s])

def segment_entry(a,b,bounds):
    """First fraction intersecting a closed target rectangle; None if absent."""
    if bounds is None:return None
    lo,hi=0.0,1.0
    for dimension in (0,1):
        delta=b[dimension]-a[dimension];lower=bounds[dimension];upper=bounds[dimension+2]
        if delta==0:
            if not lower<=a[dimension]<=upper:return None
        else:
            t1=(lower-a[dimension])/delta;t2=(upper-a[dimension])/delta
            lo=max(lo,min(t1,t2));hi=min(hi,max(t1,t2))
            if lo>hi:return None
    return lo

def step_distance_km(a,b):
    dx=(b[:,0]-a[:,0])*cosine_degrees((a[:,1]+b[:,1])*.5)
    dy=b[:,1]-a[:,1]
    return np.sqrt(dx*dx+dy*dy)*(METRES_PER_DEGREE/1000.0)

def sequential_mean(values):
    """Pin binary64 addition order across Python3.10/3.12 sum behavior."""
    total=0.0
    count=0
    for value in values:
        total=total+float(value)
        count+=1
    return total/count if count else None

def integrate(field,query,start_seconds):
    """Yield genuine progress every <=12 steps, then immutable particle results."""
    end=start_seconds+query.duration_hours*3600
    field.time_bracket(start_seconds);field.time_bracket(end)
    points=release_points(query);initial=points.copy()
    _,status=field.sample(start_seconds,points)
    valid_release=status==0
    labels=np.where(valid_release,'completed','invalid_release').astype(object)
    active=valid_release.copy()
    stop=np.zeros(len(points));distance=np.zeros(len(points));arrivals=[None]*len(points)
    paths=[[dict(elapsed_seconds=0,longitude=float(p[0]),latitude=float(p[1]))] for p in points]
    for i in np.flatnonzero(active):
        if segment_entry(points[i],points[i],query.target_bounds) is not None:arrivals[i]=0.0
    total=int((end-start_seconds)/query.dt_seconds)
    yield dict(type='progress',completed_steps=0,total_steps=total)
    for step in range(total):
        elapsed=step*query.dt_seconds
        ids=np.flatnonzero(active)
        if len(ids):
            before=points[ids].copy()
            new,failed=rk4_step(field,start_seconds+elapsed,before,query.dt_seconds)
            ok=failed==0
            distance[ids[ok]]+=step_distance_km(before[ok],new[ok])
            for local,i in enumerate(ids):
                if not ok[local]:
                    active[i]=False;labels[i]='left_domain' if failed[local]==1 else 'missing_velocity'
                else:
                    if arrivals[i] is None:
                        entry=segment_entry(before[local],new[local],query.target_bounds)
                        if entry is not None:arrivals[i]=float(elapsed+query.dt_seconds*entry)
                    points[i]=new[local];stop[i]=elapsed+query.dt_seconds
                # Final safe positions are retained even between output frames.
                if not ok[local] or (elapsed+query.dt_seconds)%OUTPUT_SECONDS==0 or step==total-1:
                    p=dict(elapsed_seconds=int(stop[i]),longitude=float(points[i,0]),latitude=float(points[i,1]))
                    if p['elapsed_seconds']!=paths[i][-1]['elapsed_seconds']:paths[i].append(p)
        if (step+1)%12==0 or step==total-1:
            yield dict(type='progress',completed_steps=step+1,total_steps=total)
    reasons={'completed':None,'invalid_release':'The release lacks a finite velocity interpolation stencil. No trajectory was integrated.',
             'left_domain':'An integration stage left the supplied case. Position and stop time are the last accepted step, not a boundary impact.',
             'missing_velocity':'A velocity stencil or traversed cell is missing. Position and stop time are the last accepted step, not a beaching event.'}
    particles=[dict(id=i+1,release_longitude=float(initial[i,0]),release_latitude=float(initial[i,1]),status=str(labels[i]),
                    stop_elapsed_seconds=int(stop[i]),stop_reason=reasons[labels[i]],distance_km=float(distance[i]),
                    arrival_elapsed_seconds=arrivals[i],points=paths[i]) for i in range(len(points))]
    arrived=[a for a in arrivals if a is not None]
    summary=dict(released=len(points),valid_releases=int(valid_release.sum()),
                 **{k:int((labels==k).sum()) for k in reasons},arrived=len(arrived),
                 arrival_fraction=len(arrived)/len(points) if query.target_bounds else None,
                 earliest_arrival_seconds=min(arrived) if arrived else None,latest_arrival_seconds=max(arrived) if arrived else None,
                 mean_distance_km=sequential_mean(distance[valid_release]))
    yield dict(type='complete',particles=particles,summary=summary,completed_steps=total,total_steps=total)

METHODS=[
    'OceanParcels 3.1.4 AdvectionRK4 kernel adapted to a bounded array runner. Four interpolated stage velocities per step. This is not the full Parcels runtime.',
    'Eastward/northward m/s on the supplied rectilinear, collocated z-level grid. No grid rotation or invented vertical velocity. Fixed native depth.',
    'Bilinear space and linear time interpolation on native analytical arrays. A complete finite U/V cell is required. Exact source times use only that snapshot for point sampling.',
    'Spherical velocity conversion uses 111120 metres per degree, matching Parcels. Cosine uses a fixed-order binary64 polynomial for the supported latitude range, independently checked against reference cosine.',
    'All RK4 stages, endpoint and the full rectangle of traversed interpolation cells must be supported. An invalid step is rejected; the particle retains its last accepted position and time. No spatial/time extrapolation.',
    'Seeded box releases are uniform in longitude/latitude, not exactly uniform in area. Point-release particles coincide deterministically. The seed changes release positions only, not their subsequent motion.',
    'Distance accumulates a midpoint spherical-metric approximation along every accepted integration step. Target entry is the first closed-rectangle intersection of an accepted step segment, linearly timed within that step.',
    'Arrival fraction divides by all requested particles, including invalid releases. Mean travel distance uses valid releases only, with explicit left-to-right binary64 addition in particle order. Display frames every lcm(1800, timestep) seconds plus the last accepted position do not control integration.'
]
LIMITATIONS=[
    'Historical passive-tracer simulation, not a live forecast, safe route, rescue probability or observed trajectory.',
    'No sinking, buoyancy, windage, tides beyond the supplied forcing, swimming, diffusion, oil chemistry or vertical transport is added.',
    'Twelve-hourly source snapshots limit temporal detail. Timestep convergence checks numerical integration, not the accuracy of those currents.',
    'Conservative missing-cell handling can terminate before a coastline or actual boundary contact. Missing velocity is not evidence of beaching.',
    'Target entry times are approximate within an integration step. Counts and differences across runs are simulations, not real-world probabilities or calibrated uncertainty.',
    'Independent drifter validation is not established for these checked cases. Browser and numerical checks do not prove real-ocean forecast skill.'
]
