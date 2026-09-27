"""Merge checked OISST distributions without interpolating missing dates."""
from __future__ import annotations
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import netCDF4
import numpy as np
from pydap.client import open_dods_file
from science.acquire_heat import ROOT, RAW

PACK = ROOT / 'casepacks/heat'
SELECTION = ('Nearest native OISST cell to the case rectangle west quartile, center or east quartile at center latitude; lower coordinate wins an exact tie. All six positions were fixed before event detection. These are point samples, not regional means.')


def file_info(path: Path, relative_to: Path = PACK):
    return {'path': path.relative_to(relative_to).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')


def selected_locations():
    lons, lats = np.arange(.125, 360, .25), np.arange(-89.875, 90, .25)
    output = []
    for case_id, prefix in [('bay-bengal-2024-01', 'bay'), ('arabian-sea-2024-01', 'arabian')]:
        case = json.loads((ROOT / 'casepacks' / case_id / 'manifest.json').read_text(encoding='utf-8'))['case']
        west, south, east, north = case['bounds']
        for name, fraction in [('west', .25), ('center', .5), ('east', .75)]:
            y, x = (south + north) / 2, west + (east - west) * fraction
            output.append({'id': f'{prefix}-{name}', 'case_id': case_id,
                'label': ('Bay of Bengal' if prefix == 'bay' else 'Arabian Sea') + ' ' + name,
                'latitude': float(lats[np.argmin(abs(lats-y))]), 'longitude': float(lons[np.argmin(abs(lons-x))]),
                'requested_latitude': y, 'requested_longitude': x,
                'case_bounds': case['bounds'], 'selection_rule': SELECTION})
    return output


def read_subset(record):
    """Decode unchanged distributor responses, retaining original time units."""
    path = ROOT / record['path']
    if record['archive_kind'] == 'unmodified_dap2_response':
        metadata_name = f"sst-{record['year']}.das"
        metadata_path = RAW / metadata_name
        if not metadata_path.exists():
            metadata_path = path.parent / metadata_name
        dataset = open_dods_file(str(path), str(metadata_path))
        field = dataset['sst']
        attrs, glob = field.attributes, dataset.attributes
        legacy = record['year'] <= 2015 and 'High-resolution Blended Analysis' in glob.get('title', '')
        if not (glob.get('version') == 'Version 2.1' or legacy) or attrs['units'] != 'degC':
            raise ValueError('Unexpected PSL source lineage or units')
        data = np.asarray(field.array.data)
        data = np.ma.masked_where(~np.isfinite(data) | np.isclose(data, attrs['missing_value']), data)
        lat, lon = [np.asarray(field[k].data) for k in ('lat', 'lon')]
        times = np.asarray(field['time'].data, dtype=float)
        time_attrs = glob['time']
        units, cal = time_attrs['units'], time_attrs.get('calendar', 'standard')
        info = {'distributor': 'NOAA PSL', 'original_units': attrs['units'],
                'original_title': glob['title'], 'original_version': glob.get('version'),
                'source_lineage': 'pre-2016 SST unchanged in v2.1' if legacy and not glob.get('version') else 'Version 2.1'}
    elif record['archive_kind'] == 'unmodified_erddap_netcdf_response':
        with netCDF4.Dataset(path) as dataset:
            field = dataset.variables['sst']
            if dataset.product_version != 'Version v02r01' or field.units != 'degree_C':
                raise ValueError('Unexpected AOML product version or units')
            data = field[:]
            lat, lon = [np.asarray(dataset.variables[k][:]) for k in ('latitude', 'longitude')]
            time_var = dataset.variables['time']
            times = np.asarray(time_var[:], dtype=float)
            units, cal = time_var.units, getattr(time_var, 'calendar', 'standard')
            info = {'distributor': 'NOAA AOML', 'original_units': field.units,
                    'original_title': dataset.title, 'original_version': dataset.product_version,
                    'source_lineage': 'Version 2.1'}
    else:
        raise ValueError('Unsupported raw response kind')
    if data.dtype not in (np.dtype('float32'), np.dtype('>f4')) or data.shape != (len(times), 2, 88):
        raise ValueError('Source SST grid or Float32 dtype changed')
    np.testing.assert_array_equal(lat, [13.375, 17.375])
    np.testing.assert_array_equal(lon, np.arange(67.125, 89, .25))
    decoded = netCDF4.num2date(times, units, calendar=cal)
    days = [t.strftime('%Y-%m-%d') for t in decoded]
    if days != sorted(set(days)) or any(not d.startswith(str(record['year'])+'-') for d in days):
        raise ValueError('Invalid dates in annual source subset')
    info.update(time_units=units, calendar=cal, source_dtype='Float32')
    return data, lat, lon, times, decoded, info


def within_one_ulp(a, b):
    if a is None or b is None:
        return a is None and b is None
    step = max(float(np.spacing(np.float32(abs(a)))), float(np.spacing(np.float32(abs(b)))))
    return abs(a-b) <= step and int(np.rint(a*100)) == int(np.rint(b*100))


def prepare():
    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / 'source-metadata').mkdir(exist_ok=True)
    locations = selected_locations()
    journals = [json.loads((RAW / name).read_text(encoding='utf-8')) for name in ('acquisition.json', 'aoml-acquisition.json')]
    records = sorted([dict(item) for j in journals for item in j['files']], key=lambda r: r['path'])
    samples, metadata_files, differences = {}, [], []
    overlap_count = 0
    for source_index, record in enumerate(records):
        path = ROOT / record['path']
        if file_info(path, ROOT)['sha256'] != record['sha256']:
            raise ValueError(f'Source checksum changed: {path.name}')
        if record['archive_kind'] == 'source_metadata':
            target = PACK / 'source-metadata' / path.name
            target.write_bytes(path.read_bytes())
            metadata_files.append(file_info(target))
            continue
        data, lat, lon, numeric, decoded, info = read_subset(record)
        record.update(info)
        ids = [(int(np.flatnonzero(lat == loc['latitude'])[0]), int(np.flatnonzero(lon == loc['longitude'])[0])) for loc in locations]
        for index, stamp in enumerate(decoded):
            day, values = stamp.strftime('%Y-%m-%d'), []
            for yy, xx in ids:
                value = data[index, yy, xx]
                if np.ma.is_masked(value) or not np.isfinite(value):
                    values.append(None)
                elif not -3 <= value <= 45:
                    raise ValueError('Finite source SST outside valid range')
                else:
                    values.append(float(value))
            incoming = {'values': values, 'timestamp': stamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'numeric_time': float(numeric[index]), 'source_index': source_index, 'distributor': info['distributor']}
            if day in samples:
                previous = samples[day]
                for loc, a, b in zip(locations, previous['values'], values):
                    overlap_count += 1
                    if not within_one_ulp(a, b):
                        raise ValueError(f"Distributor overlap differs by more than one ULP at {loc['id']} {day}")
                    if a != b:
                        differences.append({'location_id': loc['id'], 'date': day, 'first_source_index': previous['source_index'],
                            'second_source_index': source_index, 'first_value': a, 'second_value': b, 'absolute_difference_c': abs(a-b)})
                if previous['distributor'] == 'NOAA AOML':
                    continue
            samples[day] = incoming
    dates = [(date(1982,1,1)+timedelta(days=i)).isoformat() for i in range((date(2026,1,1)-date(1982,1,1)).days)]
    missing = [day for day in dates if day not in samples]
    if missing:
        raise ValueError(f'Source daily axis incomplete: {len(missing)} missing dates, first {missing[:10]}')
    source_indices = [samples[d]['source_index'] for d in dates]
    timestamps = [samples[d]['timestamp'] for d in dates]
    numeric_times = [samples[d]['numeric_time'] for d in dates]
    for loc_index, loc in enumerate(locations):
        values = [samples[d]['values'][loc_index] for d in dates]
        content = {'schema_version': '1', 'location_id': loc['id'], 'dates': dates, 'sst_c': values,
            'source_timestamps': timestamps, 'source_numeric_time': numeric_times, 'source_file_indices': source_indices,
            'time_units': None, 'calendar': 'standard',
            'time_units_policy': 'Each original numeric time uses units and calendar in manifest.source_files[source_file_indices[i]]. Mixed origins are not a single numerical axis.',
            'units': 'degree_Celsius', 'source_variable': 'sst', 'source_dtype': 'Float32'}
        path = PACK / (loc['id']+'.json')
        write_json(path, content)
        loc.update(file_info(path), sample_count=len(dates), missing_count=sum(v is None for v in values), source_start=dates[0], source_end=dates[-1])
    primary_journal = json.loads((RAW / 'primary-source-checks.json').read_text(encoding='utf-8'))
    if sorted(r['date'] for r in primary_journal['files']) != ['19820101', '19960701', '20240107']:
        raise ValueError('All three declared primary spot checks are required')
    primary_checks = []
    for record in primary_journal['files']:
        path = ROOT / record['path']
        if file_info(path, ROOT)['sha256'] != record['sha256']:
            raise ValueError('Primary source checksum changed')
        with netCDF4.Dataset(path) as ds:
            t = ds.variables['time']; stamp = netCDF4.num2date(t[0], t.units); day = stamp.strftime('%Y-%m-%d')
            field = ds.variables['sst']
            if field.units != 'Celsius':
                raise ValueError('Primary source units changed')
            scale, offset, decoded = field.scale_factor, field.add_offset, field[:]
            field.set_auto_maskandscale(False); packed = field[:]
            for li, loc in enumerate(locations):
                yy = int(np.flatnonzero(ds.variables['lat'][:] == loc['latitude'])[0]); xx = int(np.flatnonzero(ds.variables['lon'][:] == loc['longitude'])[0])
                primary, served = float(decoded[0,0,yy,xx]), samples[day]['values'][li]
                integer = int(packed[0,0,yy,xx])
                if not within_one_ulp(primary, served) or int(np.rint(served*100)) != integer:
                    raise ValueError(f"Primary source quantization mismatch: {loc['id']} {day}")
                primary_checks.append({'location_id': loc['id'], 'date': day, 'original_packed_integer': integer,
                    'source_scale_factor_float32': float(scale), 'source_add_offset': float(offset),
                    'netcdf4_decoded_float32_c': primary, 'preferred_served_float32_c': served, 'exactly_equal': primary == served,
                    'float32_scale_multiply_c': float(np.float32(integer)*np.float32(scale)+offset),
                    'decimal_centidegrees_to_float32_c': float(np.float32(integer/100.0)),
                    'absolute_difference_c': abs(primary-served), 'same_packed_centidegree': True,
                    'primary_timestamp': stamp.strftime('%Y-%m-%dT%H:%M:%SZ'), 'preferred_timestamp': samples[day]['timestamp'], 'source_sha256': record['sha256']})
    source = {'id': 'noaa-oisst-v2.1-aoml-psl', 'title': 'NOAA OISST v2.1 daily sea-surface temperature',
        'kind': 'observation_blended_analysis', 'provider': 'NOAA NCEI; distributed by NOAA AOML and NOAA PSL',
        'version': 'Version 2.1', 'source_url': 'https://www.ncei.noaa.gov/products/optimum-interpolation-sst',
        'product_url': 'https://www.ncei.noaa.gov/products/optimum-interpolation-sst', 'doi': 'https://doi.org/10.25921/RE9P-PT57',
        'grid_resolution_degrees': .25, 'temporal_resolution': 'daily', 'units': 'degree_Celsius', 'variable': 'sst',
        'definition': 'Daily gridded SST analysis blending bias-adjusted satellite and in-situ information, with spatial gaps filled by interpolation. It is not a raw instrument observation or the HYCOM subsurface model.',
        'citation': 'Huang et al. (2020), NOAA 0.25-degree Daily Optimum Interpolation Sea Surface Temperature (OISST), Version 2.1, NOAA NCEI, doi:10.25921/RE9P-PT57. Distributed by NOAA AOML and NOAA PSL, Boulder, Colorado, USA, https://psl.noaa.gov.',
        'licence': 'NOAA data are available for free use and redistribution, without warranty of accuracy or fitness. Retain source attribution.',
        'licence_url': 'https://www.noaa.gov/disclaimer',
        'retrieval_start': min(r['retrieved_at'] for r in records), 'retrieval_end': max(r['retrieved_at'] for r in records),
        'lineage_note': 'PSL pre-2016 files may retain legacy v2 metadata. NOAA documents unchanged September 1981 to December 2015 SST in v2.1; original metadata are preserved.',
        'merge_policy': 'Prefer exact Float32 values served by AOML for every available day. Use exact PSL values only on absent AOML dates. No temperature interpolation, rounding or normalization. Overlap differences must fit one Float32 ULP and the same original 0.01-degree quantization bin.',
        'quality_policy': 'Use finite source SST in the valid range [-3,45] degC; preserve missing markers as null. SST subsets have no per-sample instrument QC. Gridded completeness is not confidence.',
        'time_policy': 'Preserve AOML noon-centered and PSL midnight-labelled daily timestamps. Original numeric units are attached to each source file and referenced per day. Compare calendar days, not instantaneous readings.',
        'native_anomaly_used': False,
        'native_anomaly_note': 'The source published anomaly uses another climatology. This pack contains SST only; calculate the declared 1982-2011 baseline from SST.'}
    manifest = {'schema_version': '1', 'processing_version': 'p12-surface-source-v1', 'source': source,
        'baseline_period': [1982,2011], 'analysis_years': [2023,2024], 'context_years': [2022,2025], 'source_period': [dates[0],dates[-1]],
        'locations': locations, 'source_files': records, 'source_metadata_files': metadata_files, 'primary_spot_check_files': primary_journal['files'],
        'limitations': ['Six fixed point samples do not establish regional heatwave coverage.',
            'Long surface SST and the short 7-10 January 2024 depth case are separate products.',
            'Surface events do not prove warming throughout the water column.',
            'Small distributor representation differences are preserved and documented.']}
    write_json(PACK / 'manifest.json', manifest)
    checked_at = datetime.now(timezone.utc).isoformat()
    write_json(ROOT / 'docs/evidence/p12-surface-preparation.json', {'checked_at': checked_at, 'locations': locations,
        'manifest': file_info(PACK / 'manifest.json'), 'source_file_count': len(records), 'sample_count_per_location': len(dates),
        'source_day_counts': {p: sum(samples[d]['distributor']==p for d in dates) for p in ('NOAA AOML','NOAA PSL')},
        'checks': {'raw_sha256_verified': True, 'native_coordinate_match': True, 'complete_daily_axis': True,
            'compatible_source_lineage_and_units': True, 'native_float32_preserved': True, 'no_event_selection': True}})
    write_json(ROOT / 'docs/evidence/p12-distributor-comparison.json', {'checked_at': checked_at, 'overlap_point_day_count': overlap_count,
        'differing_point_day_count': len(differences), 'max_absolute_difference_c': max((d['absolute_difference_c'] for d in differences), default=0),
        'differences': differences, 'all_within_one_float32_ulp_and_same_centidegree': True,
        'interpretation': 'Observed differences are preserved. Primary packed-integer checks show matching centidegrees and explicit decode alternatives; the exact upstream implementation is not established.'})
    write_json(ROOT / 'docs/evidence/p12-primary-source-comparison.json', {'checked_at': checked_at, 'checks': primary_checks,
        'files': primary_journal['files'], 'passed': len(primary_checks), 'failed': 0,
        'meaning': 'Source/distributor checks at three dates and six fixed cells, not independent ocean validation.'})
    print(json.dumps({'manifest': file_info(PACK / 'manifest.json'), 'locations': locations}, indent=2))


if __name__ == '__main__':
    prepare()
