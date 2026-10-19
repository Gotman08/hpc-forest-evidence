"""NEUTRAL pure admission-boundary fixtures. No ARM execution or model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import bootstrap_resume as resume
import pytest

BASE = Path(__file__).resolve().parents[2]
EXEC = BASE / 'outputs/HPC-Forest-Matrice15-Execution-root-02'
FIXED = BASE / 'outputs/HPC-Forest-Matrice15-Unit-Operation-Preparation-r2/sol-count-corrected-input-r1/stage/INPUT-BOOTSTRAP.json'


def need(value, text):
    if not value:
        raise ValueError(text)


def ref(path):
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


@pytest.fixture
def guard(tmp_path, monkeypatch):
    failure = json.loads((EXEC / 'bootstrap-failed-755766.json').read_bytes())
    binding = {k: v for k, v in failure['binding'].items() if k != 'job_id'}
    admission = binding['remote_root'] + '-admission'
    mapping = {admission + '/bootstrap-result.json': EXEC / 'bootstrap-failed-755766.json',
               admission + '/bootstrap-intent.json': EXEC / 'original-bootstrap-intent.json',
               admission + '/scheduler-deadline-observation.json': EXEC / 'original-scheduler-deadline-observation.json'}
    proof = {'schema': 'hpc-forest-matrix15-pre-admission-resume-proof-v1', 'verified': True, 'evidence_origin': 'received',
             'failure': {'path': admission + '/bootstrap-result.json', 'sha256': resume.ORIGINAL_FAILURE_SHA, 'bytes': 1381},
             'original_intent': {'path': admission + '/bootstrap-intent.json', 'sha256': resume.OLD_FILES['bootstrap-intent.json'][0], 'bytes': 1490},
             'original_deadline': {'path': admission + '/scheduler-deadline-observation.json', 'sha256': resume.OLD_FILES['scheduler-deadline-observation.json'][0], 'bytes': 168},
             'readback': ref(EXEC / 'BOOTSTRAP-READBACK-REEL-r1.json'), 'scp': ref(EXEC / 'BOOTSTRAP-FAILED-SCP-REEL-r1.json'),
             'efficiency': ref(EXEC / 'JOB-EFFICIENCY-FAILED-REEL-r1.json')}
    now = resume.ORIGINAL_STARTED_AT + 250
    review = {'schema': 'hpc-forest-matrix15-pre-admission-resume-root-review-v1', 'verified': True, 'evidence_origin': 'received',
              'reviewer': 'ROOT', 'reviewed_at': now, 'wrapper_sha256': 'e' * 64, 'failure_sha256': resume.ORIGINAL_FAILURE_SHA,
              'corrected_input_sha256': resume.CORRECTED_INPUT_SHA, 'original_clock_preserved': True,
              'zero_model_technical_phase_only': True, 'selected_session_has_no_reservation': True,
              'reservation_observation': {'observed_at': now, 'origin': 'ROOT-private-persistent-registry-read', 'complete_registry': True, 'records': []},
              'evidence_sha256': {k: proof[k]['sha256'] for k in ('failure', 'original_intent', 'original_deadline', 'readback', 'scp', 'efficiency')}}
    review_path = tmp_path / 'ROOT-review-NEUTRAL.json'
    review_path.write_text(json.dumps(review), encoding='utf8')
    proof['root_review'] = ref(review_path)
    def regular(path):
        return mapping.get(str(path), Path(str(path))).read_bytes()
    def read_ref(item, **kwargs):
        need(set(item) == {'path', 'sha256', 'bytes'}, 'REF3')
        raw = regular(item['path'])
        need(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], 'SHA/bytes')
        return raw
    class ArmPath:
        def __init__(self, value): self.value = str(value)
        def __str__(self): return self.value
        def __truediv__(self, value): return ArmPath(self.value + '/' + value)
        def iterdir(self): return [SimpleNamespace(name=name) for name in resume.OLD_FILES]
    monkeypatch.setattr(resume, 'Path', ArmPath)
    b = SimpleNamespace(need=need, sha=lambda raw: hashlib.sha256(raw).hexdigest(), read_json=lambda raw: json.loads(raw),
        regular_bytes=regular, read_ref=read_ref, physical=lambda _: None, absent=lambda _: True,
        scientific_paths=lambda binding: {'root': binding['remote_root']})
    return b, proof, binding, now, review_path, review


def validate(guard, *, now=None):
    b, proof, binding, clock, _, _ = guard
    return resume.validate_resume(b, proof, FIXED.read_bytes(), binding, now=clock if now is None else now, wrapper_sha='e' * 64)


def test_real_failure_bytes_and_primary_boundary(guard):
    assert validate(guard)['binding']['job_id'] == resume.ORIGINAL_JOB


@pytest.mark.parametrize('delta', [600, 601, 3600, -1])
def test_original_deadline_never_renews(guard, delta):
    with pytest.raises(ValueError):
        validate(guard, now=resume.ORIGINAL_STARTED_AT + delta)


def test_exact_corrected_input_only(guard):
    b, proof, binding, now, _, _ = guard
    with pytest.raises(ValueError, match='REF3-only'):
        resume.validate_resume(b, proof, FIXED.read_bytes() + b' ', binding, now=now, wrapper_sha='e' * 64)


def test_original_sha_mutation_refused(guard):
    guard[1]['failure']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='SHA/bytes'):
        validate(guard)


def test_any_scientific_path_refused(guard):
    guard[0].absent = lambda _: False
    with pytest.raises(ValueError, match='generation had already started'):
        validate(guard)


def test_reservation_for_session_refused(guard):
    _, proof, binding, _, path, review = guard
    row = {'schema': 'hpc-forest-matrix15-single-slot-reservation-v1', 'verified': True, 'session_id': binding['session_id'], 'reservation_id': 'a' * 32}
    raw = json.dumps(row)
    review['reservation_observation']['records'] = [{'filename': 'a' * 32 + '.reservation.json', 'sha256': hashlib.sha256(raw.encode()).hexdigest(), 'raw_utf8': raw}]
    path.write_text(json.dumps(review), encoding='utf8')
    proof['root_review'] = ref(path)
    with pytest.raises(ValueError, match='already reserved'):
        validate(guard)


def test_prepared_review_refused(guard):
    _, proof, _, _, path, review = guard
    review['verified'] = False
    path.write_text(json.dumps(review), encoding='utf8')
    proof['root_review'] = ref(path)
    with pytest.raises(ValueError, match='negative evidence'):
        validate(guard)


def test_clock_translation_keeps_original_epoch():
    b = SimpleNamespace(need=need)
    started, monotonic = resume.inherited_clock(b, {'bootstrap_started_at': resume.ORIGINAL_STARTED_AT}, resume.ORIGINAL_STARTED_AT + 500, 1000)
    assert started == resume.ORIGINAL_STARTED_AT and monotonic == 500
    assert 600 - (1000 - monotonic) == 100
    with pytest.raises(ValueError, match='expired'):
        resume.inherited_clock(b, {'bootstrap_started_at': resume.ORIGINAL_STARTED_AT}, resume.ORIGINAL_STARTED_AT + 600, 1000)


def test_claim_exactly_once_and_preserve_original_files(tmp_path):
    old = tmp_path / 'bootstrap-result.json'
    old.write_bytes(b'NEUTRAL ORIGINAL')
    resume.claim_continuation(tmp_path)
    with pytest.raises(FileExistsError):
        resume.claim_continuation(tmp_path)
    assert old.read_bytes() == b'NEUTRAL ORIGINAL'
