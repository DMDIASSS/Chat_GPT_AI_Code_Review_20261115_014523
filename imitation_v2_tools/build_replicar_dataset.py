"""Create imitation NPZ shards from replicar v2 Parquet (only causal inputs).

One complete replay SHA is permanently in just one split. Future outcome is a
TARGET and is never included in an observation. TAS is not used here.
"""
import argparse, hashlib, json, math, re
from pathlib import Path
import numpy as np

HISTORY=8
CHUNK=8
ACTION=('throttle','steer','pitch','yaw','roll','jump','boost','handbrake')
SPLITS=('train','val','test')


def replay_split(key:str)->str:
    n=int(hashlib.sha256(('imitation-2026-replay-split-v1/'+key).encode()).hexdigest()[:12],16)%100
    return 'test' if n < 10 else 'val' if n < 20 else 'train'


def rot_forward_up(quat):
    # replicar documented (x,y,z,w) quaternions
    x,y,z,w=quat
    if not np.isfinite(quat).all() or abs(np.linalg.norm(quat)-1)>0.15:
        return np.zeros(3,dtype=np.float32),np.zeros(3,dtype=np.float32)
    f=np.array([1-2*(y*y+z*z),2*(x*y+z*w),2*(x*z-y*w)],dtype=np.float32)
    up=np.array([2*(x*z+y*w),2*(y*z-x*w),1-2*(x*x+y*y)],dtype=np.float32)
    return f,up


def col(d,key,n,default=np.nan):
    return np.asarray(d.get(key,np.full(n,default)),dtype=np.float32)


def make_features(d,players,ego):
    n=len(d['sim_tick'])
    team=int(players[ego]['team'])
    # Rotate only the GAME FRAME 180deg for orange; controls remain car-local.
    flip=np.array([-1.,-1.,1.],dtype=np.float32) if team==1 else np.ones(3,dtype=np.float32)
    result=[]
    for name in ('ball_position','ball_velocity','ball_angular_velocity'):
        fields=np.stack([col(d,f'{name}_{k}',n) for k in 'xyz'],axis=-1)
        result.append(fields*flip / (4096 if name.endswith('position') else 2300 if name.endswith('velocity') else 5.5))
    teammates=[p['index'] for p in players if p['index']!=ego and p['team']==team]
    opponents=[p['index'] for p in players if p['team']!=team]
    if len(teammates)>1 or len(opponents)>2:raise ValueError('Not a 1v1/2v2 match')
    slots=[ego]+teammates+[-1]*(1-len(teammates))+opponents+[-1]*(2-len(opponents))
    for slot in slots:
        if slot<0:
            result.append(np.zeros((n,18),dtype=np.float32));continue
        arrays=[]
        for suffix in ('position','velocity','angular_velocity'):
            v=np.stack([col(d,f'car_{slot}_{suffix}_{k}',n) for k in 'xyz'],axis=-1)
            v=v*flip/(4096 if suffix=='position' else 2300 if suffix=='velocity' else 5.5)
            arrays.append(v)
        q=np.stack([col(d,f'car_{slot}_rotation_{k}',n) for k in 'xyzw'],axis=-1)
        f=np.zeros((n,3),np.float32);u=np.zeros((n,3),np.float32)
        for j in range(n):f[j],u[j]=rot_forward_up(q[j]);f[j]*=flip;u[j]*=flip
        arrays.extend((f,u))
        arrays.append((col(d,f'car_{slot}_boost',n)/100)[:,None])
        arrays.append(col(d,f'car_{slot}_is_on_ground',n,0)[:,None])
        arrays.append(np.isfinite(arrays[0][:,0]).astype(np.float32)[:,None])
        result.append(np.concatenate(arrays,axis=1))
    # Avoid unknown pad ordering or geometry until mapping is verified.
    score=(col(d,'blue_score',n,0)-col(d,'orange_score',n,0))*(1 if team==0 else -1)
    result += [np.stack((score/10,col(d,'seconds_remaining',n,300)/300,
                         np.full(n,float(team))),axis=1)]
    features=np.concatenate(result,axis=1)
    assert features.shape[1]==84,features.shape
    return np.nan_to_num(features,nan=0.,posinf=0.,neginf=0.).clip(-5,5).astype('float32')


def make_labels(d,player,team):
    n=len(d['sim_tick'])
    act=np.stack([col(d,f'car_{player}_controls_{k}',n) for k in ACTION],axis=-1)
    valid=np.isfinite(act).all(axis=-1)
    act=np.nan_to_num(act,nan=0.).astype('float32')
    act[:,:5]=act[:,:5].clip(-1,1)
    act[:,5:]=act[:,5:].clip(0,1)
    end=np.asarray(d.get('future_segment_end',[None]*n),dtype=object)
    seconds=col(d,'future_seconds_until_segment_end',n)
    value=np.zeros(n,dtype=np.int64)
    for j in range(n):
        if np.isfinite(seconds[j]) and seconds[j]<=10 and end[j] in ('blue_goal','orange_goal'):
            scoring_team=0 if end[j]=='blue_goal' else 1
            value[j]=1 if scoring_team==team else 2
    return act,valid,value


def dataset_from_dict(d,header,history=HISTORY,chunk=CHUNK,stride=4,max_samples=2500,tick_step=8):
    players=header.get('players',[])
    # Future fields are allowed ONLY as targets, and must be available.
    for k in ('future_segment_end','future_seconds_until_segment_end'):
        if k not in d: raise ValueError(f'Missing supervised value target {k}')
    for k in ('sim_tick','segment'):
        if k not in d: raise ValueError(f'Missing sequence key {k}')
    for k in ('ball_position_x','ball_position_y','ball_position_z',
              'ball_velocity_x','ball_velocity_y','ball_velocity_z'):
        if k not in d: raise ValueError(f'Missing ball observation {k}')
    if not len(players) in (2,4): raise ValueError('Unsupported player count')
    if sorted([sum(p['team']==t for p in players) for t in (0,1)]) != [len(players)//2]*2:
        raise ValueError('Teams not balanced')
    # Use only play segments, not goal replays / countdowns.
    ticks=np.asarray(d['sim_tick'])
    segments=np.asarray(d['segment'],dtype=object)
    collected=[]
    for p in players:
        ego=int(p['index']);team=int(p['team'])
        essential=[f'car_{ego}_{field}_{axis}' for field in ('position','velocity','rotation')
                   for axis in ('xyzw' if field=='rotation' else 'xyz')]
        essential += [f'car_{ego}_controls_{key}' for key in ACTION]
        absent=[k for k in essential if k not in d]
        if absent:raise ValueError(f'Missing required car column(s): {absent[:3]}')
        obs_ok=np.ones(len(ticks),dtype=bool)
        for k in essential:
            obs_ok &= np.isfinite(col(d,k,len(ticks)))
        feat=make_features(d,players,ego)
        actions,valid,values=make_labels(d,ego,team)
        for i in range(history-1,len(ticks)-chunk+1,stride):
            lo=i-history+1;hi=i+chunk
            seg=segments[lo:hi]
            if any(x is None for x in seg) or not all(s==seg[0] for s in seg):continue
            # No jump over pause/interpolation gap.
            if not np.all(np.diff(ticks[lo:hi].astype(np.int64)) == tick_step): continue
            if not valid[i:hi].all() or not obs_ok[lo:hi].all():continue
            if not np.isfinite(feat[lo:i+1]).all():continue
            collected.append((feat[lo:i+1],actions[i:hi],values[i]))
    if len(collected)>max_samples:
        rng=np.random.default_rng(int(hashlib.sha256(header['replay_sha256'].encode()).hexdigest()[:16],16))
        selected=np.sort(rng.choice(len(collected),max_samples,replace=False))
        collected=[collected[int(j)] for j in selected]
    if not collected: raise ValueError('No continuous, valid windows')
    x=np.stack([z[0] for z in collected]).astype('float32')
    y=np.stack([z[1] for z in collected]).astype('float32')
    v=np.array([z[2] for z in collected],dtype='int64')
    return x,y,v


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,default=Path('data/replicar'))
    p.add_argument('--output',type=Path,default=Path('data/imitation_npz'))
    p.add_argument('--tick-step',type=int,default=8)
    p.add_argument('--max-samples-per-replay',type=int,default=2500)
    a=p.parse_args()
    try:import pyarrow.parquet as pq
    except ImportError: p.error('Install Parquet reader: pip install pyarrow')
    if a.tick_step<1 or a.max_samples_per_replay<1:p.error('positive numbers required')
    paths=sorted(x for x in a.input.rglob('*.parquet') if x.name!='index.parquet')
    if not paths:p.error(f'No converted Parquet replays in {a.input}; run replicar first')
    a.output.mkdir(parents=True,exist_ok=True)
    seen=set();summary=[]
    for path in paths:
        try:
            f=pq.ParquetFile(path)
            raw=f.metadata.metadata.get(b'replicar')
            if not raw:raise ValueError('Not replicar v2 Parquet')
            header=json.loads(raw)
            sha=header['replay_sha256']
            if sha in seen:continue
            seen.add(sha)
            if int(header.get('tick_step',-1))!=a.tick_step:
                raise ValueError(f'tick_step mismatch expected {a.tick_step} got {header.get("tick_step")}')
            table=f.read()
            d={name:table[name].to_pylist() for name in table.column_names if not name.startswith('pad_')}
            x,y,v=dataset_from_dict(d,header,tick_step=a.tick_step,max_samples=a.max_samples_per_replay)
            split=replay_split(sha)
            dest=a.output/split
            dest.mkdir(exist_ok=True,parents=True)
            np.savez_compressed(dest/(sha+'.npz'),x=x,y=y,v=v)
            print('OK',split,path.name,x.shape)
            summary.append({'source':str(path),'sha256':sha,'split':split,'samples':len(x),'players':len(header['players']),'status':'ok'})
        except (ValueError,KeyError,TypeError,IndexError,AssertionError) as e:
            print('REJECT',path.name,str(e)[:150])
            summary.append({'source':str(path),'status':'rejected','reason':str(e)})
    (a.output/'manifest.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print('Replays admitted',sum(z['status']=='ok' for z in summary),'/',len(summary))

if __name__=='__main__':main()
