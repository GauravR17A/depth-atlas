"""Trusted scalar-product registrations. Uploaded files cannot execute plugins."""
from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np
from pydantic import Field, model_validator

from science.contracts import Contract, UnsupportedData


class ProductMetadata(Contract):
    schema_version: Literal['1'] = '1'
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,63}$')
    label: str
    kind: Literal['derived', 'ml_derived']
    units: str
    definition: str
    method_id: str
    inputs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    model_version: str | None = None
    training_data_reference: str | None = None
    validation_reference: str | None = None

    @model_validator(mode='after')
    def ml_provenance(self):
        if self.kind == 'ml_derived' and not all((self.model_version, self.training_data_reference, self.validation_reference)):
            raise ValueError('External ML products require model, training-data and validation references.')
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError('Product inputs must be unique.')
        return self


@dataclass(frozen=True)
class ScalarProduct:
    metadata: ProductMetadata
    calculate: Callable[[dict[str, np.ndarray]], np.ndarray]


class ProductRegistry:
    def __init__(self):
        self._products: dict[str, ScalarProduct] = {}

    def register(self, product: ScalarProduct):
        if product.metadata.id in self._products:
            raise ValueError('A product ID cannot replace an existing registration.')
        self._products[product.metadata.id] = product

    def get(self, product_id: str) -> ScalarProduct:
        if product_id not in self._products:
            raise UnsupportedData('unsupported_variable', 'This product is not registered.')
        return self._products[product_id]

    def catalog(self):
        return [p.metadata.model_dump() for p in self._products.values()]

    def evaluate(self, product_id: str, inputs: dict[str, np.ndarray]):
        product = self.get(product_id)
        if set(inputs) != set(product.metadata.inputs):
            raise UnsupportedData('incompatible_variables', 'Product dependencies do not match its contract.')
        arrays = [np.asarray(inputs[k], dtype=np.float64) for k in product.metadata.inputs]
        if not arrays or len({a.shape for a in arrays}) != 1:
            raise UnsupportedData('incompatible_grid', 'Product inputs must share the same native grid.')
        result = np.asarray(product.calculate(dict(zip(product.metadata.inputs, arrays))), dtype=np.float64)
        if result.shape != arrays[0].shape:
            raise UnsupportedData('incompatible_grid', 'Product output changed the grid.')
        valid = np.logical_and.reduce([np.isfinite(a) for a in arrays])
        if not np.all(np.isfinite(result[valid])):
            raise UnsupportedData('invalid_product', 'Product returned non-finite values for valid inputs.')
        return np.where(valid, result, np.nan)


PRODUCTS = ProductRegistry()
PRODUCTS.register(ScalarProduct(ProductMetadata(
    id='horizontal_kinetic_energy', label='Horizontal kinetic energy', kind='derived', units='m²/s²',
    definition='Kinetic energy per unit mass from the two horizontal model currents: (u² + v²) / 2.',
    method_id='horizontal-ke-v1', inputs=['eastward_velocity', 'northward_velocity'],
    limitations=['Excludes vertical velocity, which is not supplied.', 'Not eddy kinetic energy: no mean flow has been subtracted.', 'A model-derived quantity, not an observation or an ML prediction.'],
), lambda fields: (fields['eastward_velocity'] ** 2 + fields['northward_velocity'] ** 2) / 2))
