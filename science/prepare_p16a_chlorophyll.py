"""Add a genuine, geographically overlapping BGC profile without altering model packs."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from adapters.instruments import parse_instruments

ROOT = Path(__file__).resolve().parents[1]
NAME = 'SR1902594_034.nc'
SOURCE = 'https://data-argo.ifremer.fr/dac/coriolis/1902594/profiles/' + NAME


def prepare():
    raw = ROOT / 'data/raw/instruments' / NAME
    if not raw.exists():
        with urlopen(SOURCE, timeout=40) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000: raise ValueError('Source exceeds the supported file budget.')
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(body)
    body = raw.read_bytes()
    if hashlib.sha256(body).hexdigest() != '1368b43fca3d535e3d4745cfcc0c477706ce5e121137ae18e0bf4ac9a613bc2c':
        raise ValueError('Source differs from the reviewed P16A download. Review its revision before publishing.')
    parsed = parse_instruments(body, NAME, SOURCE)
    out = ROOT / 'casepacks/instruments'
    index_path = out / 'import-examples.json'
    index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {'schema_version':'1','examples':[]}
    for p in parsed.profiles:
        assert 'chlorophyll' in p.parameters and p.parameters['chlorophyll'].accepted_count > 0
        p.collection = 'Bay of Bengal BGC · March 2024'
        p.metadata.update(provider='Argo GDAC / Coriolis', acquired_date=datetime.now(timezone.utc).date().isoformat(), source_url=SOURCE)
        p.warnings.extend([
            'This March 2024 profile is inside the Bay of Bengal model rectangle, but outside its January 2024 time coverage. It is not a simultaneous model comparison.',
            'CHLA_ADJUSTED is the provider-derived chlorophyll estimate from fluorescence. It is not CHLA_FLUORESCENCE or a chlorophyll model field. Source calibration details are retained; source reprocessing can change later downloads.',
        ])
        target = ROOT / 'docs/evidence/p16a-chlorophyll-profile.json'
        # A repeat of this preparation must preserve the published acquisition date.
        if target.exists(): p.metadata['acquired_date'] = json.loads(target.read_text(encoding='utf-8'))['metadata']['acquired_date']
        target.write_text(p.model_dump_json(), encoding='utf-8')
    (out / 'examples' / NAME).write_bytes(body)
    record = {'name': NAME, 'format': parsed.format, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
              'source_url': SOURCE, 'collection': 'Bay of Bengal BGC · March 2024; chlorophyll, separate from January model dates'}
    existing = next((x for x in index['examples'] if x['name'] == NAME), None)
    if existing and existing['sha256'] != record['sha256']: raise ValueError('Upstream source changed; review and version before replacing the pinned example.')
    index['examples'] = [x for x in index['examples'] if x['name'] != NAME] + [record]
    index_path.write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    evidence = {'source': record, 'profiles': [p.model_dump(include={'id', 'time', 'latitude', 'longitude', 'parameters', 'samples'}) for p in parsed.profiles]}
    dest = ROOT / 'docs/evidence/p16a-chlorophyll-source.json'
    dest.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__': prepare()
