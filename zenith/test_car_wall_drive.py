import RocketSim as rs
import numpy as np
import math

mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
rs.init(mesh_dir)

arena = rs.Arena(rs.GameMode.SOCCAR)
car = arena.add_car(rs.Team.BLUE)

# Place car firmly on the right side wall (x = 4096 - 17.5 = 4078.5)
side = 1.0
cs = car.get_state()
cs.pos = rs.Vec(4096.0 - 18.0, 0.0, 300.0)

# Local basis on wall: forward pointing up/forward, up pointing away from wall (towards midfield)
# Forward: (0, 0.5, 0.866), Up: (-1, 0, 0), Right: (0, -0.866, 0.5)
# In RocketSim, rot_mat columns are forward, right, up
fwd = np.array([0.0, 0.4, 0.9165])
fwd = fwd / np.linalg.norm(fwd)
up_vec = np.array([-side, 0.0, 0.0])
right_vec = np.cross(up_vec, fwd)
right_vec = right_vec / np.linalg.norm(right_vec)
up_final = np.cross(fwd, right_vec)

rot_cols = np.column_stack((fwd, right_vec, up_final))
# RotMat takes row-major or 9 elements
cs.rot_mat = rs.RotMat(*rot_cols.transpose().flatten())
cs.vel = rs.Vec(0.0, 500.0, 1100.0)
cs.is_on_ground = True
car.set_state(cs)

# Step with throttle = 1.0, boost = 1.0 (driving up the wall)
ctrl = rs.CarControls()
ctrl.throttle = 1.0
ctrl.boost = True
car.set_controls(ctrl)

print("--- Testing car driving on wall surface ---")
for tick in range(60):
    arena.step(1)
    c = car.get_state()
    if tick % 10 == 0:
        print(f"Tick {tick:02d} | Pos: ({c.pos.x:.1f}, {c.pos.y:.1f}, {c.pos.z:.1f}) | Vel: ({c.vel.x:.1f}, {c.vel.y:.1f}, {c.vel.z:.1f}) | OnGround: {c.is_on_ground}")
