"""Action space definition and lookup table for GEMINI_BOT.

Uses the exact 90-action discrete table shared by Nexto, Chronos, Galactus, and GigaLearn.
Guarantees identical action indexing across training and inference.
"""
import numpy as np

# 90-action lookup table:
# Ground actions (0..23): throttle (-1,0,1), steer (-1,0,1), boost (0,1), handbrake (0,1)
# Aerial actions (24..89): pitch, yaw, roll, jump, boost
def make_lookup_table() -> np.ndarray:
    actions = []
    # Ground actions (24 total)
    for throttle in (-1, 0, 1):
        for steer in (-1, 0, 1):
            for boost in (0, 1):
                for handbrake in (0, 1):
                    if boost == 1 and throttle != 1:
                        continue
                    actions.append([throttle or boost, steer, 0.0, steer, 0.0, 0.0, boost, handbrake])

    # Aerial actions (66 total)
    for pitch in (-1, 0, 1):
        for yaw in (-1, 0, 1):
            for roll in (-1, 0, 1):
                for jump in (0, 1):
                    for boost in (0, 1):
                        if jump == 1 and yaw != 0:  # Roll is used for side-flips
                            continue
                        if pitch == roll == jump == 0:  # Redundant with ground
                            continue
                        # Handbrake enabled with jump for wave-dashes
                        handbrake = jump == 1 and (pitch != 0 or yaw != 0 or roll != 0)
                        actions.append([boost, yaw, pitch, yaw, roll, jump, boost, float(handbrake)])

    return np.array(actions, dtype=np.float32)

TABLE = make_lookup_table()
assert len(TABLE) == 90, f"Expected 90 actions, got {len(TABLE)}"

def native_action_mask(on_ground: bool, has_flip: bool, boost_amount: float) -> np.ndarray:
    """Matches GigaLearn DefaultAction.cpp mask logic exactly.
    
    Prevents impossible inputs:
    - Pitch / roll while grounded
    - Flip inputs when in mid-air with no flip available
    - Boost inputs when out of boost
    """
    ground = np.arange(90) < 24
    jump = TABLE[:, 5] != 0
    air = (np.arange(90) >= 24) & ~jump
    air |= ground & (TABLE[:, 0] == TABLE[:, 6]) & ((TABLE[:, 3] != 0) == (TABLE[:, 7] != 0))
    
    mask = (ground if on_ground else air).copy()
    if boost_amount <= 0.01:
        mask &= (TABLE[:, 6] == 0)
    if on_ground or has_flip:
        mask |= jump
    return mask

def action_to_controller(action_row, controller_cls=None):
    """Converts a row of TABLE to an RLBot SimpleControllerState or dict."""
    throttle, steer, pitch, yaw, roll, jump, boost, handbrake = action_row
    if controller_cls is not None:
        ctrl = controller_cls()
        ctrl.throttle = float(throttle)
        ctrl.steer = float(steer)
        ctrl.pitch = float(pitch)
        ctrl.yaw = float(yaw)
        ctrl.roll = float(roll)
        ctrl.jump = bool(jump)
        ctrl.boost = bool(boost)
        ctrl.handbrake = bool(handbrake)
        return ctrl
    return {
        "throttle": float(throttle),
        "steer": float(steer),
        "pitch": float(pitch),
        "yaw": float(yaw),
        "roll": float(roll),
        "jump": bool(jump),
        "boost": bool(boost),
        "handbrake": bool(handbrake),
    }
