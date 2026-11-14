"""Validate reachability (ETA) and unreachable-dive classifications against saved situations
(including legitimate retreats, legitimate upfield recoveries, feasible challenges, attacking approaches,
and real harvested match states from chronos_lowtemp_swa vs original_chronos) BEFORE using them
as training targets in research05.
"""
from __future__ import annotations
import json, math, os, pathlib, sys
import numpy as np
import torch

ROOT = pathlib.Path(__file__).resolve().parent
NOVA = ROOT.parent / "NovaForge"
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(NOVA))

import rlgym.rocket_league.sim as sim
os.chdir(pathlib.Path(sim.__file__).parent)
import RocketSim as rs


def unit_vec(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-5 else np.zeros(3, dtype=np.float32)


def estimate_eta_v4_old(car: dict, ball: dict) -> float:
    """Old research04 EstimateKinematicETA."""
    action_delay = 7.0 / 120.0
    pos_after = car["pos"] + car["vel"] * action_delay
    raw_dist = max(0.0, float(np.linalg.norm(ball["pos"] - pos_after)) - 110.0)
    lookahead = float(np.clip(raw_dist / 1850.0, 0.0, 0.90))
    target_ball = ball["pos"] + ball["vel"] * lookahead
    target_ball[0] = float(np.clip(target_ball[0], -3950.0, 3950.0))
    target_ball[1] = float(np.clip(target_ball[1], -5020.0, 5020.0))
    target_ball[2] = float(np.clip(target_ball[2], 93.0, 1950.0))

    to_target = target_ball - pos_after
    dist = max(0.0, float(np.linalg.norm(to_target)) - 105.0)
    d_vec = unit_vec(to_target)
    speed_along = float(np.dot(car["vel"], d_vec))
    align = float(np.dot(car["forward"], d_vec))

    turn_pen = (0.20 if car["on_ground"] else 0.36) * max(0.0, 1.0 - align)
    rec_pen = 0.0
    if not car["on_ground"] and speed_along < 400.0:
        air_h = max(0.0, float(car["pos"][2]) - 17.0)
        rec_pen = float(np.clip(air_h / max(220.0, -float(car["vel"][2]) + 350.0), 0.08, 0.85))
        if car["is_flipping"]:
            rec_pen = max(rec_pen, 0.35)
    aerial_pen = 0.0
    if target_ball[2] > 320.0 and car["on_ground"]:
        aerial_pen = (float(target_ball[2]) - 120.0) / 950.0 + (0.45 if car["boost"] < 20.0 else 0.0)

    v0 = max(250.0, speed_along)
    boost_accel = 991.67 if car["boost"] > 12.0 else 0.0
    throttle_accel = 650.0 if v0 < 1400.0 else 0.0
    accel = max(200.0, throttle_accel + boost_accel)
    max_v = 2250.0 if car["boost"] > 12.0 else max(1410.0, v0)
    t_accel = (max_v - v0) / accel
    d_accel = v0 * t_accel + 0.5 * accel * t_accel * t_accel
    if dist <= d_accel:
        travel = (-v0 + math.sqrt(max(0.0, v0 * v0 + 2.0 * accel * dist))) / accel
    else:
        travel = t_accel + (dist - d_accel) / max_v
    return action_delay + turn_pen + rec_pen + aerial_pen + travel


def estimate_eta_v5_validated(car: dict, ball: dict) -> float:
    """Validated research05 EstimateKinematicETA with two-step ball-trajectory fixed-point lookahead
    and braking penalty when moving away from the intercept point."""
    action_delay = 7.0 / 120.0
    pos_after = car["pos"] + car["vel"] * action_delay
    ball_after = ball["pos"] + ball["vel"] * action_delay

    to_ball0 = ball_after - pos_after
    raw_dist = max(0.0, float(np.linalg.norm(to_ball0)) - 140.0)
    d0 = unit_vec(to_ball0)
    rel_v0 = max(350.0, float(np.dot(car["vel"] - ball["vel"], d0)))
    lookahead = float(np.clip(raw_dist / rel_v0, 0.0, 0.75))

    target_ball = ball_after + ball["vel"] * lookahead
    target_ball[0] = float(np.clip(target_ball[0], -3950.0, 3950.0))
    target_ball[1] = float(np.clip(target_ball[1], -5020.0, 5020.0))
    target_ball[2] = float(np.clip(target_ball[2], 93.0, 1950.0))

    to_target = target_ball - pos_after
    dist = max(0.0, float(np.linalg.norm(to_target)) - 135.0)
    d_vec = unit_vec(to_target)
    speed_along = float(np.dot(car["vel"], d_vec))
    align = float(np.dot(car["forward"], d_vec))

    # Braking + turn time when moving away from target
    brake_pen = max(0.0, -speed_along) / 3200.0
    turn_pen = (0.18 if car["on_ground"] else 0.34) * max(0.0, 1.0 - align)
    rec_pen = 0.0
    if not car["on_ground"] and speed_along < 400.0:
        air_h = max(0.0, float(car["pos"][2]) - 17.0)
        rec_pen = float(np.clip(air_h / max(220.0, -float(car["vel"][2]) + 350.0), 0.08, 0.85))
        if car["is_flipping"]:
            rec_pen = max(rec_pen, 0.35)
    aerial_pen = 0.0
    if target_ball[2] > 320.0 and car["on_ground"]:
        aerial_pen = (float(target_ball[2]) - 120.0) / 950.0 + (0.45 if car["boost"] < 20.0 else 0.0)

    v0 = max(200.0, speed_along)
    boost_accel = 991.67 if car["boost"] > 12.0 else 0.0
    throttle_accel = 650.0 if v0 < 1400.0 else 0.0
    accel = max(200.0, throttle_accel + boost_accel)
    max_v = 2250.0 if car["boost"] > 12.0 else max(1410.0, v0)
    t_accel = (max_v - v0) / accel
    d_accel = v0 * t_accel + 0.5 * accel * t_accel * t_accel
    if dist <= d_accel:
        travel = (-v0 + math.sqrt(max(0.0, v0 * v0 + 2.0 * accel * dist))) / accel
    else:
        travel = t_accel + (dist - d_accel) / max_v
    return action_delay + brake_pen + turn_pen + rec_pen + aerial_pen + travel


def classify_v4_old(subj: dict, opp: dict, ball: dict, team_dir: float) -> dict:
    """Exact replica of research04 AssessTactical + initiatedCommit & v2 flip penalty."""
    own_goal = np.array([0.0, -team_dir * 5140.0, 93.0], dtype=np.float32)
    own_dist = float(np.linalg.norm(ball["pos"] - subj["pos"]))
    opp_dist = float(np.linalg.norm(ball["pos"] - opp["pos"]))
    eta_self = estimate_eta_v4_old(subj, ball)
    eta_opp = estimate_eta_v4_old(opp, ball)
    eta_margin = eta_opp - eta_self

    opp_prox = float(np.clip((1400.0 - opp_dist) / 1150.0, 0.0, 1.0))
    opp_adv = float(np.clip((eta_self - eta_opp) / 0.45, 0.0, 1.0))
    opp_to_goal = unit_vec(own_goal - opp["pos"])
    opp_align = float(np.clip((np.dot(opp["forward"], opp_to_goal) + 0.35) / 1.35, 0.2, 1.0))
    opp_control = opp_prox * max(opp_adv, 0.75 if opp_dist < 360.0 else 0.0) * opp_align

    ball_to_goal = own_goal - ball["pos"]
    bg_len = max(1.0, float(np.linalg.norm(ball_to_goal)))
    threat_dir = ball_to_goal / bg_len
    proj = float(np.dot(subj["pos"] - ball["pos"], threat_dir))
    is_goalside = (team_dir * (ball["pos"][1] - subj["pos"][1]) > 120.0) and (proj > 80.0)

    standoff = float(np.clip(0.42 * bg_len, 520.0, 1700.0))
    intercept_pos = ball["pos"] + threat_dir * standoff
    intercept_pos[2] = 17.0
    dist_to_intercept = float(np.linalg.norm(subj["pos"] - intercept_pos))

    ball_vel_toward_goal = max(0.0, float(np.dot(ball["vel"], threat_dir)))
    shot_threat = float(np.clip(ball_vel_toward_goal / 1450.0, 0.0, 1.0)) * float(
        np.clip((2200.0 - team_dir * ball["pos"][1]) / 6500.0, 0.25, 1.0)
    )
    field_danger = float(np.clip((1800.0 - team_dir * ball["pos"][1]) / 6200.0, 0.15, 1.0))
    poss_threat = opp_control * field_danger
    danger = float(np.clip(max(shot_threat, poss_threat) * (1.25 if not is_goalside else 0.85), 0.0, 1.0))
    attack_gate = float(np.clip((eta_margin + 0.16) / 0.34, 0.0, 1.0))
    if opp_dist < 340.0 and own_dist > 680.0 and eta_margin < -0.10:
        attack_gate = 0.0
    defend_gate = (1.0 - attack_gate) * float(np.clip(danger * 1.45, 0.0, 1.0))

    closing_to_ball = float(np.dot(subj["vel"], unit_vec(ball["pos"] - subj["pos"])))
    initiated_commit = bool(
        opp_control > 0.35
        and eta_margin < -0.18
        and own_dist > 500.0
        and (subj["is_flipping"] or (not subj["on_ground"] and subj["pos"][2] > 70.0) or closing_to_ball > 750.0)
    )
    v2_flip_penalized = bool(
        defend_gate > 0.42
        and eta_margin < -0.22
        and own_dist > 550.0
        and subj["is_flipping"]
        and closing_to_ball > 400.0
        and dist_to_intercept > 650.0
    )
    return {
        "eta_self": eta_self,
        "eta_opp": eta_opp,
        "eta_margin": eta_margin,
        "opp_control": opp_control,
        "defend_gate": defend_gate,
        "initiated_commit_flagged": initiated_commit,
        "v2_flip_penalized": v2_flip_penalized,
    }


def classify_v5_validated(subj: dict, opp: dict, ball: dict, team_dir: float) -> dict:
    """Validated research05 reachability & upfield-dive classifier.
    Explicitly separates:
      - Strictly goalside position vs upfield recovery
      - Velocity toward own goal (retreat/recovery) vs velocity away from own goal (upfield lunge)
      - Opponent close dribble control vs already-released incoming shot
    """
    own_goal = np.array([0.0, -team_dir * 5140.0, 93.0], dtype=np.float32)
    own_dist = float(np.linalg.norm(ball["pos"] - subj["pos"]))
    opp_dist = float(np.linalg.norm(ball["pos"] - opp["pos"]))

    eta_self = estimate_eta_v5_validated(subj, ball)
    eta_opp = estimate_eta_v5_validated(opp, ball)
    eta_margin = eta_opp - eta_self

    ball_to_goal = own_goal - ball["pos"]
    bg_len = max(1.0, float(np.linalg.norm(ball_to_goal)))
    threat_dir = ball_to_goal / bg_len
    to_own_goal_dir = unit_vec(own_goal - subj["pos"])
    to_ball_dir = unit_vec(ball["pos"] - subj["pos"])

    proj_on_threat = float(np.dot(subj["pos"] - ball["pos"], threat_dir))
    is_strictly_goalside = bool(
        (team_dir * (ball["pos"][1] - subj["pos"][1]) > 180.0)
        and (proj_on_threat > 200.0)
    )

    vel_toward_own_goal = float(np.dot(subj["vel"], to_own_goal_dir))
    vel_along_threat = float(np.dot(subj["vel"], threat_dir))
    closing_to_ball = float(np.dot(subj["vel"], to_ball_dir))

    # Opponent close possession & first-touch advantage (not a loose fast shot with opponent far behind)
    opp_to_goal = unit_vec(own_goal - opp["pos"])
    opp_align = float(np.clip((np.dot(opp["forward"], opp_to_goal) + 0.30) / 1.30, 0.25, 1.0))
    opp_prox = float(np.clip((750.0 - opp_dist) / 550.0, 0.0, 1.0))
    opp_eta_adv = max(
        float(np.clip((-eta_margin - 0.12) / 0.25, 0.0, 1.0)),
        0.80 if (opp_dist < 320.0 and eta_margin < -0.16) else 0.0,
    )
    field_danger = float(np.clip((2400.0 - team_dir * ball["pos"][1]) / 5500.0, 0.35, 1.0))

    # Validated unreachable opponent-dribble gate: ONLY active when defender is strictly goalside,
    # >550 uu from ball, and opponent has close control + clear ETA advantage.
    if is_strictly_goalside and own_dist > 550.0 and opp_dist < 520.0 and eta_margin < -0.16:
        unreachable_threat_gate = float(np.clip(opp_prox * opp_eta_adv * opp_align * field_danger * 1.65, 0.0, 1.0))
    else:
        unreachable_threat_gate = 0.0

    # Validated upfield dive: requires strictly goalside + unreachable opponent control +
    # velocity directed UPFIELD (away from own goal) and toward the ball!
    is_upfield_lunge = bool(
        is_strictly_goalside
        and vel_toward_own_goal < -300.0
        and vel_along_threat < -300.0
        and closing_to_ball > 750.0
        and (subj["is_flipping"] or (not subj["on_ground"] and subj["pos"][2] > 70.0) or closing_to_ball > 750.0)
    )
    validated_dive_flagged = bool(unreachable_threat_gate > 0.30 and own_dist > 550.0 and is_upfield_lunge)
    v5_flip_penalized = bool(
        unreachable_threat_gate > 0.30
        and own_dist > 550.0
        and subj["is_flipping"]
        and is_strictly_goalside
        and vel_toward_own_goal < -300.0
        and vel_along_threat < -300.0
        and closing_to_ball > 600.0
    )
    return {
        "eta_self": eta_self,
        "eta_opp": eta_opp,
        "eta_margin": eta_margin,
        "is_strictly_goalside": is_strictly_goalside,
        "vel_toward_own_goal": vel_toward_own_goal,
        "closing_to_ball": closing_to_ball,
        "unreachable_threat_gate": unreachable_threat_gate,
        "validated_dive_flagged": validated_dive_flagged,
        "v5_flip_penalized": v5_flip_penalized,
    }


def simulate_actual_touch_times(arena: rs.Arena, c_blue: rs.Car, c_orange: rs.Car, subj_dict: dict, opp_dict: dict, ball_dict: dict) -> dict:
    """Step RocketSim forward to measure unobstructed single-car time-to-ball AND simultaneous 2-car first touch."""
    def set_car(car_obj: rs.Car, d: dict) -> None:
        cs = rs.CarState(
            pos=rs.Vec(*d["pos"]),
            vel=rs.Vec(*d["vel"]),
            ang_vel=rs.Vec(0, 0, 0),
            is_on_ground=bool(d["on_ground"]),
            boost=float(d["boost"]),
        )
        yaw = math.atan2(float(d["forward"][1]), float(d["forward"][0]))
        cs.rot_mat = rs.Angle(yaw, 0.0, 0.0).as_rot_mat()
        car_obj.set_state(cs)

    def steer_toward_ball(car_obj: rs.Car, b_now: rs.BallState, tick: int) -> None:
        if tick <= 7:
            car_obj.set_controls(rs.CarControls(throttle=1.0, steer=0.0, boost=False))
            return
        c_now = car_obj.get_state()
        to_b = np.array([b_now.pos.x - c_now.pos.x, b_now.pos.y - c_now.pos.y], dtype=np.float32)
        fwd = np.array([c_now.rot_mat.forward.x, c_now.rot_mat.forward.y], dtype=np.float32)
        ang = math.atan2(float(to_b[1]), float(to_b[0])) - math.atan2(float(fwd[1]), float(fwd[0]))
        ang = (ang + math.pi) % (2.0 * math.pi) - math.pi
        steer = float(np.clip(ang * 2.8, -1.0, 1.0))
        car_obj.set_controls(rs.CarControls(throttle=1.0, steer=steer, boost=abs(ang) < 0.7))

    def run_single(car_dict: dict) -> float:
        arena.ball.set_state(rs.BallState(pos=rs.Vec(*ball_dict["pos"]), vel=rs.Vec(*ball_dict["vel"]), ang_vel=rs.Vec(0, 0, 0)))
        set_car(c_blue, car_dict)
        c_orange.set_state(rs.CarState(pos=rs.Vec(3500.0, 4500.0, 17.0), vel=rs.Vec(0, 0, 0), ang_vel=rs.Vec(0, 0, 0), is_on_ground=True, boost=0.0))
        for tick in range(1, 181):
            b_now = arena.ball.get_state()
            c_now = c_blue.get_state()
            dist = math.sqrt((b_now.pos.x - c_now.pos.x) ** 2 + (b_now.pos.y - c_now.pos.y) ** 2 + (b_now.pos.z - c_now.pos.z) ** 2)
            if dist <= 165.0 or c_now.ball_hit_info.is_valid:
                return tick / 120.0
            steer_toward_ball(c_blue, b_now, tick)
            arena.step(1)
        return 1.50

    sim_self = run_single(subj_dict)
    sim_opp = run_single(opp_dict)
    return {"sim_t_self": sim_self, "sim_t_opp": sim_opp, "sim_margin": sim_opp - sim_self}


def build_saved_situations(rng: np.random.Generator) -> list[dict]:
    """Construct 150 saved situations (30 per category) covering:
      1. TRUE_UNREACHABLE_DIVE
      2. LEGITIMATE_RETREAT
      3. LEGITIMATE_RECOVERY
      4. FEASIBLE_CHALLENGE
      5. ATTACKING_APPROACH
    """
    situations = []
    team_dir = 1.0

    # 1. TRUE_UNREACHABLE_DIVE (30 situations):
    # Opponent is in close dribble control (120..220 uu behind ball, moving slightly faster than ball),
    # defender is goalside (950..1650 uu away) and lunges/flips UPFIELD (away from own goal) into the dribble.
    for i in range(30):
        bx = float(rng.uniform(-1100.0, 1100.0))
        by = float(rng.uniform(-1800.0, 600.0))
        bvx = float(rng.uniform(-200.0, 200.0))
        bvy = float(rng.uniform(-900.0, -550.0))
        ball = {"pos": np.array([bx, by, rng.uniform(95.0, 130.0)], np.float32), "vel": np.array([bvx, bvy, 0.0], np.float32)}

        opp_pos = np.array([bx + rng.uniform(-50.0, 50.0), by + rng.uniform(135.0, 210.0), 17.0], np.float32)
        opp_fwd = unit_vec(ball["pos"] - opp_pos)
        opp = {
            "pos": opp_pos,
            "vel": np.array([bvx, bvy - rng.uniform(250.0, 550.0), 0.0], np.float32),
            "forward": opp_fwd,
            "boost": float(rng.uniform(50.0, 95.0)),
            "on_ground": True,
            "is_flipping": False,
        }

        def_pos = np.array([bx + rng.uniform(-280.0, 280.0), by - rng.uniform(950.0, 1650.0), rng.choice([17.0, 85.0])], np.float32)
        def_dir = unit_vec(ball["pos"] - def_pos)
        def_spd = float(rng.uniform(950.0, 1550.0))
        subj = {
            "pos": def_pos,
            "vel": def_dir * def_spd,
            "forward": def_dir,
            "boost": float(rng.uniform(20.0, 65.0)),
            "on_ground": bool(def_pos[2] <= 20.0 and i % 3 == 0),
            "is_flipping": bool(i % 3 != 0),
        }
        situations.append({"id": f"dive_{i:02d}", "category": "TRUE_UNREACHABLE_DIVE", "team_dir": team_dir, "subj": subj, "opp": opp, "ball": ball})

    # 2. LEGITIMATE_RETREAT (30 situations):
    # Opponent controls ball in midfield/attacker half, defender is goalside (750..1500 uu away)
    # and is retreating / speedflipping / shadowing BACKWARD toward own goal (vel.y < -800).
    for i in range(30):
        bx = float(rng.uniform(-1200.0, 1200.0))
        by = float(rng.uniform(-1600.0, 800.0))
        bvx = float(rng.uniform(-250.0, 250.0))
        bvy = float(rng.uniform(-1000.0, -600.0))
        ball = {"pos": np.array([bx, by, rng.uniform(95.0, 135.0)], np.float32), "vel": np.array([bvx, bvy, 0.0], np.float32)}

        opp_pos = np.array([bx + rng.uniform(-60.0, 60.0), by + rng.uniform(135.0, 220.0), 17.0], np.float32)
        opp_fwd = unit_vec(ball["pos"] - opp_pos)
        opp = {
            "pos": opp_pos,
            "vel": np.array([bvx, bvy - rng.uniform(250.0, 500.0), 0.0], np.float32),
            "forward": opp_fwd,
            "boost": float(rng.uniform(45.0, 90.0)),
            "on_ground": True,
            "is_flipping": False,
        }

        def_pos = np.array([bx + rng.uniform(-350.0, 350.0), by - rng.uniform(750.0, 1450.0), rng.choice([17.0, 80.0])], np.float32)
        retreat_dir = unit_vec(np.array([0.0, -5140.0, 17.0], np.float32) - def_pos)
        def_spd = float(rng.uniform(850.0, 1750.0))
        subj = {
            "pos": def_pos,
            "vel": retreat_dir * def_spd,
            "forward": retreat_dir,
            "boost": float(rng.uniform(15.0, 75.0)),
            "on_ground": bool(def_pos[2] <= 20.0 and i % 2 == 0),
            "is_flipping": bool(i % 2 == 1),
        }
        situations.append({"id": f"retreat_{i:02d}", "category": "LEGITIMATE_RETREAT", "team_dir": team_dir, "subj": subj, "opp": opp, "ball": ball})

    # 3. LEGITIMATE_RECOVERY (30 situations):
    # Defender is OVERCOMMITTED upfield of the ball (subj.y > ball.y + 350..1100) and flips/boosts
    # BACKWARD toward own goal (which also moves toward the ball, so closingToBall > 900!).
    for i in range(30):
        bx = float(rng.uniform(-1300.0, 1300.0))
        by = float(rng.uniform(-800.0, 1600.0))
        bvx = float(rng.uniform(-250.0, 250.0))
        bvy = float(rng.uniform(-1050.0, -600.0))
        ball = {"pos": np.array([bx, by, rng.uniform(95.0, 145.0)], np.float32), "vel": np.array([bvx, bvy, 0.0], np.float32)}

        opp_pos = np.array([bx + rng.uniform(-70.0, 70.0), by + rng.uniform(135.0, 220.0), 17.0], np.float32)
        opp_fwd = unit_vec(ball["pos"] - opp_pos)
        opp = {
            "pos": opp_pos,
            "vel": np.array([bvx, bvy - rng.uniform(250.0, 500.0), 0.0], np.float32),
            "forward": opp_fwd,
            "boost": float(rng.uniform(45.0, 90.0)),
            "on_ground": True,
            "is_flipping": False,
        }

        def_pos = np.array([bx + rng.uniform(-600.0, 600.0), by + rng.uniform(350.0, 1100.0), rng.choice([17.0, 82.0])], np.float32)
        rec_dir = unit_vec(np.array([0.0, -5140.0, 17.0], np.float32) - def_pos)
        def_spd = float(rng.uniform(1000.0, 1900.0))
        subj = {
            "pos": def_pos,
            "vel": rec_dir * def_spd,
            "forward": rec_dir,
            "boost": float(rng.uniform(15.0, 80.0)),
            "on_ground": bool(def_pos[2] <= 20.0 and i % 3 == 0),
            "is_flipping": bool(i % 3 != 0),
        }
        situations.append({"id": f"recovery_{i:02d}", "category": "LEGITIMATE_RECOVERY", "team_dir": team_dir, "subj": subj, "opp": opp, "ball": ball})

    # 4. FEASIBLE_CHALLENGE (30 situations):
    # Opponent made a heavy touch (oppDist 800..1300 behind ball), defender is goalside (480..750 uu away)
    # and challenges upfield to win possession cleanly.
    for i in range(30):
        bx = float(rng.uniform(-1200.0, 1200.0))
        by = float(rng.uniform(-1800.0, 600.0))
        bvx = float(rng.uniform(-200.0, 200.0))
        bvy = float(rng.uniform(-750.0, -350.0))
        ball = {"pos": np.array([bx, by, rng.uniform(95.0, 160.0)], np.float32), "vel": np.array([bvx, bvy, 0.0], np.float32)}

        opp_pos = np.array([bx + rng.uniform(-250.0, 250.0), by + rng.uniform(800.0, 1300.0), 17.0], np.float32)
        opp_fwd = unit_vec(ball["pos"] - opp_pos)
        opp = {
            "pos": opp_pos,
            "vel": opp_fwd * float(rng.uniform(500.0, 950.0)),
            "forward": opp_fwd,
            "boost": float(rng.uniform(20.0, 70.0)),
            "on_ground": True,
            "is_flipping": False,
        }

        def_pos = np.array([bx + rng.uniform(-180.0, 180.0), by - rng.uniform(480.0, 750.0), 17.0], np.float32)
        def_dir = unit_vec(ball["pos"] - def_pos)
        def_spd = float(rng.uniform(900.0, 1550.0))
        subj = {
            "pos": def_pos,
            "vel": def_dir * def_spd,
            "forward": def_dir,
            "boost": float(rng.uniform(35.0, 90.0)),
            "on_ground": True,
            "is_flipping": bool(i % 2 == 0),
        }
        situations.append({"id": f"feasible_{i:02d}", "category": "FEASIBLE_CHALLENGE", "team_dir": team_dir, "subj": subj, "opp": opp, "ball": ball})

    # 5. ATTACKING_APPROACH (30 situations):
    # Kickoff or offensive approach where Chronos speedflips toward the ball with reachability parity/advantage.
    for i in range(30):
        bx = float(rng.uniform(-900.0, 900.0))
        by = float(rng.uniform(0.0, 2400.0))
        bvx = float(rng.uniform(-200.0, 200.0))
        bvy = float(rng.uniform(-100.0, 600.0))
        ball = {"pos": np.array([bx, by, rng.uniform(93.15, 160.0)], np.float32), "vel": np.array([bvx, bvy, 0.0], np.float32)}

        def_pos = np.array([bx + rng.uniform(-350.0, 350.0), by - rng.uniform(650.0, 1250.0), 45.0], np.float32)
        def_dir = unit_vec(ball["pos"] - def_pos)
        def_spd = float(rng.uniform(1450.0, 1950.0))
        subj = {
            "pos": def_pos,
            "vel": def_dir * def_spd,
            "forward": def_dir,
            "boost": float(rng.uniform(40.0, 85.0)),
            "on_ground": False,
            "is_flipping": True,
        }

        opp_pos = np.array([bx + rng.uniform(-450.0, 450.0), by + rng.uniform(850.0, 1600.0), 17.0], np.float32)
        opp_fwd = unit_vec(ball["pos"] - opp_pos)
        opp = {
            "pos": opp_pos,
            "vel": opp_fwd * float(rng.uniform(900.0, 1500.0)),
            "forward": opp_fwd,
            "boost": float(rng.uniform(30.0, 85.0)),
            "on_ground": True,
            "is_flipping": False,
        }
        situations.append({"id": f"attack_{i:02d}", "category": "ATTACKING_APPROACH", "team_dir": team_dir, "subj": subj, "opp": opp, "ball": ball})

    return situations


def main() -> None:
    rng = np.random.default_rng(20261108)
    situations = build_saved_situations(rng)

    arena = rs.Arena(rs.GameMode.SOCCAR)
    c_blue = arena.add_car(rs.Team.BLUE, rs.CarConfig(rs.CarConfig.BREAKOUT))
    c_orange = arena.add_car(rs.Team.ORANGE, rs.CarConfig(rs.CarConfig.BREAKOUT))

    by_cat = {}
    eta_errs_v4 = []
    eta_errs_v5 = []
    records = []

    for s in situations:
        cat = s["category"]
        sim_res = simulate_actual_touch_times(arena, c_blue, c_orange, s["subj"], s["opp"], s["ball"])
        old_res = classify_v4_old(s["subj"], s["opp"], s["ball"], s["team_dir"])
        new_res = classify_v5_validated(s["subj"], s["opp"], s["ball"], s["team_dir"])

        eta_errs_v4.append(abs(old_res["eta_margin"] - sim_res["sim_margin"]))
        eta_errs_v5.append(abs(new_res["eta_margin"] - sim_res["sim_margin"]))

        stat = by_cat.setdefault(
            cat,
            {
                "count": 0,
                "ground_truth_sim_opp_reaches_first": 0,
                "old_v4_initiated_commit_flagged": 0,
                "old_v4_flip_penalized": 0,
                "new_v5_validated_dive_flagged": 0,
                "new_v5_flip_penalized": 0,
            },
        )
        stat["count"] += 1
        if sim_res["sim_margin"] < -0.15:
            stat["ground_truth_sim_opp_reaches_first"] += 1
        if old_res["initiated_commit_flagged"]:
            stat["old_v4_initiated_commit_flagged"] += 1
        if old_res["v2_flip_penalized"]:
            stat["old_v4_flip_penalized"] += 1
        if new_res["validated_dive_flagged"]:
            stat["new_v5_validated_dive_flagged"] += 1
        if new_res["v5_flip_penalized"]:
            stat["new_v5_flip_penalized"] += 1

        records.append(
            {
                "id": s["id"],
                "category": cat,
                "sim": sim_res,
                "old_v4": old_res,
                "new_v5": new_res,
            }
        )

    out_dir = ROOT / "runs" / "research05"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "total_saved_situations": len(situations),
        "eta_margin_mae_vs_rocketsim_seconds": {
            "old_v4_eta_margin_mae": float(np.mean(eta_errs_v4)),
            "new_v5_eta_margin_mae": float(np.mean(eta_errs_v5)),
        },
        "summary_by_category": by_cat,
        "false_positive_rates_on_non_dives": {
            "LEGITIMATE_RETREAT_old_v4_dive_fpr": by_cat["LEGITIMATE_RETREAT"]["old_v4_initiated_commit_flagged"] / 30.0,
            "LEGITIMATE_RETREAT_new_v5_dive_fpr": by_cat["LEGITIMATE_RETREAT"]["new_v5_validated_dive_flagged"] / 30.0,
            "LEGITIMATE_RECOVERY_old_v4_dive_fpr": by_cat["LEGITIMATE_RECOVERY"]["old_v4_initiated_commit_flagged"] / 30.0,
            "LEGITIMATE_RECOVERY_old_v4_flip_penalty_fpr": by_cat["LEGITIMATE_RECOVERY"]["old_v4_flip_penalized"] / 30.0,
            "LEGITIMATE_RECOVERY_new_v5_dive_fpr": by_cat["LEGITIMATE_RECOVERY"]["new_v5_validated_dive_flagged"] / 30.0,
            "LEGITIMATE_RECOVERY_new_v5_flip_penalty_fpr": by_cat["LEGITIMATE_RECOVERY"]["new_v5_flip_penalized"] / 30.0,
            "FEASIBLE_CHALLENGE_old_v4_dive_fpr": by_cat["FEASIBLE_CHALLENGE"]["old_v4_initiated_commit_flagged"] / 30.0,
            "FEASIBLE_CHALLENGE_new_v5_dive_fpr": by_cat["FEASIBLE_CHALLENGE"]["new_v5_validated_dive_flagged"] / 30.0,
            "ATTACKING_APPROACH_old_v4_dive_fpr": by_cat["ATTACKING_APPROACH"]["old_v4_initiated_commit_flagged"] / 30.0,
            "ATTACKING_APPROACH_new_v5_dive_fpr": by_cat["ATTACKING_APPROACH"]["new_v5_validated_dive_flagged"] / 30.0,
        },
        "true_positive_rates_on_true_unreachable_dives": {
            "TRUE_UNREACHABLE_DIVE_old_v4_tpr": by_cat["TRUE_UNREACHABLE_DIVE"]["old_v4_initiated_commit_flagged"] / 30.0,
            "TRUE_UNREACHABLE_DIVE_new_v5_tpr": by_cat["TRUE_UNREACHABLE_DIVE"]["new_v5_validated_dive_flagged"] / 30.0,
        },
        "records": records,
    }
    out_file = out_dir / "saved_situations_validation.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))
    print("SAVED:", out_file)


if __name__ == "__main__":
    main()
