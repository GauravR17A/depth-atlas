"""Reacquire genuine P04 examples, recording source identity before preparation."""
from pathlib import Path
from urllib.request import urlopen
from datetime import datetime,timezone
import hashlib,json,io,zipfile

ROOT=Path(__file__).resolve().parents[1]
GLIDER='https://gliders.ioos.us/erddap/tabledap/ru29-20240419T1430-delayed.nc?trajectory,profile_id,time,latitude,longitude,precise_time,precise_lat,precise_lon,pressure,temperature,salinity,depth,pressure_qartod_summary_flag,temperature_qartod_summary_flag,salinity_qartod_summary_flag&time>=2024-04-19T14:30:00Z&time<=2024-04-19T16:30:00Z'
SOURCES={
    'SR6903091_100.nc':'https://data-argo.ifremer.fr/dac/coriolis/6903091/profiles/SR6903091_100.nc',
    'glider-ru29.nc':GLIDER,
    'i06sb_ct1.zip':'https://cchdo.ucsd.edu/data/6331/i06sb_ct1.zip',
}

def acquire():
    out=ROOT/'data/raw/instruments';out.mkdir(parents=True,exist_ok=True);records=[]
    for name,url in SOURCES.items():
        path=out/name
        if not path.exists():
            with urlopen(url,timeout=45) as response:body=response.read(10_000_001)
            if len(body)>10_000_000:raise ValueError('Source download exceeds acquisition budget.')
            path.write_bytes(body)
        body=path.read_bytes();records.append({'file':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'source_url':url})
    # Only an explicitly named member is read; nothing is extracted using archive paths.
    member='i06sb_00001_00001_ct1.csv'
    with zipfile.ZipFile(io.BytesIO((out/'i06sb_ct1.zip').read_bytes())) as archive:
        if archive.getinfo(member).file_size>2_000_000:raise ValueError('CTD cast too large.')
        (out/'ctd-station.csv').write_bytes(archive.read(member))
    (out/'glider-url.txt').write_text(GLIDER,encoding='utf8')
    journal={'recorded_at':datetime.now(timezone.utc).isoformat(),'files':records,'ctd_archive_member':member,'note':'Existing files are preserved. Compare hashes with the published P04 index before using a fresh upstream revision.'}
    (out/'acquisition.json').write_text(json.dumps(journal,indent=2)+'\n',encoding='utf8')
    print(json.dumps(journal,indent=2))

if __name__=='__main__':acquire()
