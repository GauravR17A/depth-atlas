"""Explicit trusted adapter registry. Modules are installed by maintainers, never uploaded."""
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from science.contracts import UnsupportedData


@dataclass(frozen=True)
class Adapter:
    id: str
    version: str
    entrypoint: str
    input_contract: str
    output_contract: str = 'ModelGrid/native-float64/v1'


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, Adapter] = {}

    def register(self, adapter: Adapter):
        if adapter.id in self._adapters:
            raise ValueError('An adapter ID cannot overwrite another registration.')
        self._adapters[adapter.id] = adapter

    def load(self, adapter_id: str, path: Path):
        if adapter_id not in self._adapters:
            raise UnsupportedData('unsupported_adapter', 'Choose a registered data adapter.')
        module, function = self._adapters[adapter_id].entrypoint.split(':')
        return getattr(import_module(module), function)(path)

    def catalog(self):
        from dataclasses import asdict
        return [asdict(a) for a in self._adapters.values()]


ADAPTERS = AdapterRegistry()
ADAPTERS.register(Adapter('hycom-rectilinear', '1', 'adapters.cf_model:load_model', 'HYCOM named rectilinear fields; metres; Gregorian time; explicit source units'))
ADAPTERS.register(Adapter('cf-exchange', '1', 'adapters.cf_exchange:load_exchange', 'CF-1.10 named rectilinear fields; latitude/longitude axes; dimensionless practical salinity'))
ADAPTERS.register(Adapter('godas-monthly-subset','1','adapters.wider:load_godas','Pinned native GODAS monthly potential temperature and source salinity; original axes and source hashes','WiderSource/p15-1'))
ADAPTERS.register(Adapter('gobai-oxygen','1','adapters.wider:load_gobai','Pinned GOBAI-O2 v2.2 monthly oxygen and provider uncertainty; native pressure in dbar','WiderSource/p15-1'))
