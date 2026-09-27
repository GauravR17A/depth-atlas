"""Source-note fidelity and quantitative holds are separate from original QC."""
from pathlib import Path
from api.instrument_store import InstrumentStore


def test_original_calibration_sentence_and_warning_survive_preparation():
    store = InstrumentStore(Path(__file__).resolve().parents[1] / 'casepacks/instruments')
    item = next(p for p in store.catalog()['profiles'] if p['platform'] == '5907083')
    profile = store.read(item['id'])
    comments = profile.metadata['scientific_calibration']['SCIENTIFIC_CALIB_COMMENT']
    assert comments[0] == 'Headless verification run - no calibration comments entered.'
    assert any('pending source clarification' in warning for warning in profile.warnings)
    assert profile.parameters['temperature'].accepted_count == 102
    assert all(level.readings['temperature'].qc == '1' for level in profile.levels)
