"""Watch any pinned candidate actor against original_chronos or against chronos_lowtemp_swa in rlviser."""
from __future__ import annotations
from contextlib import chdir
import argparse, pathlib, sys, time
import torch
from filelock import FileLock

ROOT = pathlib.Path(__file__).resolve().parent
NOVA = ROOT.parent / "NovaForge"
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(NOVA))

import run as gf_run
import trial_watch
from nova.core import sha256
from nova.forge_env import ForgeEnv
from nova.forge_eval import action
from nova.forge_models import check_actor
from nova.viewer import prepare_viewer, learner_first_state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="research04")
    parser.add_argument("--trial", type=int, default=1)
    parser.add_argument("--actor", default=None, help="Explicit path to actor.lt")
    parser.add_argument("--opponent", choices=["original_chronos", "chronos_lowtemp_swa", "original_galactus", "ripple", "ducky"], default="original_chronos")
    parser.add_argument("--profile", choices=["match", "defense", "pressure", "balanced"], default="match")
    args = parser.parse_args()

    if args.actor:
        actor_path = pathlib.Path(args.actor).resolve()
    else:
        run_dir = gf_run.folder(args.run)
        actor_path = trial_watch.prepare(gf_run, run_dir, "chronos", args.trial)

    actor = torch.jit.load(str(actor_path), map_location="cpu").eval()
    torch.set_num_threads(1)
    check_actor(actor_path, "chronos")

    cfg = gf_run.read(NOVA / "configs/forge_league.json")
    cfg["hitboxes"] = {"chronos": "breakout", "galactus": "octane", "ripple": "octane", "ducky": "octane"}

    if args.opponent == "original_chronos":
        opp_entry = {"name": "chronos", "hitbox": "breakout"}
        opp_label = "original_chronos (Breakout)"
    elif args.opponent == "original_galactus":
        opp_entry = {"name": "galactus", "hitbox": "octane"}
        opp_label = "original_galactus (Octane)"
    elif args.opponent == "chronos_lowtemp_swa":
        r03_actor = trial_watch.prepare(gf_run, gf_run.folder("research03"), "chronos", 1)
        opp_entry = {
            "name": "chronos",
            "hitbox": "breakout",
            "path": str(r03_actor),
            "sha256": sha256(r03_actor),
        }
        opp_label = "chronos_lowtemp_swa preview (Breakout)"
    elif args.opponent == "ripple":
        opp_entry = {"name": "ripple", "hitbox": "octane"}
        opp_label = "ripple (Octane)"
    elif args.opponent == "ducky":
        opp_entry = {"name": "ducky", "hitbox": "octane"}
        opp_label = "ducky (Octane)"

    lock = NOVA / "work/rlviser-watch.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock), timeout=0), chdir(NOVA):
        prepare_viewer(mode="auto")
        from rlgym.rocket_league.rlviser import RLViserRenderer
        scenario = "kickoff" if args.profile == "match" else None
        env = ForgeEnv(cfg, "chronos", [opp_entry], profile=args.profile, side=0, scenario=scenario)
        renderer = RLViserRenderer(tick_rate=15)
        try:
            obs, _ = env.reset(seed=271031)
            print(
                f"WATCH [{args.profile}]: Blue = {args.run} trial {args.trial} (Breakout) | "
                f"Orange = {opp_label}. Ctrl+C stops.",
                flush=True,
            )
            while True:
                started = time.monotonic()
                obs, _, terminal, _, info = env.step(action(actor, obs, "chronos"))
                renderer.render(learner_first_state(env.arena.state, env.arena.agent), {})
                if terminal:
                    print("MATCH:", info, flush=True)
                    obs, _ = env.reset()
                time.sleep(max(0.0, 1.0 / 15.0 - (time.monotonic() - started)))
        except KeyboardInterrupt:
            pass
        finally:
            try:
                renderer.close()
            finally:
                env.close()


if __name__ == "__main__":
    main()
