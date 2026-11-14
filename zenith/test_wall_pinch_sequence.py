import RocketSim as rs
import numpy as np

mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
rs.init(mesh_dir)

arena = rs.Arena(rs.GameMode.SOCCAR)
car = arena.add_car(rs.Team.BLUE)

# Place car on right wall
side = 1.0
cs = car.get_state()
cs.pos = rs.Vec(4096.0 - 18.0, 0.0, 300.0)

fwd = np.array([0.0, 0.4, 0.9165])
fwd = fwd / np.linalg.norm(fwd)
up_vec = np.array([-side, 0.0, 0.0])
right_vec = np.cross(up_vec, fwd)
right_vec = right_vec / np.linalg.norm(right_vec)
up_final = np.cross(fwd, right_vec)

rot_cols = np.column_stack((fwd, right_vec, up_final))
cs.rot_mat = rs.RotMat(*rot_cols.transpose().flatten())
cs.vel = rs.Vec(0.0, 500.0, 1100.0)
cs.is_on_ground = True
car.set_state(cs)

# Also place the ball slightly higher on the wall: z = 450, x = 4096 - 93 = 4003
bs = arena.ball.get_state()
bs.pos = rs.Vec(4096.0 - 93.0, 50.0, 450.0)
bs.vel = rs.Vec(0.0, 450.0, 900.0)
arena.ball.set_state(bs)

print("--- Testing wall jump & pinch ---")
for tick in range(40):
    ctrl = rs.CarControls()
    ctrl.throttle = 1.0
    ctrl.boost = True
    if tick == 5:
        # Jump off wall
        ctrl.jump = True
    elif tick == 12:
        # Dodge/flip towards wall (+x)
        ctrl.jump = True
        ctrl.roll = 1.0
        ctrl.pitch = -1.0
    car.set_controls(ctrl)
    
    arena.step(1)
    c = car.get_state()
    b = arena.ball.get_state()
    b_spd = np.linalg.norm([b.vel.x, b.vel.y, b.vel.z])
    if tick % 5 == 0 or b_spd > 2000:
        print(f"Tick {tick:02d} | Car: ({c.pos.x:.0f}, {c.pos.y:.0f}, {c.pos.z:.0f}) | Ball: ({b.pos.x:.0f}, {b.pos.y:.0f}, {b.pos.z:.0f}), Speed: {b_spd:.1f} uu/s ({b_spd*0.036:.1f} km/h)")
