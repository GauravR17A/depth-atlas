"""Read a bounded teaching example only while its source identities still match."""
import json
import math
from functools import lru_cache
from science.contracts import UnsupportedData

class GuideStore:
    def __init__(self,cases): self.cases=cases

    @lru_cache(maxsize=1)
    def read(self):
        path=self.cases.root/'guides/indian-ocean.json'
        if not path.is_file(): raise UnsupportedData('guide_unavailable','The guided example is unavailable. You can still explore available cases.')
        guide=json.loads(path.read_text(encoding='utf8'))
        for c in guide['columns']:
            m,sha=self.cases.require(c['case_id']);x,y,z=c['point']
            if sha!=c['manifest_sha256'] or c['depth_m']!=m.coordinates.depth_m or c['time']!=m.coordinates.times[c['time_index']] or c['latitude']!=m.coordinates.latitude[y] or c['longitude']!=m.coordinates.longitude[x]:
                raise UnsupportedData('case_integrity_error','The guided example no longer matches its source case.')
            values=self.cases._read_array(c['case_id'],'analytical','temperature',c['time_index'])
            ny,nx=len(m.coordinates.latitude),len(m.coordinates.longitude)
            actual=[values[(k*ny+y)*nx+x] for k in range(len(m.coordinates.depth_m))]
            if [v if math.isfinite(v) else None for v in actual]!=c['temperature_c']:
                raise UnsupportedData('case_integrity_error','The guided profile no longer matches native model values.')
        return guide
