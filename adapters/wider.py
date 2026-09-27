"""Trusted prepared-source adapters. No user-supplied Python or URLs execute."""
import json
from pathlib import Path
from science.contracts import UnsupportedData


def _load(path:Path, variables:set[str], axis:str):
    source=json.loads(path.read_text(encoding='utf-8'))
    if not {'lat','lon',axis} <= set(source.get('axes',{})) or not source.get('files'):
        raise UnsupportedData('unsupported_grid','Prepared native coordinates and source records are required.')
    if {f['source_variable'] for f in source['files']} != variables:
        raise UnsupportedData('incompatible_variables','Prepared variables differ from the registered source adapter.')
    expected=[len(source['axes'][k]) for k in (axis,'lat','lon')]
    if any(f['shape']!=expected for f in source['files']):
        raise UnsupportedData('unsupported_grid','Fields must share the declared rectilinear grid.')
    return source


def load_godas(path):return _load(path,{'pottmp','salt'},'depth')
def load_gobai(path):return _load(path,{'oxy','uncer'},'pres')
