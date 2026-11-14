import sys,struct,hashlib
from pathlib import Path
import unittest,tempfile
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]))
from audit_sources import audit_tas,audit_replays
from build_replicar_dataset import dataset_from_dict,replay_split
from quality_gate import assess


def fake_game(n=60):
    d={'sim_tick':list(range(0,8*n,8)),'segment':[0]*n,
       'future_segment_end':['blue_goal']*n,
       'future_seconds_until_segment_end':[4.0]*n,
       'blue_score':[1]*n,'orange_score':[0]*n,'seconds_remaining':[300]*n}
    for k in 'xyz':
        d['ball_position_'+k]=[0.]*n
        d['ball_velocity_'+k]=[0.]*n
        d['ball_angular_velocity_'+k]=[0.]*n
    for i in (0,1):
        for suffix in ('position','velocity','angular_velocity'):
            for k in 'xyz':d[f'car_{i}_{suffix}_{k}']=[0.]*n
        for k in 'xyzw':d[f'car_{i}_rotation_{k}']=[1. if k=='w' else 0.]*n
        d[f'car_{i}_boost']=[100.]*n
        d[f'car_{i}_is_on_ground']=[1.]*n
        for k in ('throttle','steer','pitch','yaw','roll','jump','boost','handbrake'):
            d[f'car_{i}_controls_{k}']=[1. if k=='throttle' else 0.]*n
    h={'players':[{'index':0,'team':0},{'index':1,'team':1}], 'replay_sha256':'abcd'*16}
    return d,h

class PipelineTests(unittest.TestCase):
    def test_tas_struct_and_replay_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'one.data').write_bytes(struct.pack('<II',1,2)+b'\x00'*(2*32+128))
            t=audit_tas(p)
            self.assertEqual(t['total_records'],2)
            self.assertEqual(t['structurally_valid'],1)
            (p/'a.replay').write_bytes(struct.pack('<II',8,1)+b'\0'*128)
            (p/'b.replay').write_bytes(struct.pack('<II',8,1)+b'\0'*128)
            self.assertEqual(audit_replays(p)['duplicate_files'],1)
    def test_split_stable(self):
        self.assertEqual(replay_split('foo'),replay_split('foo'))
        self.assertIn(replay_split('bar'),('train','val','test'))
    def test_future_labels_not_features(self):
        d,h=fake_game()
        x,y,v=dataset_from_dict(d,h)
        self.assertEqual(x.shape[1:],(8,84))
        self.assertEqual(y.shape[1:],(8,8))
        self.assertEqual(set(v),{1,2})
        d['future_segment_end']=['orange_goal']*len(d['sim_tick'])
        x2,y2,v2=dataset_from_dict(d,h)
        self.assertTrue(np.array_equal(x,x2))
        self.assertTrue(np.array_equal(y,y2))
        self.assertTrue(np.array_equal(3-v,v2))
    def test_no_cross_segment_windows(self):
        d,h=fake_game()
        d['segment']=[0]*20+[1]*40
        x,y,v=dataset_from_dict(d,h)
        self.assertGreater(len(x),0)
        self.assertLess(len(x), 100)
    def test_promotion_gate_fails_closed(self):
        self.assertFalse(assess({})[0])
        self.assertTrue(assess({'heldout_replays':30,'replay_reconstruction_position_p90_uu':3.5,
              'rollout_matches':100,'model_only_winrate':0.55,'baseline_winrate':0.5,
              'model_only_own_goals':0,'baseline_own_goals':0,'planner_p95_ms':50})[0])
    def test_model_gradient(self):
        import torch
        from train_imitation import create_model,loss_metrics
        model=create_model()
        params=sum(p.numel() for p in model.parameters())
        self.assertGreater(params,3_000_000)
        self.assertLess(params,4_000_000)
        p,v=model(torch.rand(2,8,84))
        loss,ms=loss_metrics(p,v,torch.rand(2,8,8),torch.tensor([0,1]))
        loss.backward()
        self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for p in model.parameters()))
if __name__=='__main__':unittest.main()
