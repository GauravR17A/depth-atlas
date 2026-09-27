"""Portable, bounded original observation inputs. No URLs are fetched."""
import base64
import binascii
import hashlib
from typing import Annotated, Literal

from pydantic import Field
from science.contracts import Contract, UnsupportedData
from science.evidence_contracts import MatchSettings

IMPORT_METHOD = 'p16c-original-input-v1'


class ColumnMapping(Contract):
    source: str = Field(min_length=1, max_length=120)
    units: str | None = Field(default=None, max_length=40)


class ImportedSource(Contract):
    schema_version: Literal['1'] = '1'
    filename: str = Field(min_length=1, max_length=160, pattern=r'^[^/\\\x00-\x1f]+$')
    content_base64: str = Field(min_length=4, max_length=2_666_668)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    parser_version: str = Field(min_length=1, max_length=80)
    mapping: dict[Annotated[str, Field(max_length=60)], ColumnMapping | None] | None = Field(default=None, max_length=30)

    def original_bytes(self):
        try:
            body = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise UnsupportedData('source_mismatch', 'The imported source encoding is invalid. Use the original file.') from exc
        if not body or len(body) > 2_000_000:
            raise UnsupportedData('file_limits', 'Imported source files must be non-empty and no larger than 2 MB.')
        if hashlib.sha256(body).hexdigest() != self.source_sha256:
            raise UnsupportedData('source_mismatch', 'The imported source bytes do not match their saved checksum. No result was substituted.')
        return body


class ImportedComparisonRequest(Contract):
    import_source: ImportedSource
    profile_id: str = Field(pattern=r'^[a-zA-Z0-9_.-]{1,100}$')
    settings: MatchSettings


class ImportedCoverageRequest(Contract):
    import_source: ImportedSource
    settings: MatchSettings
