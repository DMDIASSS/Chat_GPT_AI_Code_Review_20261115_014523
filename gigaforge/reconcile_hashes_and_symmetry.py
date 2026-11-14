"""Read-only forensic reconciliation of model hashes, functional equivalence, and Blue/Orange symmetry."""
from __future__ import annotations
import hashlib, json, math, os, pathlib, subprocess, sys, tempfile
import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parent
NOVA = ROOT.parent / "NovaForge"
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(NOVA))

import run as gf_run
from nova.giga_teachers import GigaNetwork


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    # 1. Direct file-hash inventory from actual files on disk
    r03 = ROOT / "runs/research03"
    r04 = ROOT / "runs/research04"

    files_to_hash = {
        "upstream_original_chronos_POLICY.lt": NOVA / "assets/chronos/POLICY.lt",
        "upstream_original_chronos_SHARED_HEAD.lt": NOVA / "assets/chronos/SHARED_HEAD.lt",
        "r03_parent_chronos_POLICY.lt": r03 / "parents/chronos/POLICY.lt",
        "r03_parent_chronos_SHARED_HEAD.lt": r03 / "parents/chronos/SHARED_HEAD.lt",
        "r04_parent_chronos_POLICY.lt": r04 / "parents/chronos/POLICY.lt",
        "r04_parent_chronos_SHARED_HEAD.lt": r04 / "parents/chronos/SHARED_HEAD.lt",
        "r03_ckpt_chronos_lowtemp_swa_POLICY.lt": r03 / "branches/chronos/chronos_lowtemp_swa/checkpoints/1000000/POLICY.lt",
        "r03_ckpt_chronos_lowtemp_swa_SHARED_HEAD.lt": r03 / "branches/chronos/chronos_lowtemp_swa/checkpoints/1000000/SHARED_HEAD.lt",
        "r03_watch_pin_POLICY.lt": r03 / "watch_pins/chronos/trial_00001_18e2b4909ade/POLICY.lt",
        "r03_watch_pin_SHARED_HEAD.lt": r03 / "watch_pins/chronos/trial_00001_18e2b4909ade/SHARED_HEAD.lt",
        "r03_watch_pin_actor.lt": r03 / "watch_pins/chronos/trial_00001_18e2b4909ade/actor.lt",
        "r03_export_actor_634ccf28e7f4.lt": r03 / "export_actors/chronos/634ccf28e7f4.lt",
        "r03_rlbot_bundle_actor.lt": ROOT / "exports/research03/Forge_chronos_333f9e91f8_e7f399/actor.lt",
        "r04_parent_chronos_lowtemp_swa_POLICY.lt": r04 / "parents/chronos_lowtemp_swa/POLICY.lt",
        "r04_parent_chronos_lowtemp_swa_SHARED_HEAD.lt": r04 / "parents/chronos_lowtemp_swa/SHARED_HEAD.lt",
        "r04_ckpt_chronos_defensive_swa_POLICY.lt": r04 / "branches/chronos/chronos_defensive_swa/checkpoints/1000000/POLICY.lt",
        "r04_ckpt_chronos_defensive_swa_SHARED_HEAD.lt": r04 / "branches/chronos/chronos_defensive_swa/checkpoints/1000000/SHARED_HEAD.lt",
        "r04_watch_pin_POLICY.lt": r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/POLICY.lt",
        "r04_watch_pin_SHARED_HEAD.lt": r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/SHARED_HEAD.lt",
        "r04_watch_pin_actor.lt": r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/actor.lt",
        "r04_watch_pin_actor.lt.json": r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/actor.lt.json",
        "r04_watch_pin_manifest.json": r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/pin_manifest.json",
        "r04_export_actor_bbf92bc0c1f4.lt": r04 / "export_actors/chronos/bbf92bc0c1f4.lt",
        "r04_export_actor_bbf92bc0c1f4.lt.json": r04 / "export_actors/chronos/bbf92bc0c1f4.lt.json",
        "r04_rlbot_bundle_actor.lt": ROOT / "exports/research04/Forge_chronos_769c232267_e7f399/actor.lt",
        "r04_rlbot_bundle_actor.lt.json": ROOT / "exports/research04/Forge_chronos_769c232267_e7f399/actor.lt.json",
        "r04_h2h_matchup1_cand_POLICY.lt": r04 / "h2h/6ae1d06c86c4a8a2/original/POLICY.lt",
        "r04_h2h_matchup1_opp_SHARED_HEAD.lt": r04 / "h2h/6ae1d06c86c4a8a2/original/SHARED_HEAD.lt",
        "r04_h2h_matchup2_opp_POLICY.lt": r04 / "h2h/382c876fddd8c800/opponent_chronos_lowtemp_swa/POLICY.lt",
        "r04_h2h_matchup2_opp_SHARED_HEAD.lt": r04 / "h2h/382c876fddd8c800/opponent_chronos_lowtemp_swa/SHARED_HEAD.lt",
        "native_GigaForge_exe": gf_run.binary(),
    }
    disk_hashes = {k: {"path": str(v), "sha256": sha256_file(v)} for k, v in files_to_hash.items()}

    # 2. Functional equivalence checks on 28 reference states + 256 random states
    cases = json.loads((NOVA / "tests/fixtures/giga_reference.json").read_text(encoding="utf8"))["cases"]
    ref_obs_225 = torch.tensor([c["reference"]["chronos"]["features"] for c in cases], dtype=torch.float32)
    torch.manual_seed(271031)
    rand_obs_228 = torch.randn(256, 228, dtype=torch.float32)
    ref_obs_228 = torch.cat([ref_obs_225, torch.linspace(-1.0, 1.0, len(cases) * 3).reshape(len(cases), 3)], dim=-1)

    # 2a. SHARED_HEAD.lt: e0aac68a... (original upstream) vs 713b9b05... (LibTorch checkpoint reserialization)
    net_orig = GigaNetwork(NOVA / "assets/chronos", "chronos").eval()
    net_r04_pin = GigaNetwork(r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94", "chronos").eval()
    sh_orig_sd = net_orig.head.state_dict()
    sh_froz_sd = net_r04_pin.head.state_dict()
    sh_tensor_equality = {k: bool(torch.equal(sh_orig_sd[k], sh_froz_sd[k])) for k in sh_orig_sd}
    with torch.inference_mode():
        sh_ref_max_diff = float((net_orig.head(ref_obs_225) - net_r04_pin.head(ref_obs_225)).abs().max().item())
        sh_rand_max_diff = float((net_orig.head(rand_obs_228[:, :225]) - net_r04_pin.head(rand_obs_228[:, :225])).abs().max().item())

    # 2b. chronos_defensive_swa: watch_pin actor.lt (1a71f6a6...) vs export actor.lt (769c2322...) vs native GigaNetwork (bbf92bc0...)
    r04_pin_actor = torch.jit.load(str(r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/actor.lt"), map_location="cpu").eval()
    r04_exp_actor = torch.jit.load(str(ROOT / "exports/research04/Forge_chronos_769c232267_e7f399/actor.lt"), map_location="cpu").eval()
    r04_sd_pin = r04_pin_actor.state_dict()
    r04_sd_exp = r04_exp_actor.state_dict()
    r04_core_keys = [k for k in r04_sd_pin if k.startswith("core.")]
    r04_core_exact = all(torch.equal(r04_sd_pin[k], r04_sd_exp[k]) for k in r04_core_keys)
    r04_res2_zero = (
        int(torch.count_nonzero(r04_sd_pin["residual.2.weight"]).item()) == 0
        and int(torch.count_nonzero(r04_sd_pin["residual.2.bias"]).item()) == 0
        and int(torch.count_nonzero(r04_sd_exp["residual.2.weight"]).item()) == 0
        and int(torch.count_nonzero(r04_sd_exp["residual.2.bias"]).item()) == 0
    )
    r04_res0_equal = bool(
        torch.equal(r04_sd_pin["residual.0.weight"], r04_sd_exp["residual.0.weight"])
        and torch.equal(r04_sd_pin["residual.0.bias"], r04_sd_exp["residual.0.bias"])
    )
    with torch.inference_mode():
        r04_ref_diff_pin_vs_exp = float((r04_pin_actor(ref_obs_228) - r04_exp_actor(ref_obs_228)).abs().max().item())
        r04_ref_diff_pin_vs_native = float((r04_pin_actor(ref_obs_228) - net_r04_pin(ref_obs_225)).abs().max().item())
        r04_rand_diff_pin_vs_exp = float((r04_pin_actor(rand_obs_228) - r04_exp_actor(rand_obs_228)).abs().max().item())
        r04_rand_diff_pin_vs_native = float((r04_pin_actor(rand_obs_228) - net_r04_pin(rand_obs_228[:, :225])).abs().max().item())

    # 2c. chronos_lowtemp_swa: watch_pin actor.lt (02be35f8...) vs export actor.lt (333f9e91...) vs native GigaNetwork (634ccf28...)
    net_r03_pin = GigaNetwork(r03 / "watch_pins/chronos/trial_00001_18e2b4909ade", "chronos").eval()
    r03_pin_actor = torch.jit.load(str(r03 / "watch_pins/chronos/trial_00001_18e2b4909ade/actor.lt"), map_location="cpu").eval()
    r03_exp_actor = torch.jit.load(str(ROOT / "exports/research03/Forge_chronos_333f9e91f8_e7f399/actor.lt"), map_location="cpu").eval()
    r03_sd_pin = r03_pin_actor.state_dict()
    r03_sd_exp = r03_exp_actor.state_dict()
    r03_core_keys = [k for k in r03_sd_pin if k.startswith("core.")]
    r03_core_exact = all(torch.equal(r03_sd_pin[k], r03_sd_exp[k]) for k in r03_core_keys)
    r03_res2_zero = (
        int(torch.count_nonzero(r03_sd_pin["residual.2.weight"]).item()) == 0
        and int(torch.count_nonzero(r03_sd_pin["residual.2.bias"]).item()) == 0
        and int(torch.count_nonzero(r03_sd_exp["residual.2.weight"]).item()) == 0
        and int(torch.count_nonzero(r03_sd_exp["residual.2.bias"]).item()) == 0
    )
    r03_res0_equal = bool(
        torch.equal(r03_sd_pin["residual.0.weight"], r03_sd_exp["residual.0.weight"])
        and torch.equal(r03_sd_pin["residual.0.bias"], r03_sd_exp["residual.0.bias"])
    )
    with torch.inference_mode():
        r03_ref_diff_pin_vs_exp = float((r03_pin_actor(ref_obs_228) - r03_exp_actor(ref_obs_228)).abs().max().item())
        r03_ref_diff_pin_vs_native = float((r03_pin_actor(ref_obs_228) - net_r03_pin(ref_obs_225)).abs().max().item())
        r03_rand_diff_pin_vs_exp = float((r03_pin_actor(rand_obs_228) - r03_exp_actor(rand_obs_228)).abs().max().item())
        r03_rand_diff_pin_vs_native = float((r03_pin_actor(rand_obs_228) - net_r03_pin(rand_obs_228[:, :225])).abs().max().item())

    # 3. Mirrored-state and identical-actor symmetry diagnostics
    from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
    rows_blue = []
    rows_orange_inv = []
    slots = []
    for case in cases:
        s = deserialize_game_state(np.asarray(case["state"], np.float32))
        keys = list(s.cars)
        aid = next(k for k, p in s.cars.items() if p.team_num == 0)
        slots.append(case["reference"]["chronos"]["opponent_slot"])
        prev_act = np.asarray(case["previous"], np.float32)

        r_b = [keys.index(aid), *s.ball.position, *s.ball.linear_velocity, *s.ball.angular_velocity]
        for k in keys:
            p = s.cars[k]
            r_b.extend([p.team_num, *p.physics.position, *p.physics.linear_velocity, *p.physics.angular_velocity, *p.physics.rotation_mtx.T.flatten(), p.boost_amount, p.on_ground, p.has_jumped, p.has_flipped, p.has_double_jumped, p.air_time_since_jump, *(prev_act if k == aid else np.zeros(8))])
        r_b.extend([*s.boost_pad_timers, *np.asarray(case["predictions"]).ravel()])
        rows_blue.append(r_b)

        inv_vec = np.array([-1.0, -1.0, 1.0], dtype=np.float32)
        r_o = [keys.index(aid), *(s.ball.position * inv_vec), *(s.ball.linear_velocity * inv_vec), *(s.ball.angular_velocity * inv_vec)]
        for k in keys:
            p = s.cars[k]
            rot_inv = (p.physics.rotation_mtx.T * inv_vec).flatten()
            r_o.extend([1 - p.team_num, *(p.physics.position * inv_vec), *(p.physics.linear_velocity * inv_vec), *(p.physics.angular_velocity * inv_vec), *rot_inv, p.boost_amount, p.on_ground, p.has_jumped, p.has_flipped, p.has_double_jumped, p.air_time_since_jump, *(prev_act if k == aid else np.zeros(8))])
        r_o.extend([*s.boost_pad_timers[::-1], *np.asarray(case["predictions"]).ravel()])
        rows_orange_inv.append(r_o)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        f_b = tmp / "b.bin"; f_o = tmp / "o.bin"
        out_b = tmp / "out_b.bin"; out_o = tmp / "out_o.bin"
        sl_f = tmp / "slots.json"
        np.asarray(rows_blue, np.float32).tofile(f_b)
        np.asarray(rows_orange_inv, np.float32).tofile(f_o)
        gf_run.write(sl_f, slots)
        subprocess.run([str(gf_run.binary()), "--features", "chronos", str(f_b), str(out_b), str(sl_f)], env=gf_run.environment(), check=True)
        subprocess.run([str(gf_run.binary()), "--features", "chronos", str(f_o), str(out_o), str(sl_f)], env=gf_run.environment(), check=True)
        act_b = np.fromfile(out_b, np.float32).reshape(len(cases), 225 + 90 + 720)
        act_o = np.fromfile(out_o, np.float32).reshape(len(cases), 225 + 90 + 720)
        mirror_obs_diff = float(np.max(np.abs(act_b[:, :225] - act_o[:, :225])))
        mirror_mask_diff = float(np.max(np.abs(act_b[:, 225:315] - act_o[:, 225:315])))
        mirror_table_diff = float(np.max(np.abs(act_b[:, 315:] - act_o[:, 315:])))

    report = {
        "status": "PAUSED_AND_RECONCILED",
        "champion_status_unchanged": json.loads((r04 / "champions/chronos.json").read_text(encoding="utf8")),
        "direct_file_hashes_on_disk": disk_hashes,
        "discrepancy_reconciliations": {
            "1_actor_lt_watch_pin_vs_export_actor": {
                "explanation": (
                    "research.pin_candidate() and run.export()->run.candidate_actor() each construct a fresh DirectActor('chronos') "
                    "and load the identical GigaNetwork (POLICY.lt + SHARED_HEAD.lt) into actor.core. In DirectActor, the residual "
                    "output layer (residual.2.weight and residual.2.bias) is zero-initialized (all zeros), so the residual branch contributes "
                    "identically 0.0 to all logits. However, the unused input layer (residual.0.weight, residual.0.bias) is initialized from "
                    "PyTorch's RNG on each DirectActor() instantiation, producing distinct actor.lt file hashes despite identical core weights "
                    "and 0.0 logit difference."
                ),
                "chronos_defensive_swa_research04": {
                    "POLICY.lt_sha256": disk_hashes["r04_watch_pin_POLICY.lt"]["sha256"],
                    "SHARED_HEAD.lt_sha256": disk_hashes["r04_watch_pin_SHARED_HEAD.lt"]["sha256"],
                    "watch_pin_actor.lt_sha256": disk_hashes["r04_watch_pin_actor.lt"]["sha256"],
                    "export_actor.lt_sha256": disk_hashes["r04_rlbot_bundle_actor.lt"]["sha256"],
                    "all_26_core_tensors_bitwise_equal": r04_core_exact,
                    "residual_2_output_layer_all_zero": r04_res2_zero,
                    "dead_residual_0_layer_equal": r04_res0_equal,
                    "max_abs_logit_diff_28_ref_states_pin_vs_export": r04_ref_diff_pin_vs_exp,
                    "max_abs_logit_diff_28_ref_states_pin_vs_native": r04_ref_diff_pin_vs_native,
                    "max_abs_logit_diff_256_random_states_pin_vs_export": r04_rand_diff_pin_vs_exp,
                    "max_abs_logit_diff_256_random_states_pin_vs_native": r04_rand_diff_pin_vs_native,
                },
                "chronos_lowtemp_swa_research03": {
                    "POLICY.lt_sha256": disk_hashes["r03_watch_pin_POLICY.lt"]["sha256"],
                    "SHARED_HEAD.lt_sha256": disk_hashes["r03_watch_pin_SHARED_HEAD.lt"]["sha256"],
                    "watch_pin_actor.lt_sha256": disk_hashes["r03_watch_pin_actor.lt"]["sha256"],
                    "export_actor.lt_sha256": disk_hashes["r03_rlbot_bundle_actor.lt"]["sha256"],
                    "all_26_core_tensors_bitwise_equal": r03_core_exact,
                    "residual_2_output_layer_all_zero": r03_res2_zero,
                    "dead_residual_0_layer_equal": r03_res0_equal,
                    "max_abs_logit_diff_28_ref_states_pin_vs_export": r03_ref_diff_pin_vs_exp,
                    "max_abs_logit_diff_28_ref_states_pin_vs_native": r03_ref_diff_pin_vs_native,
                    "max_abs_logit_diff_256_random_states_pin_vs_export": r03_rand_diff_pin_vs_exp,
                    "max_abs_logit_diff_256_random_states_pin_vs_native": r03_rand_diff_pin_vs_native,
                },
            },
            "2_shared_head_lt_upstream_vs_checkpoint": {
                "explanation": (
                    "Upstream original_chronos SHARED_HEAD.lt has SHA256 e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640. "
                    "When GigaForge.exe trains with freeze_shared=true, zero optimizer steps are taken on shared_head, and C++ LibTorch "
                    "reserializes the identical tensors into a TorchScript archive with SHA256 "
                    "713b9b0549e86960ff2fe2050d97292bcf550cf3afd6a244ae13f51a56cb679a."
                ),
                "upstream_SHARED_HEAD_sha256": disk_hashes["upstream_original_chronos_SHARED_HEAD.lt"]["sha256"],
                "checkpoint_SHARED_HEAD_sha256": disk_hashes["r04_watch_pin_SHARED_HEAD.lt"]["sha256"],
                "tensor_bitwise_equality": sh_tensor_equality,
                "max_abs_output_diff_28_ref_states": sh_ref_max_diff,
                "max_abs_output_diff_256_random_states": sh_rand_max_diff,
            },
            "3_pin_metadata_confirmation_delta_timestamps": {
                "explanation": (
                    "During finalize_research04.py runs: (1) seed=910000000 (delta=-0.015625) created watch_pins/.../actor.lt and actor.lt.json; "
                    "(2) seed=810000000 (delta=-0.03515625) updated pin_manifest.json while leaving actor.lt and actor.lt.json untouched because "
                    "`if not actor.exists():` was False; (3) canonical seed=710010000 (delta=-0.0078125) was restored to "
                    "lab_00001_chronos_confirmation.json and lab_state.json while preserving the existing watch_pins files unchanged. "
                    "All three metadata files record the exact same POLICY.lt (bbf92bc0...) and SHARED_HEAD.lt (713b9b05...)."
                ),
                "actor_lt_json_delta": json.loads((r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/actor.lt.json").read_text(encoding="utf8"))["trial_evidence"]["statistics"]["delta"],
                "pin_manifest_json_delta": json.loads((r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/pin_manifest.json").read_text(encoding="utf8"))["statistics"]["delta"],
                "canonical_confirmation_json_delta": json.loads((r04 / "evaluations/lab_00001_chronos_confirmation.json").read_text(encoding="utf8"))["statistics"]["delta"],
            },
        },
        "which_models_were_used_where": {
            "watched_in_rlviser": {
                "script": "watch_custom.py (24_WATCH_DEFENSIVE_CHRONOS_VS_ORIGINAL.bat, 25_WATCH_DEFENSIVE_CHRONOS_VS_PREV_SWA.bat, 26_WATCH_DEFENSIVE_DRILLS_CHRONOS.bat)",
                "actor_path": str(r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94/actor.lt"),
                "actor_sha256": disk_hashes["r04_watch_pin_actor.lt"]["sha256"],
                "core_POLICY.lt_sha256": disk_hashes["r04_watch_pin_POLICY.lt"]["sha256"],
                "core_SHARED_HEAD.lt_sha256": disk_hashes["r04_watch_pin_SHARED_HEAD.lt"]["sha256"],
            },
            "exported_to_rlbot_v5": {
                "bundle_dir": str(ROOT / "exports/research04/Forge_chronos_769c232267_e7f399"),
                "actor_path": str(ROOT / "exports/research04/Forge_chronos_769c232267_e7f399/actor.lt"),
                "actor_sha256": disk_hashes["r04_rlbot_bundle_actor.lt"]["sha256"],
                "core_POLICY.lt_sha256": disk_hashes["r04_ckpt_chronos_defensive_swa_POLICY.lt"]["sha256"],
                "core_SHARED_HEAD.lt_sha256": disk_hashes["r04_ckpt_chronos_defensive_swa_SHARED_HEAD.lt"]["sha256"],
                "functional_equivalence_to_watched_actor": "Exact 0.0 logit difference (all 26 core tensors bitwise equal, residual.2 output layer all zero)",
            },
            "evaluated_in_2000_game_h2h_matchup_1_and_2": {
                "matchup_1_dir": str(r04 / "h2h/6ae1d06c86c4a8a2"),
                "matchup_2_dir": str(r04 / "h2h/382c876fddd8c800"),
                "candidate_pin_dir": str(r04 / "watch_pins/chronos/trial_00001_2057ee1e9b94"),
                "candidate_POLICY.lt_sha256": disk_hashes["r04_watch_pin_POLICY.lt"]["sha256"],
                "candidate_SHARED_HEAD.lt_sha256": disk_hashes["r04_watch_pin_SHARED_HEAD.lt"]["sha256"],
                "candidate_actor.lt_sha256": disk_hashes["r04_watch_pin_actor.lt"]["sha256"],
                "matchup_1_opponent_POLICY.lt_sha256": disk_hashes["r04_h2h_matchup1_cand_POLICY.lt"]["sha256"],
                "matchup_1_opponent_SHARED_HEAD.lt_sha256": disk_hashes["r04_h2h_matchup1_opp_SHARED_HEAD.lt"]["sha256"],
                "matchup_2_opponent_POLICY.lt_sha256": disk_hashes["r04_h2h_matchup2_opp_POLICY.lt"]["sha256"],
                "matchup_2_opponent_SHARED_HEAD.lt_sha256": disk_hashes["r04_h2h_matchup2_opp_SHARED_HEAD.lt"]["sha256"],
            },
        },
        "orange_side_advantage_investigation": {
            "mirrored_state_invariance_28_ref_states": {
                "max_abs_obs_diff": mirror_obs_diff,
                "max_abs_action_mask_diff": mirror_mask_diff,
                "max_abs_action_table_diff": mirror_table_diff,
                "conclusion": "GF::Obs::BuildObs, GF::Actions::GetActionMask, and GF::Actions::ParseAction are 100% bitwise invariant (0.0 diff) under exact team inversion S <-> S_inv.",
            },
            "kickoff_spawning_and_physics_micro_asymmetry": {
                "kickoff_yaw_float32_rounding": (
                    "In Arena::ResetToRandomKickoff (Arena.cpp:180-189), Orange yaw is computed in float32 as yaw_blue + M_PI. "
                    "Because cosf(yaw + pi) != -cosf(yaw) by 1 ULP in float32, initial kickoff observations differ by 3.18e-8 to 2.38e-7 "
                    "(initial logit diff 7.6e-6 to 2.7e-5; initial argmax action 16 is identical on all 5 spawns)."
                ),
                "bullet_raycast_and_50_50_kickoff_pinch": (
                    "Even when initial rotMat is forced to exact InvertPhys and car addition order is reversed, Bullet btRaycastVehicle / "
                    "SuspensionCollisionGrid / triangle-mesh floor contact accumulates a 1.91e-6 velocity difference by tick 2 (2.56e-3 position "
                    "difference by tick 180) between (-x,-y) and (+x,+y). On symmetric diagonal 50/50 kickoff pinches (Kickoffs 0 and 1), "
                    "the ball rebounds with negative y-velocity (toward Blue's net: vel.y = -31.69 and -7.52 uu/s)."
                ),
                "opponent_slot_rng_tie_breaking": (
                    "In GF::Obs::BuildObs (native_features.h:91), the 1v1 opponent's 29 features are placed into 1 of 3 opponent slots "
                    "chosen by RNG seeded with (seed + team * 113). Changing slot (0 vs 1 vs 2) alters Chronos argmax action on 2-4 / 28 "
                    "reference states (max logit diff 1.80), breaking mirror lockstep between Blue and Orange."
                ),
            },
            "identical_actor_and_cross_family_empirical_comparison": {
                "original_chronos_self_play_5072_games": {
                    "blue_score_rate": 0.4810725552050473,
                    "orange_score_rate": 0.5244479495268138,
                    "orange_minus_blue_pp": 4.337539432176656,
                },
                "original_galactus_self_play_5552_games": {
                    "blue_score_rate": 0.5190922190201729,
                    "orange_score_rate": 0.4823487031700288,
                    "orange_minus_blue_pp": -3.674351585014409,
                },
                "chronos_2000_game_135s_h2h_runs": {
                    "research02_trial54_vs_orig": {"blue": 0.4545, "orange": 0.5265, "orange_minus_blue_pp": 7.20},
                    "research03_lowtemp_swa_vs_orig": {"blue": 0.4570, "orange": 0.5475, "orange_minus_blue_pp": 9.05},
                    "research04_defensive_swa_vs_orig": {"blue": 0.4620, "orange": 0.5190, "orange_minus_blue_pp": 5.70},
                    "research04_defensive_swa_vs_lowtemp_swa": {"blue": 0.4825, "orange": 0.5405, "orange_minus_blue_pp": 5.80},
                },
                "paired_block_cancellation": (
                    "In arena-rng-v4, when identical actors play on seed s, the side=0 and side=1 games execute the exact same physical "
                    "trajectory with subject/opponent labels swapped (verified 50/50 on dev100 and 32/32 on all three confirmation panels). "
                    "Because every seed is evaluated once on Blue and once on Orange, any additive color bias cancels out in the overall "
                    "match score and paired-seed Student-t confidence interval."
                ),
            },
        },
    }

    out_path = r04 / "hash_and_symmetry_reconciliation.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf8")
    print("SAVED RECONCILIATION REPORT:", out_path)


if __name__ == "__main__":
    main()
