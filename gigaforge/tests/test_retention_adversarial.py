"""Adversarial stress-testing of Candidate Checkpoint Retention (Feature 5).

Verifies that pinned checkpoints in watch_pins/ remain fully recoverable by
trial_watch.find_exact and head_to_head.select even after total branch deletion,
under multi-candidate ranking, across both Chronos and Galactus families, and
under branch corruption.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib, json, sys, copy, shutil, torch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
nova = Path(__file__).resolve().parents[2] / 'novaforge'
if not nova.exists():
    nova = Path(__file__).resolve().parents[2] / 'NovaForge'
sys.path.insert(0, str(nova))

import trial_watch as w
import research
import head_to_head
from nova.teachers import verify_teacher


def make_mock_m(root):
    def write(p, data):
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (dict, list)):
            p.write_text(json.dumps(data))
        elif isinstance(data, (bytes, bytearray)):
            p.write_bytes(data)
        else:
            p.write_text(str(data))

    def read(p):
        return json.loads(Path(p).read_text())

    def sha(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    m = SimpleNamespace(
        ROOT=root,
        read=read,
        write=write,
        sha=sha,
        seal_generation=lambda *a: None,
        verify_generation=lambda *a: None,
    )
    return m


def setup_candidate_fixture(tmp_path, family='chronos', trial=62, delta=0.046875, branch_subpath='evolved_40/base/checkpoints/1048576'):
    """Sets up a complete candidate with genuine teacher weights and evaluation records."""
    root = tmp_path / f'gigaforge_{family}_{trial}'
    run = root / 'runs/research02'
    run.mkdir(parents=True, exist_ok=True)
    m = make_mock_m(root)

    teacher = verify_teacher(family)
    source = run / 'branches' / family / branch_subpath
    source.mkdir(parents=True, exist_ok=True)
    for n in w.FILES:
        shutil.copy2(teacher / n, source / n)

    # Optional checkpoint files
    for n in ('POLICY_OPTIM.lt', 'SHARED_HEAD_OPTIM.lt', 'CRITIC.lt', 'CRITIC_OPTIM.lt', 'RUNNING_STATS.json', 'COMPLETE'):
        (source / n).write_bytes(f'state for {n} trial {trial}'.encode())

    files = w.identity(m, source)
    record = dict(trial=trial, family=family, candidate=str(source.relative_to(run)).replace('/', '\\'))
    
    # State
    state_file = run / 'lab_state.json'
    if state_file.is_file():
        state = m.read(state_file)
        state['results'].append(record)
    else:
        state = dict(trial=trial, results=[record], last_candidates={family: str(source.relative_to(run))})
    m.write(state_file, state)

    # Evaluation record
    rows = [
        dict(opponent='original_' + ('galactus' if family == 'chronos' else 'chronos'),
             seed=710620000 + trial, side=s, goals_for=1, goals_against=0, outcome=1, seconds=60)
        for s in (0, 1)
    ]
    eval_path = run / 'evaluations' / f'lab_{trial:05d}_{family}_confirmation.json'
    eval_data = dict(trials=rows, split='confirmation', statistics=dict(delta=delta))
    m.write(eval_path, eval_data)

    job_data = dict(
        identity=dict(models=[dict(family=family, hitbox='breakout' if family == 'chronos' else 'octane', files=files)]),
        result=dict(trials=rows)
    )
    m.write(run / 'evaluations/jobs' / f'job_{trial}_{family}.json', job_data)

    return m, run, source, files, eval_data


def test_adversarial_retention_branch_wipe_chronos(tmp_path):
    """Adversarially verify that wiping the entire branch tree does NOT cause lookup: 'missing' for Chronos."""
    m, run, source, files, eval_data = setup_candidate_fixture(tmp_path, family='chronos', trial=62, delta=0.05)
    state = m.read(run / 'lab_state.json')
    result = dict(split='confirmation', decision='uncertain', statistics=eval_data['statistics'], summary={}, baseline_summary={})

    # Pin candidate to watch_pins
    pinned_dir = research.pin_candidate(m, run, state, 'chronos', source, result, 'confirmation')
    assert pinned_dir is not None and pinned_dir.is_dir()
    assert (pinned_dir / 'POLICY.lt').is_file()
    assert (pinned_dir / 'SHARED_HEAD.lt').is_file()
    assert (pinned_dir / 'actor.lt').is_file()
    assert (pinned_dir / 'pin_manifest.json').is_file()

    # Adversarial action: delete ALL branches
    shutil.rmtree(run / 'branches')
    assert not (run / 'branches').exists()
    assert not source.exists()

    # Verify find_exact finds the pinned model
    target = w.trial_identity(m, run, 'chronos', 62)
    found = w.find_exact(m, run, target)
    assert found['kind'] == 'native', f"Expected native kind but got {found}"
    assert Path(found['path']).resolve() == pinned_dir.resolve()
    assert found.get('errors') == []

    # Verify head_to_head.select succeeds with lookup: 'native' and zero 'missing'
    selection = head_to_head.select(m, run)
    assert selection['trial'] == 62
    assert selection['family'] == 'chronos'
    assert selection['attempts'][0]['lookup'] == 'native'
    assert not any(att.get('lookup') == 'missing' for att in selection['attempts'])
    assert Path(selection['actor']).resolve() == (pinned_dir / 'actor.lt').resolve()

    # Verify inference forward pass on the pinned actor
    actor = torch.jit.load(selection['actor'], map_location='cpu')
    x = torch.zeros(4, 225 + 3)
    with torch.inference_mode():
        logits = actor(x)
    assert logits.shape == (4, 90)
    assert torch.isfinite(logits).all()


def test_adversarial_retention_branch_wipe_galactus(tmp_path):
    """Adversarially verify candidate retention, hitbox octane, and inference for Galactus after branch wipe."""
    m, run, source, files, eval_data = setup_candidate_fixture(tmp_path, family='galactus', trial=75, delta=0.045)
    state = m.read(run / 'lab_state.json')
    result = dict(split='confirmation', decision='improved', statistics=eval_data['statistics'], summary={}, baseline_summary={})

    pinned_dir = research.pin_candidate(m, run, state, 'galactus', source, result, 'confirmation')
    assert pinned_dir is not None and pinned_dir.is_dir()

    # Adversarial action: wipe all branches
    shutil.rmtree(run / 'branches')
    assert not (run / 'branches').exists()

    target = w.trial_identity(m, run, 'galactus', 75)
    found = w.find_exact(m, run, target)
    assert found['kind'] == 'native'
    assert Path(found['path']).resolve() == pinned_dir.resolve()

    # Verify prepare produces valid octane actor
    actor_path = w.prepare(m, run, 'galactus', 75)
    from nova.forge_models import check_actor
    meta = check_actor(actor_path, 'galactus')
    assert meta['contract']['hitbox'] == 'octane'
    assert meta['contract']['family'] == 'galactus'

    actor = torch.jit.load(str(actor_path), map_location='cpu')
    x = torch.zeros(4, 258 + 3)
    with torch.inference_mode():
        logits = actor(x)
    assert logits.shape == (4, 90)
    assert torch.isfinite(logits).all()


def test_adversarial_multi_candidate_ranking_and_fallback_after_branch_wipe(tmp_path):
    """Stress-test selection order among multiple candidates when all branches are wiped.
    
    Highest delta candidate is selected first. If the top pin is subsequently lost,
    selection falls back to the second best candidate without failing or returning 'missing'.
    """
    root = tmp_path / 'gigaforge_multicand'
    run = root / 'runs/research02'
    run.mkdir(parents=True, exist_ok=True)
    m = make_mock_m(root)
    teacher = verify_teacher('chronos')

    trials = [
        (60, 0.020, 'arm1/ckpt/100'),
        (61, 0.075, 'arm2/ckpt/200'),  # highest delta
        (62, 0.045, 'arm3/ckpt/300'),  # second highest delta
    ]

    pinned_dirs = {}
    records = []

    for trial, delta, subpath in trials:
        source = run / 'branches/chronos' / subpath
        source.mkdir(parents=True, exist_ok=True)
        # Give each trial unique weights by modifying bytes slightly so tags and hashes differ
        for n in w.FILES:
            raw = (teacher / n).read_bytes()
            (source / n).write_bytes(raw + f'_trial_{trial}'.encode())
        for n in ('POLICY_OPTIM.lt', 'SHARED_HEAD_OPTIM.lt', 'CRITIC.lt', 'CRITIC_OPTIM.lt', 'RUNNING_STATS.json', 'COMPLETE'):
            (source / n).write_bytes(b'ckpt')

        files = w.identity(m, source)
        records.append(dict(trial=trial, family='chronos', candidate=str(source.relative_to(run)).replace('/', '\\')))

        rows = [
            dict(opponent='original_galactus', seed=710620000 + trial, side=s, goals_for=1, goals_against=0, outcome=1, seconds=60)
            for s in (0, 1)
        ]
        m.write(run / 'evaluations' / f'lab_{trial:05d}_chronos_confirmation.json', dict(trials=rows, split='confirmation', statistics=dict(delta=delta)))
        m.write(run / 'evaluations/jobs' / f'job_{trial}.json', dict(identity=dict(models=[dict(family='chronos', hitbox='breakout', files=files)]), result=dict(trials=rows)))

        state_for_pin = dict(trial=trial, results=records, pinned_candidates={})
        result = dict(split='confirmation', decision='improved' if delta > 0.03 else 'uncertain', statistics=dict(delta=delta), summary={}, baseline_summary={})
        pdir = research.pin_candidate(m, run, state_for_pin, 'chronos', source, result, 'confirmation')
        pinned_dirs[trial] = pdir

    m.write(run / 'lab_state.json', dict(trial=62, results=records, last_candidates={'chronos': 'branches/chronos/arm3/ckpt/300'}))

    # Adversarial action: delete entire branches directory!
    shutil.rmtree(run / 'branches')
    assert not (run / 'branches').exists()

    # Selection MUST select Trial 61 (highest delta +0.075) with lookup: 'native'
    sel1 = head_to_head.select(m, run)
    assert sel1['trial'] == 61
    assert sel1['confirmation_delta'] == 0.075
    assert sel1['attempts'][0]['lookup'] == 'native'
    assert not any(a.get('lookup') == 'missing' for a in sel1['attempts'])

    # Adversarial action 2: Simulate physical loss/corruption of top candidate's pin directory
    shutil.rmtree(pinned_dirs[61])
    assert not pinned_dirs[61].exists()

    # Selection MUST now cleanly fall back to Trial 62 (second highest delta +0.045)
    sel2 = head_to_head.select(m, run)
    assert sel2['trial'] == 62
    assert sel2['confirmation_delta'] == 0.045
    # First attempt (trial 61) is missing, but second attempt (trial 62) is native!
    assert sel2['attempts'][0]['trial'] == 61
    assert sel2['attempts'][0]['lookup'] == 'missing'
    assert sel2['attempts'][1]['trial'] == 62
    assert sel2['attempts'][1]['lookup'] == 'native'

    # Adversarial action 3: Remove Trial 62 pin as well
    shutil.rmtree(pinned_dirs[62])
    sel3 = head_to_head.select(m, run)
    assert sel3['trial'] == 60
    assert sel3['confirmation_delta'] == 0.020
    assert sel3['attempts'][2]['trial'] == 60
    assert sel3['attempts'][2]['lookup'] == 'native'


def test_adversarial_prune_branches_immunity_watch_pins_never_deleted(tmp_path):
    """Stress-test research.prune_branches to verify that watch_pins is completely immune from pruning."""
    root = tmp_path / 'gigaforge_prune_test'
    run = root / 'runs/research02'
    run.mkdir(parents=True, exist_ok=True)
    m = make_mock_m(root)
    teacher = verify_teacher('chronos')

    # Create 10 fake branch checkpoints under branches/
    branches_dir = run / 'branches/chronos/arm_attack/run_1/checkpoints'
    branches_dir.mkdir(parents=True, exist_ok=True)
    for i in range(10):
        ckpt = branches_dir / f'{1000 * (i + 1)}'
        ckpt.mkdir(parents=True, exist_ok=True)
        (ckpt / 'POLICY.lt').write_bytes(b'ckpt policy')
        (ckpt / 'SHARED_HEAD.lt').write_bytes(b'ckpt head')

    # Create watch_pins directory with 3 pinned candidates
    pins_dir = run / 'watch_pins/chronos'
    pins_dir.mkdir(parents=True, exist_ok=True)
    pin_hashes = {}
    for t in (10, 20, 30):
        pdir = pins_dir / f'trial_{t:05d}_abc{t}def123'
        pdir.mkdir(parents=True, exist_ok=True)
        for n in w.FILES:
            raw = (teacher / n).read_bytes()
            (pdir / n).write_bytes(raw)
            pin_hashes[str(pdir / n)] = hashlib.sha256(raw).hexdigest()
        (pdir / 'actor.lt').write_bytes(b'actor')
        pin_hashes[str(pdir / 'actor.lt')] = hashlib.sha256(b'actor').hexdigest()
        (pdir / 'pin_manifest.json').write_text(json.dumps({'trial': t}))
        pin_hashes[str(pdir / 'pin_manifest.json')] = hashlib.sha256((pdir / 'pin_manifest.json').read_bytes()).hexdigest()

    state = dict(
        branches={},
        last_candidates={},
        population={'chronos': [{'name': 'arm_defense'}]},
    )

    # Execute prune_branches multiple times
    for _ in range(3):
        research.prune_branches(m, run, state)

    # Verify that all watch_pins files exist and hashes are 100% unchanged
    for path_str, expected_hash in pin_hashes.items():
        p = Path(path_str)
        assert p.is_file(), f"File in watch_pins was deleted: {p}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected_hash, f"File in watch_pins was corrupted: {p}"


def test_adversarial_corrupted_branch_prefers_pristine_pin(tmp_path):
    """Verify that if the source branch is corrupted (hash mismatch), find_exact ignores the corrupt branch
    and successfully recovers the genuine weights from watch_pins.
    """
    m, run, source, files, eval_data = setup_candidate_fixture(tmp_path, family='chronos', trial=88, delta=0.06)
    state = m.read(run / 'lab_state.json')
    result = dict(split='confirmation', decision='improved', statistics=eval_data['statistics'], summary={}, baseline_summary={})

    pinned_dir = research.pin_candidate(m, run, state, 'chronos', source, result, 'confirmation')
    assert pinned_dir.is_dir()

    # Adversarial action: Corrupt the source branch checkpoint
    (source / 'POLICY.lt').write_bytes(b'CORRUPTED_BYTES_IN_BRANCH_CHECKPOINT')

    target = w.trial_identity(m, run, 'chronos', 88)
    found = w.find_exact(m, run, target)

    # find_exact must reject the corrupted source branch and return the pristine pin in watch_pins
    assert found['kind'] == 'native'
    assert Path(found['path']).resolve() == pinned_dir.resolve()
    assert Path(found['path']).resolve() != source.resolve()

    # head_to_head.select also successfully selects the pinned actor with lookup: 'native'
    selection = head_to_head.select(m, run)
    assert selection['trial'] == 88
    assert selection['attempts'][0]['lookup'] == 'native'


def test_adversarial_incomplete_source_rejected_from_pinning(tmp_path):
    """Verify that an incomplete source directory (e.g. from an interrupted save) is rejected
    and does not create a broken pin or corrupt state.
    """
    root = tmp_path / 'gigaforge_incomplete'
    run = root / 'runs/research02'
    run.mkdir(parents=True, exist_ok=True)
    m = make_mock_m(root)

    source = run / 'branches/chronos/interrupted/checkpoints/1000'
    source.mkdir(parents=True, exist_ok=True)
    # Only POLICY.lt, missing SHARED_HEAD.lt
    (source / 'POLICY.lt').write_bytes(b'policy only')

    state = dict(trial=99, pinned_candidates={})
    result = dict(split='confirmation', decision='improved', statistics=dict(delta=0.05))

    ret = research.pin_candidate(m, run, state, 'chronos', source, result, 'confirmation')
    assert ret is None
    assert not (run / 'watch_pins').exists()
    assert 'pinned_candidates' in state and state['pinned_candidates'] == {}
