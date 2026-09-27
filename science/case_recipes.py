"""Explicit bounded acquisition recipes; no inferred sources or dates."""

RECIPES = {
    'bay-bengal-2024-01': {
        'region_id': 'bay-of-bengal', 'name': 'Bay of Bengal', 'raw': 'data/raw',
        'bounds': (85, 12, 90, 15), 'shape': (40, 76, 63), 'processing_version': 'p02.1',
        'profiles': [f'incois/{p}/profiles/D{p}_012.nc' for p in ['1902669','2903891','4903775','4903776','5907083','7901125','7901126']],
    },
    'arabian-sea-2024-01': {
        'region_id': 'arabian-sea', 'name': 'Arabian Sea', 'raw': 'data/raw/arabian-sea',
        'bounds': (66, 16, 71, 19), 'shape': (40, 76, 63), 'processing_version': 'p09.1',
        'profiles': ['incois/1902671/profiles/D1902671_010.nc',
                     'incois/1902672/profiles/D1902672_010.nc',
                     'incois/5907084/profiles/D5907084_010.nc',
                     'incois/7901128/profiles/R7901128_010.nc',
                     'incois/2902273/profiles/R2902273_172.nc'],
    },
    'bay-bengal-2024-03': {
        'region_id': 'bay-of-bengal', 'name': 'Bay of Bengal', 'raw': 'data/raw/bay-march',
        'bounds': (85, 12, 86, 13), 'shape': (40, 26, 13), 'processing_version': 'p16b.1',
        'times': ['2024-03-28T00:00:00Z', '2024-03-28T12:00:00Z',
                  '2024-03-29T00:00:00Z', '2024-03-29T12:00:00Z', '2024-03-30T00:00:00Z'],
        'title': 'Bay of Bengal · 28-30 March 2024',
        'profiles': [], 'require_observation_overlap': False, 'adapter': 'hycom-rectilinear',
    },
}
