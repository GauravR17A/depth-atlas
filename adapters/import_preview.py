"""Bounded observation review and explicit CSV mappings. No upload persistence."""
import csv
import hashlib
import io
import json
import math

from adapters.instruments import MAX_BYTES, MAX_LEVELS, parse_instruments, fail
from science.contracts import UnsupportedData

PARSER_VERSION = 'observation-preview-v1'
REQUIRED = ['profile_id', 'instrument', 'platform', 'time', 'latitude', 'longitude',
            'pressure_dbar', 'pressure_qc', 'position_qc', 'time_qc']
VALUES = {'temperature_c': ('temperature', 'degC'), 'salinity_psu': ('salinity', 'psu'),
          'oxygen_umol_kg': ('oxygen', 'umol/kg'), 'chlorophyll_mg_m3': ('chlorophyll', 'mg/m3'),
          'nitrate_umol_kg': ('nitrate', 'umol/kg')}
# Only dimensional conversions requiring no additional physical assumptions.
CONVERSIONS = {'temperature_c': {'degC': (1, 0), 'K': (1, -273.15)},
               'salinity_psu': {'psu': (1, 0), 'PSS-78': (1, 0)},
               'oxygen_umol_kg': {'umol/kg': (1, 0)},
               'chlorophyll_mg_m3': {'mg/m3': (1, 0), 'ug/L': (1, 0), 'mg/L': (1000, 0)},
               'nitrate_umol_kg': {'umol/kg': (1, 0)}}
TARGETS = REQUIRED + [field for target, (key, _) in VALUES.items() for field in (target, key + '_qc')]


def inspect_import(body: bytes, filename: str, mapping: dict | None = None, source_url: str = '') -> dict:
    if not body or len(body) > MAX_BYTES:
        fail('file_limits', 'Choose a non-empty file no larger than 2 MB.')
    plain_csv = filename.lower().endswith(('.csv', '.txt')) and not body.startswith((b'CTD,', b'\xef\xbb\xbfCTD,'))
    columns = []
    used = []
    normalized = body
    applied = {}
    if mapping is not None and (not plain_csv or not isinstance(mapping, dict) or len(mapping) > len(TARGETS)):
        fail('invalid_mapping', 'Column mapping supports documented CSV tables only. Native NetCDF and CTD Exchange use their source metadata.')
    if plain_csv:
        try:
            reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig')), strict=True)
            columns = reader.fieldnames or []
            if not columns or len(columns) > 80 or len(set(columns)) != len(columns) or any(not c or len(c) > 120 for c in columns):
                fail('invalid_csv', 'Use unique, non-empty column names, at most 80 columns and 120 characters per name.')
            rows = []
            for row in reader:
                if len(rows) >= MAX_LEVELS: fail('file_limits', 'At most 5,000 samples per CSV.')
                if None in row or any(v is None for v in row.values()): fail('invalid_csv', 'Every CSV row must have the same number of columns.')
                rows.append(row)
            if not rows: fail('invalid_csv', 'The CSV contains no observation rows.')
        except (UnicodeError, csv.Error):
            fail('invalid_csv', 'Use a valid UTF-8 comma-separated table with a header.')
        used = [c for c in columns if c in TARGETS]
        if mapping is not None:
            if any(k not in TARGETS for k in mapping): fail('invalid_mapping', 'A mapping contains an unsupported target field.')
            output = {}
            for target in TARGETS:
                spec = mapping.get(target, {'source': target} if target in columns else None)
                if spec is None: continue
                if not isinstance(spec, dict) or set(spec) - {'source', 'units'} or not isinstance(spec.get('source'), str):
                    fail('invalid_mapping', 'Each mapped field needs a source column and, for measurements, supported source units.')
                source = spec['source']
                if source not in columns: fail('invalid_mapping', f'Source column {source} is absent.')
                scale, offset = 1, 0
                units = spec.get('units')
                if target in VALUES:
                    default = VALUES[target][1]
                    if units is None and source == target: units = default
                    if not isinstance(units,str) or units not in CONVERSIONS[target]: fail('incompatible_units', f'{target}: select supported source units. No density-dependent or guessed conversion is performed.')
                    if source in VALUES and (source != target or units != VALUES[source][1]):
                        fail('invalid_mapping', 'A documented measurement column cannot be relabelled as another quantity or unit.')
                    scale, offset = CONVERSIONS[target][units]
                elif units is not None:
                    fail('invalid_mapping', 'Coordinate and QC mappings rename columns only. Coordinates must already use the documented units and QC scheme.')
                output[target] = (source, scale, offset)
                applied[target] = {'source': source, 'source_units': units, 'scale': scale, 'offset': offset}
            sources = [spec[0] for spec in output.values()]
            if len(sources) != len(set(sources)): fail('invalid_mapping', 'Each source column can map to only one target. Separate quantities and QC fields are required.')
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=list(output), lineterminator='\n')
            writer.writeheader()
            for row in rows:
                converted = {}
                for target, (source, scale, offset) in output.items():
                    val = row[source]
                    if target in VALUES and val.strip():
                        try: number = float(val)
                        except ValueError: fail('invalid_file', f'{source} contains a non-numeric measurement.')
                        # Missing/non-finite values remain missing; do not turn sentinels into plausible data.
                        val = repr(number * scale + offset) if math.isfinite(number) else ''
                    converted[target] = val
                writer.writerow(converted)
            normalized = stream.getvalue().encode('utf-8')
            if len(normalized) > MAX_BYTES: fail('file_limits', 'The mapped table exceeds the 2 MB parser budget.')
            used = sources
    response = {'schema_version': '1', 'parser_version': PARSER_VERSION,
                'source_sha256': hashlib.sha256(body).hexdigest(), 'columns': columns,
                'mapping_supported': plain_csv, 'ignored_fields': [c for c in columns if c not in used],
                'result': None, 'issue': None}
    try:
        result = parse_instruments(normalized, filename, source_url)
    except UnsupportedData as error:
        if plain_csv and error.code in {'missing_metadata', 'missing_variable'}:
            response['issue'] = str(error)
            return response
        raise
    if mapping is not None:
        mapping_hash = hashlib.sha256(json.dumps(applied, sort_keys=True).encode()).hexdigest()
        for p in result.profiles:
            p.source_sha256 = response['source_sha256']
            p.id = p.id.rsplit('-', 1)[0] + '-' + p.source_sha256[:10] + '-' + mapping_hash[:10]
            p.metadata.update(import_mapping=applied, mapping_sha256=mapping_hash,
                              parser_version=PARSER_VERSION, normalized_sha256=hashlib.sha256(normalized).hexdigest())
            for target, (key, _) in VALUES.items():
                if key in p.parameters:
                    p.parameters[key].source_field = applied[target]['source']
            p.warnings.append('CSV mapping is declared by the uploader. Displayed values, including raw-value inspection, use the displayed units after the recorded conversion. Original file identity is retained.')
    if not plain_csv:
        response['ignored_fields'] = sorted({name for p in result.profiles for name in p.metadata.get('unsupported_parameters', [])})
    response['result'] = result.model_dump()
    if len(json.dumps(response, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 3_500_000:
        fail('file_limits', 'The decoded review exceeds the 3.5 MB response limit. Use a smaller source subset.')
    return response
