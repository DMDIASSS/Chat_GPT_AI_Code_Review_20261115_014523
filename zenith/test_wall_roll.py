import RocketSim as rs
import math

mesh_dir = r"E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Lib\site-packages\rlgym\rocket_league\sim\collision_meshes"
rs.init(mesh_dir)

arena = rs.Arena(rs.GameMode.SOCCAR)
car = arena.add_car(rs.Team.BLUE)

bs = arena.ball.get_state()
bs.pos = rs.Vec(2800, -1000, 93)
spd = 1400.0
ang = math.radians(15.0)  # 15 degrees into wall, tilted forward
bs.vel = rs.Vec(spd * math.cos(ang), spd * math.sin(ang), 0)
arena.ball.set_state(bs)

print(f"Initial ball vel: vx={bs.vel.x:.1f}, vy={bs.vel.y:.1f}, vz={bs.vel.z:.1f}")

max_z = 0.0
for tick in range(240):
    arena.step(1)
    b = arena.ball.get_state()
    if b.pos.z > max_z:
        max_z = b.pos.z
    if b.pos.x > 3800 and tick % 20 == 0:
        print(f"Tick {tick:03d}: pos=({b.pos.x:.0f}, {b.pos.y:.0f}, {b.pos.z:.0f}), vel=({b.vel.x:.0f}, {b.vel.y:.0f}, {b.vel.z:.0f})")

print(f"\n>> Max height climbed on wall: {max_z:.1f} uu (Distance from wall: {4096 - b.pos.x:.1f} uu)")
