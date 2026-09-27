"""Independent packed-file checks. Does not use production adapters or stores."""
from pathlib import Path
import gzip
import hashlib
import json
import netCDF4
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def main():
    checks=[];native={}
    for cid,rawdir in [('bay-bengal-2024-01','data/raw'),('arabian-sea-2024-01','data/raw/arabian-sea')]:
        pack=ROOT/'casepacks'/cid;m=json.loads((pack/'manifest.json').read_text(encoding='utf8'))
        journal=json.loads((ROOT/rawdir/'acquisition.json').read_text())
        models=sorted([r for r in journal['files'] if r['archive_kind']=='packed_source_subset_reconstructed_as_netcdf'],key=lambda r:r['time'])
        for t,r in enumerate(models):
            path=ROOT/r['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
            with netCDF4.Dataset(path) as ds:
                for src,key in [('water_temp','temperature'),('salinity','salinity'),('water_u','eastward_velocity'),('water_v','northward_velocity')]:
                    var=ds[src];var.set_auto_maskandscale(False);raw=np.asarray(var[:]);a=raw.astype(np.float64)*float(var.scale_factor)+float(var.add_offset);a[raw==var._FillValue]=np.nan;a=a[0]
                    analytical=np.frombuffer(gzip.decompress((pack/'analytical'/f'{key}-{t}.bin.gz').read_bytes()),dtype='<f8').reshape(a.shape)
                    np.testing.assert_array_equal(a,analytical)
                    yi=m['representations']['display']['latitude_source_indices'];xi=m['representations']['display']['longitude_source_indices']
                    visual=np.frombuffer(gzip.decompress((pack/'display'/f'{key}-{t}.bin.gz').read_bytes()),dtype='<f4').reshape(len(a),len(yi),len(xi))
                    np.testing.assert_array_equal(a[:,yi,:][:,:,xi].astype('float32'),visual)
                    if key=='temperature' and t==1:native[cid]=a
                    checks.append(dict(case_id=cid,time_index=t,variable=key,values=int(a.size),native_exact=True,display_exact=True,missing=int(np.isnan(a).sum())))
                for source,axis in [('lat','latitude'),('lon','longitude'),('depth','depth_m')]:
                    np.testing.assert_array_equal(ds[source][:],m['coordinates'][axis])
                assert str(netCDF4.num2date(ds['time'][0],ds['time'].units)).replace(' ','T')+'Z'==m['coordinates']['times'][t]
        with netCDF4.Dataset(ROOT/'casepacks/standards'/f'{cid}.nc') as exchange:
            np.testing.assert_array_equal(exchange['temperature'][1].filled(np.nan),native[cid])
    guide=json.loads((ROOT/'casepacks/guides/indian-ocean.json').read_text())
    for c in guide['columns']:
        x,y,z=c['point'];actual=native[c['case_id']][:,y,x]
        np.testing.assert_array_equal(actual,np.array([np.nan if v is None else v for v in c['temperature_c']]))
    # Independent full vectorized comparison of all valid pairs, no production selector.
    a,b=[native[c['case_id']] for c in guide['columns']];z=19
    best=(-1,None,None)
    for start in range(0,a.shape[1]*a.shape[2],64):
        aa=a[0].ravel()[start:start+64,None];ad=a[z].ravel()[start:start+64,None]
        eligible=np.isfinite(aa+ad)&np.isfinite(b[0].ravel()+b[z].ravel())[None,:]&(np.abs(aa-b[0].ravel()[None,:])<=.05)
        delta=np.where(eligible,np.abs(ad-b[z].ravel()[None,:]),-1)
        i,j=np.unravel_index(np.argmax(delta),delta.shape)
        if delta[i,j]>best[0]:best=(float(delta[i,j]),start+i,int(j))
    for c,flat in zip(guide['columns'],best[1:]):
        assert c['point'][:2]==[flat%63,flat//63]
    result=dict(date='2026-09-22',checks=checks,checked_native_values=sum(r['values'] for r in checks),teaching_pair_global_selection_verified=True,difference_at_100m_c=best[0],original_files=[dict(path=r['path'],sha256=r['sha256']) for r in journal['files']])
    (ROOT/'docs/evidence/p09-source-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','original_files')},indent=2))
if __name__=='__main__':main()
