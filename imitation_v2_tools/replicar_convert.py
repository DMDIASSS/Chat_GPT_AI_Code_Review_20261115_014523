"""Safe wrapper around upstream Rolv-Arild/replicar v2 CLI. Not a replacement for it."""
import argparse, subprocess, shutil, sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--replicar',default='replicar',help='Path to compiled replicar executable')
    p.add_argument('--input',type=Path,default=Path('data/replays/ranked-duels'))
    p.add_argument('--output',type=Path,default=Path('data/replicar/duels'))
    p.add_argument('--meshes',type=Path,required=True,help='RocketSim collision_meshes directory')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--tick-step',type=int,default=8)
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    exe=shutil.which(a.replicar) or str(Path(a.replicar).resolve())
    if not a.input.is_dir(): p.error(f'Input replay directory missing: {a.input}')
    if not a.meshes.is_dir() or not list(a.meshes.rglob('*.cmf')):
        p.error(f'Missing RocketSim .cmf mesh files under {a.meshes}')
    if a.jobs<1 or a.tick_step<1: p.error('jobs and tick-step must be positive')
    cmd=[exe,'convert',str(a.input.resolve()),'-o',str(a.output.resolve()),
         '--jobs',str(a.jobs),'--tick-step',str(a.tick_step),'--meshes',str(a.meshes.resolve())]
    print('Command:',subprocess.list2cmdline(cmd),flush=True)
    if a.dry_run:return
    a.output.mkdir(parents=True,exist_ok=True)
    r=subprocess.run(cmd,check=False)
    if r.returncode: sys.exit(r.returncode)
    print('Conversion complete. Check index.parquet errors; outputs are NOT automatically accepted as quality labels.')

if __name__=='__main__':main()
