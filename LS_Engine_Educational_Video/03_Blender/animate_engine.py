"""LS V8 kinematics + per-frame scene state.

Shared by build_engine.py (geometry constants), create_scenes.py and render_scenes.py.
Everything that moves frame-by-frame (crank, pistons, rods, valves, cam, injector spray,
combustion, particles, signal pulses, mode colours) is computed here from the frame
number, so any frame can be rendered independently (resume-capable rendering).

Geometry (metres, Z up, +Y = front of engine, crank axis = Y axis):
  * 90 deg V, LEFT bank (driver side, odd cylinders 1-3-5-7) on -X, offset forward
  * bore spacing 4.40 in, bore 3.90 in (99 mm), stroke 92 mm, rod 6.098 in,
    deck height 9.24 in -> piston top reaches the deck at TDC
  * cross-plane crank, firing order 1-8-7-2-6-5-4-3
  * OHV pushrod valvetrain, single cam in block, 2 valves / cylinder
  * sequential PORT fuel injection (injectors in the intake runners, not the chamber)
"""
import math
from mathutils import Vector, Matrix

FPS = 30
TOTAL_FRAMES = 3600
S45 = math.sqrt(0.5)

BORE_SPACING = 0.1118
BORE_R = 0.0495
CRANK_R = 0.046           # stroke 92 mm
ROD_L = 0.1549
COMP_H = 0.0338
DECK = 0.235
FIRING_ORDER = [1, 8, 7, 2, 6, 5, 4, 3]

# scene boundaries (seconds) - kept in sync with 01_Project/scene_timeline.json
SCENES = [(1, 0.0, 12.0), (2, 12.0, 26.5), (3, 26.5, 38.0), (4, 38.0, 55.0), (5, 55.0, 68.0),
          (6, 68.0, 88.0), (7, 88.0, 103.0), (8, 103.0, 114.5), (9, 114.5, 120.0)]

ORANGE = (1.0, 0.25, 0.013)
BLUE = (0.013, 0.47, 1.0)
GREEN = (0.047, 1.0, 0.26)
PURPLE = (0.45, 0.10, 1.0)
NEUTRAL = (0.65, 0.85, 1.0)


def bank(side):
    """side = 'L' or 'R'. Returns (d, u): d = cylinder axis (up/out), u = outward perpendicular."""
    s = -1 if side == 'L' else 1
    d = Vector((s * S45, 0, S45))
    u = Vector((s * S45, 0, -S45))
    return d, u


def bank_rot(side):
    return (0.0, (-1 if side == 'L' else 1) * math.radians(45), 0.0)


def bp(side, a, b, y):
    """Point in bank coordinates: a along cylinder axis, b outward, y along engine."""
    d, u = bank(side)
    return d * a + u * b + Vector((0, y, 0))


# cylinder table ---------------------------------------------------------------
CYL = {}
for k in range(4):
    ypin = (1.5 - k) * BORE_SPACING
    CYL[2 * k + 1] = dict(side='L', y=ypin + 0.0115, pin=k)   # 1,3,5,7
    CYL[2 * k + 2] = dict(side='R', y=ypin - 0.0115, pin=k)   # 2,4,6,8
for n, c in CYL.items():
    alpha = 135.0 if c['side'] == 'L' else 45.0
    psi = FIRING_ORDER.index(n) * 90.0           # crank angle of compression TDC
    c['alpha'] = alpha
    c['psi'] = psi
    c['pin_offset'] = (alpha - psi) % 360.0      # crankpin angle at crank angle 0
PIN_OFFSETS = {}
for n, c in CYL.items():
    PIN_OFFSETS.setdefault(c['pin'], c['pin_offset'])
    assert abs(((PIN_OFFSETS[c['pin']] - c['pin_offset']) + 180) % 360 - 180) < 1e-6, "pin sharing broken"


def crank_pin(n, theta_deg):
    c = CYL[n]
    phi = math.radians(c['pin_offset'] + theta_deg)
    ypin = (1.5 - c['pin']) * BORE_SPACING
    return Vector((CRANK_R * math.cos(phi), c['y'], CRANK_R * math.sin(phi))), ypin


def piston_s(n, theta_deg):
    """distance of wrist pin from crank axis along the bank axis + pin position."""
    pin, _ = crank_pin(n, theta_deg)
    d, _ = bank(CYL[n]['side'])
    p2 = Vector((pin.x, 0, pin.z))
    pd = p2.dot(d)
    s = pd + math.sqrt(max(1e-9, ROD_L ** 2 - (p2.length_squared - pd ** 2)))
    return s, pin


def cycle_angle(n, theta_deg):
    """0 = compression TDC (spark), 0-180 power, 180-360 exhaust, 360-540 intake, 540-720 compression"""
    return (theta_deg - CYL[n]['psi']) % 720.0


def lift(c, open_a, close_a):
    if open_a <= c <= close_a:
        x = (c - open_a) / (close_a - open_a)
        return math.sin(math.pi * x) ** 2
    return 0.0


def intake_lift(n, th):
    c = cycle_angle(n, th)
    return max(lift(c, 345, 595), lift(c + 720, 345, 595))


def exhaust_lift(n, th):
    c = cycle_angle(n, th)
    return max(lift(c, 125, 380), lift(c - 720, 125, 380))


def combustion(n, th):
    c = cycle_angle(n, th)
    if c < 75:
        return math.exp(-c / 22.0) * min(1.0, (c + 2) / 6.0)
    return 0.0


def spark(n, th):
    c = cycle_angle(n, th)
    return 1.0 if (c > 712 or c < 2) else 0.0


def injecting(n, th, pw=1.0):
    """Sequential port injection, closed-valve timing; pw scales pulse width."""
    c = cycle_angle(n, th)
    start = 330 - 110 * pw
    return 1.0 if start <= c <= 330 else 0.0


# time helpers -----------------------------------------------------------------
def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ramp(t, a, b):
    if b == a:
        return 1.0 if t >= a else 0.0
    return smooth((t - a) / (b - a))


def window(t, a, b, fade=0.6):
    return ramp(t, a - fade, a) * (1 - ramp(t, b, b + fade))


def mix(c1, c2, f):
    return tuple(a + (b - a) * f for a, b in zip(c1, c2))


def scene_at(t):
    for sid, a, b in SCENES:
        if a <= t < b:
            return sid
    return 9


def crank_speed(t):
    """visual crank speed in rev/s (slow-motion so the 4 strokes stay readable at 30 fps)"""
    v = 0.75
    v = v + (0.32 - v) * ramp(t, 13.0, 15.5)          # S2 slow-motion internals
    v = v + (0.60 - v) * ramp(t, 25.5, 27.5)          # S3
    v = v * (1 - ramp(t, 38.0, 39.0))                  # S4 engine stopped -> cold start
    v = v + 0.25 * window(t, 39.6, 40.6, 0.3)          # cranking
    v = v + 0.62 * ramp(t, 40.6, 42.0)                 # fires & idles (cold, open loop)
    v = v - 0.12 * ramp(t, 113.5, 117.0)
    return v


_ANG = [0.0]
for _f in range(1, TOTAL_FRAMES + 2):
    _ANG.append(_ANG[-1] + 360.0 * crank_speed((_f - 0.5) / FPS) / FPS)


def crank_angle(frame):
    f = max(0, min(TOTAL_FRAMES + 1, frame))
    return _ANG[int(f)]


def env(t, force_mode=None):
    """High-level visual state at time t (seconds)."""
    e = {}
    e['lights'] = ramp(t, 0.0, 3.0)
    # x-ray transparency of the outer castings
    e['ghost_shell'] = ramp(t, 13.0, 15.5) * (1 - ramp(t, 26.3, 28.3)) + 0.35 * window(t, 69.0, 88.0, 1.2) \
        + 0.25 * window(t, 103.0, 114.5, 0.4)
    e['ghost_intake'] = ramp(t, 12.5, 14.5) * (1 - ramp(t, 26.3, 28.3)) + 0.3 * window(t, 69.0, 88.0, 1.2)
    e['ghost_exhaust'] = 0.3 * window(t, 13.0, 26.5, 1.0) + 0.8 * window(t, 57.0, 88.0, 1.5) \
        + 0.6 * window(t, 103.0, 114.5, 0.4)
    # mode colour: 0 = orange (open loop), 1 = blue (closed loop)
    e['mode'] = ramp(t, 61.0, 66.5)
    e['accent'] = ramp(t, 38.0, 40.0) * (1 - ramp(t, 88.0, 89.5)) + ramp(t, 102.5, 104.0)
    e['trim'] = window(t, 88.6, 102.6, 0.9)              # S7 green/purple accents
    e['neutral'] = 1 - ramp(t, 38.0, 40.0) + ramp(t, 113.5, 116.0)
    e['air'] = window(t, 13.0, 26.5, 0.8) + 0.6 * window(t, 41.0, 55.0, 0.8) + 0.6 * window(t, 68.0, 88.0, 0.8)
    e['exhaust'] = window(t, 16.0, 26.5, 0.8) + window(t, 57.5, 88.0, 0.8) + 0.8 * window(t, 103.0, 114.5, 0.4)
    e['sensors'] = window(t, 27.5, 112.0, 0.8) * (1 - 0.75 * ramp(t, 54.0, 57.0))
    e['cmd'] = window(t, 31.0, 114.5, 0.8)
    e['o2_ready'] = ramp(t, 58.5, 62.5)
    e['o2_feedback'] = ramp(t, 64.0, 66.5) * (1 - ramp(t, 102.0, 103.0))
    e['map'] = window(t, 41.5, 56.0, 1.0)
    e['coolant'] = 20 + 70 * ramp(t, 55.5, 61.5) if t >= 42 else 20.0
    e['ecu_glow'] = window(t, 27.0, 114.5, 1.0)
    # STFT (fast, %), LTFT (slow, %), narrowband O2 voltage, pulse-width factor
    if t < 64.0:
        e['stft'], e['ltft'] = 0.0, 0.0
    else:
        e['stft'] = 6.0 * math.sin(2 * math.pi * 0.9 * t) * math.exp(-0.0 * t) + 2.0 * math.sin(2 * math.pi * 0.37 * t)
        e['ltft'] = 4.0 * ramp(t, 88.0, 101.0) + 1.0 * ramp(t, 66.0, 80.0)
        e['stft'] *= (1 - 0.45 * ramp(t, 88.0, 101.0))
    e['o2v'] = 0.45 + 0.4 * math.tanh(3 * math.sin(2 * math.pi * 0.9 * t + 1.2)) if t >= 62.0 else 0.45
    e['pw'] = 1.0 + (0.02 * (e['stft'] + e['ltft']) if t >= 64.0 else 0.25 * (1 - ramp(t, 42, 61)))
    e['split'] = None
    if force_mode is not None:
        e['mode'] = force_mode
        e['split'] = force_mode
        e['o2_feedback'] = 1.0 if force_mode > 0.5 else 0.0
        e['o2_ready'] = 1.0
    return e


# ------------------------------------------------------------------ camera path
# (time s, camera location, look-at target, lens mm). 'CUT' marks a hard cut (used under the split-screen wipe).
CAM_KEYS = [
    (0.0, (2.9, 3.2, 1.35), (0.0, 0.0, 0.15), 40),
    (6.0, (1.85, 2.05, 0.85), (0.0, 0.0, 0.15), 40),
    (11.5, (1.15, 1.6, 0.75), (0.0, 0.1, 0.22), 36),
    (14.5, (0.22, 1.05, 0.58), (0.0, 0.25, 0.40), 32),
    (17.0, (0.04, 0.50, 0.50), (0.0, 0.0, 0.36), 26),
    (19.8, (-0.52, 0.42, 0.58), (-0.15, 0.05, 0.24), 28),
    (23.0, (-0.12, 0.98, 0.22), (-0.04, 0.10, 0.10), 30),
    (26.2, (0.22, 0.95, 0.30), (0.0, 0.08, 0.12), 30),
    (29.8, (-1.20, 2.20, 1.10), (-0.30, 0.20, 0.22), 30),
    (37.6, (-0.95, 2.40, 1.12), (-0.25, 0.20, 0.22), 30),
    (41.0, (0.10, 2.05, 1.00), (0.10, 0.05, 0.16), 30),
    (48.0, (0.45, 1.95, 0.95), (0.25, 0.02, 0.14), 30),
    (54.6, (0.25, 1.85, 0.80), (0.10, 0.05, 0.12), 30),
    (57.6, (-0.75, 1.30, 0.62), (-0.22, 0.22, 0.20), 34),
    (61.8, (-1.10, -0.78, 0.08), (-0.34, -0.18, -0.12), 40),
    (66.5, (-1.65, -0.20, 0.55), (-0.30, -0.02, 0.02), 32),
    (72.5, (-1.80, 0.70, 0.80), (-0.35, 0.10, 0.08), 30),
    (80.0, (-1.85, -0.25, 0.70), (-0.35, 0.05, 0.04), 30),
    (87.6, (-1.55, 1.35, 1.00), (-0.45, 0.30, 0.22), 30),
    (91.0, (-1.30, 1.68, 0.98), (-0.78, 0.74, 0.50), 38),
    (102.99, (-1.20, 1.55, 0.92), (-0.78, 0.74, 0.50), 41, 'CUT'),
    (103.0, (-0.62, 2.10, 0.90), (-0.22, 0.04, 0.10), 26),
    (114.4, (-0.52, 1.92, 0.80), (-0.22, 0.04, 0.10), 26),
    (119.95, (0.95, 3.35, 1.55), (0.0, 0.0, 0.20), 34),
]


def _hermite(keys, t, idx):
    """piecewise cubic Hermite with Catmull-Rom tangents; zero tangent at ends and at cuts."""
    times = [k[0] for k in keys]
    if t <= times[0]:
        return _vec(keys[0][idx])
    if t >= times[-1]:
        return _vec(keys[-1][idx])
    i = max(j for j in range(len(times) - 1) if times[j] <= t)
    t0, t1 = times[i], times[i + 1]
    v0, v1 = Vector(_vec(keys[i][idx])), Vector(_vec(keys[i + 1][idx]))
    if len(keys[i]) > 4 and keys[i][4] == 'CUT':
        return _vec(keys[i + 1][idx]) if t > t0 else _vec(keys[i][idx])

    def tangent(j):
        if j == 0 or j == len(keys) - 1:
            return Vector([0.0] * len(v0))
        if len(keys[j]) > 4 and keys[j][4] == 'CUT':
            return Vector([0.0] * len(v0))
        if len(keys[j - 1]) > 4 and keys[j - 1][4] == 'CUT':
            return Vector([0.0] * len(v0))
        a, b = Vector(_vec(keys[j - 1][idx])), Vector(_vec(keys[j + 1][idx]))
        return (b - a) / (times[j + 1] - times[j - 1]) * 0.85
    m0, m1 = tangent(i) * (t1 - t0), tangent(i + 1) * (t1 - t0)
    s = (t - t0) / (t1 - t0)
    h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
    r = v0 * h00 + m0 * h10 + v1 * h01 + m1 * h11
    return tuple(r)


def _vec(v):
    return v if isinstance(v, (tuple, list)) else (v, 0.0)


def camera_at(t):
    loc = Vector(_hermite(CAM_KEYS, t, 1))
    tgt = Vector(_hermite(CAM_KEYS, t, 2))
    lens = _hermite(CAM_KEYS, t, 3)[0]
    return loc, tgt, lens


# ------------------------------------------------------------------ per-frame application (bpy)
_CACHE = {}


def _paths():
    import bpy, json
    if 'paths' not in _CACHE:
        _CACHE['paths'] = json.loads(bpy.data.texts['ls_paths.json'].as_string())
    return _CACHE['paths']


def _along(pts, u):
    u = max(0.0, min(0.9999, u))
    x = u * (len(pts) - 1)
    i = int(x); f = x - i
    a, b = Vector(pts[i]), Vector(pts[i + 1])
    return a.lerp(b, f)


def _em(mat_name, color=None, strength=None):
    import bpy
    m = bpy.data.materials[mat_name]
    nt = m.node_tree
    n = nt.nodes.get('em')
    if n is not None:
        if color is not None:
            n.inputs['Color'].default_value = (*color, 1)
        if strength is not None:
            n.inputs['Strength'].default_value = strength
    else:
        p = nt.nodes.get('Principled BSDF')
        if color is not None:
            p.inputs['Emission Color'].default_value = (*color, 1)
        if strength is not None:
            p.inputs['Emission Strength'].default_value = strength


def apply_frame(scene, frame, force_mode=None):
    """Pose every animated element for `frame`. Returns env dict for overlays."""
    import bpy
    O = bpy.data.objects
    t = frame / FPS
    e = env(t, force_mode)
    th = crank_angle(frame)
    P = _paths()

    # camera
    cam = scene.camera
    loc, tgt, lens = camera_at(t)
    cam.location = loc
    cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    cam.data.dof.focus_distance = (tgt - loc).length

    # rotating assembly
    O['Crankshaft'].rotation_euler = (0, -math.radians(th), 0)
    O['Camshaft'].rotation_euler = (0, -math.radians(th / 2), 0)
    O['ThrottlePlate'].rotation_euler = (math.radians(90 - 12 - 6 * math.sin(t * 0.7)), 0, 0)
    for n, c in CYL.items():
        side = c['side']
        d, u = bank(side)
        s, pin = piston_s(n, th)
        wrist = d * s + Vector((0, c['y'], 0))
        O[f'Piston_{n}'].location = wrist
        rod = O[f'Rod_{n}']
        rod.location = pin
        rod.rotation_quaternion = (wrist - pin).to_track_quat('Z', 'Y')
        for kind, lf, dy in (('Intake', intake_lift(n, th), 0.021), ('Exhaust', exhaust_lift(n, th), -0.021)):
            v = O[f'{kind}Valve_{n}']
            v.location = Vector(v['rest']) - d * (0.0115 * lf)
            pr = O[f'Pushrod_{kind}_{n}']
            pr.location = Vector(pr['rest']) + Vector(pr['dir']) * (0.0075 * lf)
            rk = O[f'Rocker_{kind}_{n}']
            r0 = rk['rest']
            rk.rotation_euler = (r0[0], r0[1] + (-1 if side == 'L' else 1) * math.radians(6) * lf, r0[2])
        cb = combustion(n, th)
        cf = O[f'Combustion_{n}']
        cf.hide_render = cb < 0.02
        cf.scale = (0.6 + 0.4 * cb, 0.6 + 0.4 * cb, 0.25 * (0.4 + cb))
        O[f'CombLight_{n}'].data.energy = 6.0 * cb
        O[f'Spark_{n}'].hide_render = spark(n, th) < 0.5
        inj = injecting(n, th, e['pw'])
        sp = O[f'Spray_{n}']
        sp.hide_render = inj < 0.5 or t < 13.5 and t > 0 and False
        sp.scale = (1, 1, 1) if inj else (0.01, 0.01, 0.01)
    _em('Combustion', strength=22.0)
    _em('Spark', strength=60.0)
    _em('Spray_Fuel', strength=2.2)

    # flow particles
    for n in CYL:
        ap = P['air'][str(n)]
        for k in range(9):
            o = O[f'Air_{n}_{k}']
            u = (t * 0.32 + k / 9 + n * 0.071) % 1.0
            o.location = _along(ap, u)
            sc = e['air'] * min(1, u * 8, (1 - u) * 8)
            o.hide_render = sc < 0.05
            o.scale = (sc,) * 3
        xp = P['exh'][str(n)]
        for k in range(7):
            o = O[f'Exh_{n}_{k}']
            u = (t * 0.26 + k / 7 + n * 0.113) % 1.0
            o.location = _along(xp, u)
            sc = e['exhaust'] * min(1, u * 8, (1 - u) * 8)
            o.hide_render = sc < 0.05
            o.scale = (sc,) * 3

    # x-ray
    for grp, key in (('shell', 'ghost_shell'), ('intake', 'ghost_intake'), ('exhaust', 'ghost_exhaust')):
        for m in bpy.data.materials:
            if m.get('ghost_group') == grp:
                m.node_tree.nodes['ghost'].outputs[0].default_value = min(1.0, e[key])

    # mode colour
    mode_col = mix(ORANGE, BLUE, e['mode'])
    neutral_w = min(1.0, e['neutral'])
    ring = mix(mode_col, (0.8, 0.85, 1.0), neutral_w)
    if e['split'] is None and t > 113.5:
        ring = mix(ring, (0.8, 0.85, 1.0), ramp(t, 114.5, 116.0))
    _em('Pedestal_Ring', ring, (1.5 + 2.5 * (1 - neutral_w)) * e['lights'])
    acc = e['accent'] * (1 - neutral_w * 0.0)
    L = O['AccentL'].data; R = O['AccentR'].data; U = O['Under'].data
    if e['trim'] > 0.01:
        L.color = mix(mode_col, GREEN, e['trim']); R.color = mix(mode_col, PURPLE, e['trim'])
    elif t > 114.5 and e['split'] is None:
        L.color, R.color = ORANGE, BLUE
    else:
        L.color = R.color = mode_col
    U.color = mode_col
    fin = ramp(t, 114.5, 116.5) if e['split'] is None else 0.0
    L.energy = 90 * max(acc, fin) * e['lights']
    R.energy = 90 * max(acc, fin) * e['lights']
    U.energy = 20 * acc
    for nm in ('Key', 'Fill', 'RimL', 'RimR', 'Top'):
        o = O[nm]
        o.data.energy = o['base_energy'] * e['lights'] * (1 - 0.35 * acc)
        if nm in ('RimL', 'RimR'):
            o.data.color = mix((1, 1, 1), mode_col, 0.6 * acc)

    # sensors & signals
    o2c = mix((1.0, 0.25, 0.05), (1.0, 0.45, 0.1), e['o2_ready'])
    for sd in 'LR':
        pass
    _em('O2_Tip', o2c, 1.0 + 30 * e['o2_ready'])
    tempf = (e['coolant'] - 20) / 70
    _em('ECT_Glow', mix((0.1, 0.4, 1.0), (1.0, 0.25, 0.05), tempf), 8.0 * e['sensors'] + 6 * window(t, 55, 62, 1))
    _em('ECU_LED', mix(NEUTRAL, mode_col, 1 - neutral_w) if e['trim'] < 0.5 else GREEN, 25 * e['ecu_glow'])
    wires = P['wires']
    for name, pts in wires.items():
        if name.startswith('O2'):
            act = e['o2_feedback']
            col = BLUE
            sheath_strength = 0.4 * e['sensors'] * (1 - act) + 2.5 * act
            sheath_col = mix((0.25, 0.25, 0.28), BLUE, act)
            vis = e['sensors'] > 0.02
        elif name.startswith('INJ'):
            act = e['cmd']
            col = mix(NEUTRAL, mode_col, 1 - neutral_w)
            if e['trim'] > 0.01:
                col = mix(col, GREEN, e['trim'])
            sheath_strength, sheath_col, vis = 2.0 * act, col, act > 0.02
        else:
            act = e['sensors']
            col = NEUTRAL
            sheath_strength, sheath_col, vis = 1.2 * act, col, act > 0.02
        O[f'Wire_{name}'].hide_render = not vis
        _em(f'WireSheath_{name}', sheath_col, sheath_strength)
        _em(f'Wire_{name}', col, 14.0)
        speed = 0.55 if not name.startswith('O2') else 0.45
        for k in range(4):
            o = O[f'Pulse_{name}_{k}']
            u = (t * speed + k / 4) % 1.0
            o.location = _along(pts, u)
            sc = act * min(1, u * 10, (1 - u) * 10)
            o.hide_render = sc < 0.05
            o.scale = (sc,) * 3

    # fuel map
    fm = O['FuelMap']
    vis = e['map'] > 0.01
    for o in [fm] + list(fm.children):
        o.hide_render = not vis
    fm.scale = (1, 1, max(0.01, e['map']))
    mk = O['FuelMapMarker']
    rpm_x = 0.15 + 0.1 * math.sin(t * 0.6)
    load_y = 0.25 + 0.15 * math.sin(t * 0.37 + 1)
    zz = 0.15 + 0.65 * load_y ** 1.15 * (0.85 + 0.25 * math.sin(math.pi * (0.2 + 0.7 * rpm_x))) + 0.08 * (1 - rpm_x) * (1 - load_y)
    mk.location = ((rpm_x - 0.5) * 0.5, (load_y - 0.5) * 0.5, zz * 0.28 + 0.012)
    return e


def anchors_2d(scene):
    """screen-space (pixels, origin top-left, in final 1920x1080 space) of labelled 3D points."""
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    P = _paths()
    out = {}
    for k, v in P['anchors'].items():
        co = world_to_camera_view(scene, scene.camera, Vector(v))
        out[k] = (round(co.x * 1920, 1), round((1 - co.y) * 1080, 1), round(co.z, 3))
    return out
