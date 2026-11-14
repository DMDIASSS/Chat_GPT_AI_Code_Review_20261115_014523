"""Fail-closed candidate promotion gate; no training reward proxy can pass it."""
import argparse,json,sys
from pathlib import Path

# Independent evaluator should emit JSON with actual matches and model-only play.
REQUIRED=('heldout_replays','replay_reconstruction_position_p90_uu',
          'rollout_matches','model_only_winrate','baseline_winrate',
          'model_only_own_goals','baseline_own_goals','planner_p95_ms')

def assess(v):
    errors=[]
    for k in REQUIRED:
        if k not in v:errors.append(f'missing {k}')
    if errors:return False,errors
    if v['heldout_replays']<20:errors.append('heldout_replays < 20')
    if v['replay_reconstruction_position_p90_uu']>10:errors.append('reconstruction p90 > 10 UU (proposal, calibrate locally)')
    if v['rollout_matches']<100:errors.append('rollout_matches < 100')
    if v['model_only_winrate']<v['baseline_winrate']:errors.append('model-only policy loses to baseline')
    if v['model_only_own_goals']>v.get('baseline_own_goals',0):errors.append('own goals exceed baseline')
    if v['planner_p95_ms']>60:errors.append('planner p95 exceeds suggested 15Hz decision-time budget')
    return not errors,errors

def main():
    p=argparse.ArgumentParser();p.add_argument('independent_evaluation_json',type=Path);a=p.parse_args()
    v=json.loads(a.independent_evaluation_json.read_text())
    ok,errors=assess(v)
    print('PASS independent gate' if ok else 'FAIL: '+', '.join(errors))
    sys.exit(0 if ok else 2)
if __name__=='__main__':main()
