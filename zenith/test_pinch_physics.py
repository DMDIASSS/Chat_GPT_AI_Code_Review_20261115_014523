import RocketSim as rs
import numpy as np
import math

mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
rs.init(mesh_dir)

arena = rs.Arena(rs.GameMode.SOCCAR)
car = arena.add_car(rs.Team.BLUE)

# Place ball right on the right wall (x = 4096 - 93 = 4003)
ball_state = arena.ball.get_state()
ball_state.pos = rs.Vec(4096 - 93, 0, 350)
ball_state.vel = rs.Vec(0, 200, 100)
arena.ball.set_state(ball_state)

# Place car approaching the wall and ball at high speed
car_state = car.get_state()
car_state.pos = rs.Vec(4096 - 220, -180, 330)
car_state.vel = rs.Vec(1400, 1600, 50)
car.set_state(car_state)

ctrl = rs.CarControls()
ctrl.throttle = 1.0
ctrl.boost = True
ctrl.steer = 1.0
ctrl.jump = True
ctrl.pitch = -1.0
ctrl.roll = 1.0
ctrl.handbrake = True
car.set_controls(ctrl)

max_spd = 0.0
for tick in range(60):
    arena.step(1)
    bs = arena.ball.get_state()
    spd = math.hypot(bs.vel.x, bs.vel.y, bs.vel.z)
    if spd > max_spd:
        max_spd = spd
    if tick % 10 == 0 or spd > 2000:
        print(f"Tick {tick:02d}: Ball Speed = {spd:.1f} uu/s ({spd * 0.036:.1f} km/h) | Pos = ({bs.pos.x:.0f}, {bs.pos.y:.0f}, {bs.pos.z:.0f})")

print(f"\n>> Final Max Ball Velocity: {max_spd:.1f} uu/s ({max_spd * 0.036:.1f} km/h)")

