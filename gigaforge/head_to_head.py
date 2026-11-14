"""Frozen, resumable direct W/D/L: no learning, baseline copies or promotion."""
from pathlib import Path
from types import SimpleNamespace
import csv,hashlib,json,math,shutil,subprocess,time


TELEMETRY_COLS=[
 'saves_and_clears','failed_challenges','attacking_shots',
 'opp_possession_steps','goalside_shadow_steps',
 'ball_in_opp_half_steps','passive_net_camp_steps',
 'concede_unreachable_dive','concede_overcommit_behind_ball',
 'concede_boost_detour','concede_not_goalside_lane','concede_slow_recovery'
]


def validate(rows,pairs,seed,seconds,expected_opponent):
 expected={(seed+p,s) for p in range(pairs) for s in (0,1)}
 if len(rows)!=2*pairs or {(r['seed'],r['side']) for r in rows}!=expected:raise ValueError('Wrong or duplicate head-to-head round count')
 for r in rows:
  if r['opponent']!=expected_opponent or abs(r['seconds']-seconds)>1e-6:raise ValueError(f'Wrong opponent ({r["opponent"]} != {expected_opponent}) or timeout')
  a,b=r['goals_for'],r['goals_against']
  if any(type(x) is not int or x<0 for x in (a,b)) or r['outcome']!=((a>b)-(a<b)):raise ValueError('Invalid W/D/L outcome')


def summary(rows):
 from scipy.stats import t
 n=len(rows)
 wins=sum(r['outcome']==1 for r in rows);draws=sum(r['outcome']==0 for r in rows);losses=n-wins-draws
 score=(wins+.5*draws)/n if n else None
 gf=sum(r['goals_for'] for r in rows);ga=sum(r['goals_against'] for r in rows)
 blocks={}
 for r in rows:blocks.setdefault(r['seed'],[]).append((r['outcome']+1)/2)
 paired=[sum(v)/2 for v in blocks.values() if len(v)==2]
 lower=upper=se=t_crit=margin=None
 if len(paired)>=2:
  mean=sum(paired)/len(paired);variance=sum((v-mean)**2 for v in paired)/(len(paired)-1)
  se=math.sqrt(variance/len(paired))
  t_crit=float(t.ppf(.975,len(paired)-1))
  margin=t_crit*se if variance>0 else math.sqrt(math.log(40)/(2*len(paired)))
  lower=max(0.,mean-margin);upper=min(1.,mean+margin)
 verdict='uncertain'
 if lower is not None and lower>.5:verdict='candidate_ahead_in_this_test'
 elif upper is not None and upper<.5:verdict='opponent_ahead_in_this_test' if any(r.get('opponent','').startswith('chronos_') for r in rows) else 'original_ahead_in_this_test'
 out=dict(
  games=n,wins=wins,draws=draws,losses=losses,score_rate=score,
  goals_for=gf,goals_against=ga,goal_diff=gf-ga,
  goals_for_per_game=(gf/n if n else None),
  goals_against_per_game=(ga/n if n else None),
  goal_diff_per_game=((gf-ga)/n if n else None),
  paired_blocks=len(paired),paired_std_error=se,t_critical_95=t_crit,margin_95=margin,
  score_interval_95=[lower,upper],verdict=verdict,
  interval_method='Approximate paired-seed Student-t interval; both colors form one block. Zero sample variance uses a bounded Hoeffding interval. No automatic promotion.'
 )
 if n and all(k in rows[0] for k in TELEMETRY_COLS):
  totals={k:sum(int(r[k]) for r in rows) for k in TELEMETRY_COLS}
  opp_poss=totals['opp_possession_steps']
  opp_half=totals['ball_in_opp_half_steps']
  out['telemetry']=dict(
   totals=totals,
   per_game={k:totals[k]/n for k in TELEMETRY_COLS},
   goalside_shadow_rate=(totals['goalside_shadow_steps']/opp_poss if opp_poss>0 else None),
   passive_net_camp_rate=(totals['passive_net_camp_steps']/opp_half if opp_half>0 else None),
   concession_forensics_per_conceded_goal=({
    k:totals[k]/ga for k in (
     'concede_unreachable_dive','concede_overcommit_behind_ball',
     'concede_boost_detour','concede_not_goalside_lane','concede_slow_recovery'
    )
   } if ga>0 else None)
  )
 return out


def select(m,run,trial=None,family='chronos'):
 import trial_watch
 from research_eval import digest
 hashes={}
 def cached_sha(path):
  p=Path(path);stat=p.stat();key=(str(p.resolve()),stat.st_size,stat.st_mtime_ns)
  if key not in hashes:hashes[key]=m.sha(p)
  return hashes[key]
 proxy=SimpleNamespace(**vars(m));proxy.sha=cached_sha
 if trial is not None:
  target=trial_watch.trial_identity(proxy,run,family,trial)
  found=trial_watch.find_exact(proxy,run,target)
  if found['kind']=='missing':
   raise FileNotFoundError(f'Explicitly requested {family} trial {trial} weights not found')
  actor=trial_watch.prepare(proxy,run,family,trial)
  return dict(
   selection_mode='explicit_pinned_trial',
   trial=trial,
   family=family,
   arm=target['record'].get('arm'),
   confirmation_delta=target['delta'],
   confirmation_split=target['split'],
   files=target['files'],
   actor=str(actor),
   attempts=[dict(trial=trial,family=family,confirmation_delta=target['delta'],lookup=found['kind'])]
  )
 state=m.read(run/'lab_state.json');ranked=[];seen=set();attempts=[]
 for r in state.get('results',[]):
  if r['family'] not in ('chronos','galactus'):continue
  path=run/'evaluations'/f'lab_{r["trial"]:05d}_{r["family"]}_confirmation.json'
  if not path.is_file():continue
  result=m.read(path)
  if result['statistics']['delta']>0:ranked.append((result['statistics']['delta'],r))
 if not ranked:raise FileNotFoundError('No positive confirmation-test candidate recorded; no original or latest model substituted')
 for delta,r in sorted(ranked,key=lambda v:(v[0],v[1]['trial']),reverse=True):
  try:target=trial_watch.trial_identity(proxy,run,r['family'],r['trial'])
  except (OSError,ValueError,KeyError) as error:
   attempts.append(dict(trial=r['trial'],family=r['family'],lookup='identity_unavailable',error=str(error)));continue
  tag=digest(target['files'])
  if tag in seen:continue
  seen.add(tag);found=trial_watch.find_exact(proxy,run,target)
  attempts.append(dict(trial=r['trial'],family=r['family'],confirmation_delta=delta,lookup=found['kind']))
  if found['kind']=='missing':continue
  actor=trial_watch.prepare(proxy,run,r['family'],r['trial'])
  return dict(selection_mode='auto_positive_confirmation',trial=r['trial'],family=r['family'],arm=r.get('arm'),
   confirmation_delta=delta,files=target['files'],actor=str(actor),attempts=attempts)
 m.write(run/'h2h_selection.json',dict(status='no_weights_available',attempts=attempts))
 raise FileNotFoundError('No positive confirmation-test candidate weights found; see h2h_selection.json')


def native_actor(m,run,selection,settings,test,prefix='candidate'):
 """Use saved native components, or materialize a verified native-only export."""
 import torch
 from nova.giga_teachers import GigaNetwork
 from trial_watch import FILES
 actor=Path(selection['actor']);pin=actor.parent;family=selection['family']
 script=torch.jit.load(str(actor),map_location='cpu').eval()
 if not all((pin/n).is_file() for n in FILES):
  weights=script.state_dict()
  if any(k not in weights or torch.count_nonzero(weights[k]).item()!=0 for k in ('residual.2.weight','residual.2.bias')):
   raise ValueError('Export has non-core policy changes; cannot convert it to the exact native actor')
  pin=test/f'native_{prefix}';pin.mkdir(parents=True,exist_ok=True)
  torch.jit.save(script.core.head,str(pin/'SHARED_HEAD.lt'));torch.jit.save(script.core.policy,str(pin/'POLICY.lt'))
  m.seal_generation(pin,family)
 # Test both native archive loading and actual logits before a long tournament.
 size=225 if family=='chronos' else 258
 x=torch.linspace(-1,1,4*(size+3)).reshape(4,size+3)
 with torch.inference_mode():
  expected=script(x);torch.testing.assert_close(GigaNetwork(pin,family)(x[:,:size]),expected,rtol=0,atol=0)
 out=test/f'{prefix}_native_logits.json';recipe=m.base_recipe(run,family,settings,mode='self')
 recipe.update(anchor=str(pin),checkpoints='',games=2,probe_only=True,probe_input=x[:,:size].contiguous().flatten().tolist(),probe_output=str(out),stop_file=str(test/'STOP'),metrics_file=str(test/'unused_metrics.jsonl'))
 m.launch(recipe,log=test/f'{prefix}_native_parity.log')
 torch.testing.assert_close(torch.tensor(m.read(out)).reshape(4,90),expected,rtol=3e-5,atol=5e-5)
 return pin


def resolve_opponent(m,run,family,opponent_spec,settings,test):
 """Freeze and verify the exact opponent model for head-to-head testing."""
 from trial_watch import identity
 if opponent_spec in (None,'original',f'original_{family}'):
  from nova.teachers import verify_teacher
  original=verify_teacher(family)
  original_pin=test/'original';original_pin.mkdir(exist_ok=True)
  for file in ('SHARED_HEAD.lt','POLICY.lt'):shutil.copy2(original/file,original_pin/file)
  m.seal_generation(original_pin,family)
  return dict(
   name=f'original_{family}',
   mode='original_teacher',
   family=family,
   hitbox='breakout' if family=='chronos' else 'octane',
   source=str(original),
   pin=str(original_pin),
   files=identity(m,original_pin),
   actor_sha256=None
  )
 if opponent_spec=='chronos_lowtemp_swa':
  if family!='chronos':raise ValueError('chronos_lowtemp_swa opponent requires chronos family')
  r03_run=m.folder('research03')
  opp_sel=select(m,r03_run,trial=1,family='chronos')
  opp_source_pin=native_actor(m,r03_run,opp_sel,settings,test,prefix='opponent')
  opp_pin=test/'opponent_chronos_lowtemp_swa';opp_pin.mkdir(exist_ok=True)
  for file in ('SHARED_HEAD.lt','POLICY.lt'):shutil.copy2(opp_source_pin/file,opp_pin/file)
  m.seal_generation(opp_pin,family)
  if identity(m,opp_pin)!=opp_sel['files']:raise ValueError('Opponent pin hash mismatch vs research03 trial 1')
  return dict(
   name='chronos_lowtemp_swa',
   mode='explicit_pinned_preview',
   source_run='research03',
   source_trial=1,
   family=family,
   hitbox='breakout',
   source=str(opp_source_pin),
   pin=str(opp_pin),
   files=identity(m,opp_pin),
   actor=opp_sel['actor'],
   actor_sha256=m.sha(opp_sel['actor'])
  )
 raise ValueError(f'Unsupported head-to-head opponent specification: {opponent_spec}')


def run(m,name='research02',choice='auto',rounds=200,seconds=100.,batch_pairs=25,seed=1580000000,*,trial=None,family='chronos',opponent_spec=None):
 from filelock import FileLock
 from research_eval import digest
 from trial_watch import identity
 if rounds<2 or rounds%2 or seconds<=0 or seconds*15!=round(seconds*15) or batch_pairs<1:raise ValueError('Use an even game count, positive duration aligned to 1/15s, and positive batch size')
 if not 0<=seed<=2_000_000_000-rounds:raise ValueError('Seed outside the supported range')
 run=m.folder(name)
 if not (run/'lab_state.json').is_file():raise FileNotFoundError('Head-to-head testing requires an existing research run')
 test_root=run/'h2h';test_root.mkdir(parents=True,exist_ok=True)
 with FileLock(str(run/'train.lock'),timeout=0),FileLock(str(test_root/'test.lock'),timeout=0):
  probe=subprocess.run([str(m.binary()),'--head-to-head-protocol'],env=m.environment(),capture_output=True,text=True)
  if probe.returncode or probe.stdout.strip()!='direct-h2h-v1':raise RuntimeError('Install the complete 200-round test update, including native/GigaForge.exe')
  settings=m.read(run/'config.json');settings['device']=m.device(choice)
  opponent_key=opponent_spec or f'original_{family}'
  request=dict(rounds=rounds,seconds=seconds,batch_pairs=batch_pairs,seed=seed)
  if trial is not None:request['trial']=trial
  if opponent_spec is not None:request['opponent']=opponent_spec
  pointer=test_root/'active.json'
  if pointer.exists() and m.read(pointer).get('request')==request:
   test=(test_root/m.read(pointer)['directory']).resolve()
   if not test.is_relative_to(test_root.resolve()):raise ValueError('Invalid test path')
   state=m.read(test/'test.json')
   if state['binary_sha256']!=m.sha(m.binary()):raise ValueError('Native executable changed during this test. Keep the existing results and use a different --seed for a new test.')
  else:
   selection=select(m,run,trial=trial,family=family);family=selection['family']
   key_payload=dict(selection=selection['files'],family=family,request=request,binary=m.sha(m.binary()))
   key=digest(key_payload)[:16]
   test=test_root/key;test.mkdir(exist_ok=True)
   opp_info=resolve_opponent(m,run,family,opponent_spec,settings,test)
   candidate=native_actor(m,run,selection,settings,test)
   state=dict(
    status='ready',
    selection=selection,
    request=request,
    family=family,
    candidate=str(candidate),
    original=opp_info['pin'],
    opponent_name=opp_info['name'],
    opponent_info=opp_info,
    candidate_files=identity(m,candidate),
    original_files=opp_info['files'],
    binary_sha256=m.sha(m.binary()),
    device=settings['device'],
    actor_sha256=m.sha(selection['actor']),
    chunks=[],
    games=[],
    automatic_promotion=False
   )
   m.write(test/'test.json',state);m.write(pointer,dict(directory=test.name,request=request))
  stop=test/'STOP';stop.unlink(missing_ok=True)
  family=state['family'];settings['device']=state['device'];started=time.monotonic()
  opp_name=state.get('opponent_name','original_'+family)
  print(f'H2H_SELECTED: {family} trial {state["selection"]["trial"]} ({state["selection"].get("selection_mode","auto")}), prior confirmation difference {state["selection"]["confirmation_delta"]:+.2%}. Opponent: {opp_name}. Unverified candidate.',flush=True)
  print(f'H2H_TEST: {rounds} unique games, {seconds:g} simulated seconds each, {rounds//2} games per color. Draw at timeout; no overtime. No training or extra baseline games.',flush=True)
  print('H2H_OUTPUT:',test,flush=True)
  try:
   state['status']='running'
   for offset in range(0,rounds//2,batch_pairs):
    pairs=min(batch_pairs,rounds//2-offset);output=test/f'batch_{offset:04d}.json'
    if identity(m,Path(state['candidate']))!=state['candidate_files'] or identity(m,Path(state['original']))!=state['original_files']:raise ValueError('Frozen test weights changed')
    if stop.exists():break
    if output.exists():data=m.read(output)
    else:
     spec=dict(candidate=m.descriptor(state['candidate'],family),opponents=[dict(m.descriptor(state['original'],family),name=opp_name)],
      compare_baseline=False,pairs=pairs,seconds=seconds,seed=seed+offset,output=str(output),stop_file=str(stop))
     recipe=m.base_recipe(run,family,settings,mode='self');recipe.update(evaluation=spec,stop_file=str(stop))
     print(f'H2H_BATCH: games {2*offset+1}-{2*(offset+pairs)}/{rounds}',flush=True)
     m.launch(recipe,log=test/f'batch_{offset:04d}.log');data=m.read(output)
    if not data.get('direct_head_to_head') or data['baseline_trials']:raise ValueError('Native engine ran unwanted baseline copies')
    validate(data['trials'],pairs,seed+offset,seconds,opp_name)
    # Rebuild from completed batches; resuming never double-counts games.
    known={c['offset']:c for c in state['chunks']};known[offset]=dict(offset=offset,path=output.name,sha256=m.sha(output))
    state['chunks']=[known[k] for k in sorted(known)];games=[]
    for chunk in state['chunks']:
     path=test/chunk['path']
     if m.sha(path)!=chunk['sha256']:raise ValueError('Completed W/D/L batch changed')
     games.extend(m.read(path)['trials'])
    state['games']=games;state['summary']=summary(games)
    state['by_side']={('blue' if side==0 else 'orange'):summary([r for r in games if r['side']==side]) for side in (0,1)}
    m.write(test/'test.json',state)
    s=state['summary'];print(f'H2H_PROGRESS: {s["games"]}/{rounds}: {s["wins"]} W / {s["draws"]} D / {s["losses"]} L; goals {s["goals_for"]}:{s["goals_against"]}',flush=True)
   state['status']='complete' if len(state['games'])==rounds else 'paused'
  except KeyboardInterrupt:stop.touch();state['status']='paused'
  except Exception as error:
   state['status']='paused' if stop.exists() else 'error';state['error']=str(error)
   if state['status']=='error':raise
  finally:
   state['invocation_seconds']=time.monotonic()-started;m.write(test/'test.json',state)
   if state['games']:
    base_cols=['round','seed','side','opponent','goals_for','goals_against','outcome','seconds']
    extra_cols=[c for c in TELEMETRY_COLS if c in state['games'][0]]
    fieldnames=base_cols+extra_cols
    with (test/'games.csv').open('w',newline='',encoding='utf8') as out:
     writer=csv.DictWriter(out,fieldnames=fieldnames);writer.writeheader()
     for i,row in enumerate(state['games'],1):writer.writerow(dict(round=i,**{k:row[k] for k in fieldnames if k!='round'}))
   m.write(run/'latest_h2h.json',state)
  print('H2H_RESULT:',state['status'],state.get('summary',{}),flush=True)
  return state
