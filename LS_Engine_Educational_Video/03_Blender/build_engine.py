"""Procedurally build a technically-faithful GM LS-style V8 (Gen III/IV architecture) + studio.

Run:  python3 03_Blender/build_engine.py      (uses the `bpy` module, Blender 5.x)
Creates the geometry/material/light setup in the current bpy session. create_scenes.py
calls build() and then adds cameras/keyframes and saves LS_Engine_Master.blend.

All parts are original procedural geometry (no third-party models -> no licensing issues).
Simplifications (documented in 01_Project/technical_validation.md): no water jackets,
no accessory belt, simplified rocker geometry, valves parallel to bore axis.
"""
import math, os, sys
import bpy, bmesh
from mathutils import Vector, Matrix, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import animate_engine as A

C = {}          # collections
M = {}          # materials
GHOST = {'shell': [], 'intake': [], 'exhaust': []}   # value nodes driving x-ray transparency


# ------------------------------------------------------------------ helpers
def coll(name):
    if name not in C:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        C[name] = c
    return C[name]


def link(obj, cname):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll(cname).objects.link(obj)
    return obj


def principled(m):
    return m.node_tree.nodes.get('Principled BSDF')


def make_mat(name, color, metallic=0.0, rough=0.5, coat=0.0, emit=None, strength=0.0, aniso=0.0, ghost=None, cast=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    p = principled(m)
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metallic
    p.inputs['Roughness'].default_value = rough
    if coat:
        p.inputs['Coat Weight'].default_value = coat
        p.inputs['Coat Roughness'].default_value = 0.08
    if aniso and 'Anisotropic' in p.inputs:
        p.inputs['Anisotropic'].default_value = aniso
    if emit is not None:
        p.inputs['Emission Color'].default_value = (*emit, 1)
        p.inputs['Emission Strength'].default_value = strength
    if cast:
        nt = m.node_tree
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 900.0
        nz.inputs['Detail'].default_value = 4.0
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = cast
        bump.inputs['Distance'].default_value = 0.0004
        nt.links.new(nz.outputs['Fac'], bump.inputs['Height']); nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
        rr = nt.nodes.new('ShaderNodeMapRange'); rr.inputs['To Min'].default_value = rough - 0.08
        rr.inputs['To Max'].default_value = rough + 0.1
        nt.links.new(nz.outputs['Fac'], rr.inputs['Value']); nt.links.new(rr.outputs['Result'], p.inputs['Roughness'])
    if ghost:
        add_ghost(m, ghost)
    M[name] = m
    return m


def add_ghost(m, group):
    """Mix the surface with an x-ray shader (transparent + blue fresnel edge glow)."""
    nt = m.node_tree
    out = nt.nodes.get('Material Output')
    p = principled(m)
    val = nt.nodes.new('ShaderNodeValue'); val.name = 'ghost'; val.outputs[0].default_value = 0.0
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    lw = nt.nodes.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = 0.25
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (0.18, 0.42, 1.0, 1)
    mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 0.55
    nt.links.new(lw.outputs['Facing'], mul.inputs[0]); nt.links.new(mul.outputs[0], em.inputs['Strength'])
    add = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(tr.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    # ghost value 0..1 -> mix factor 0..0.93 (keep a faint body)
    mf = nt.nodes.new('ShaderNodeMath'); mf.operation = 'MULTIPLY'; mf.inputs[1].default_value = 0.96
    nt.links.new(val.outputs[0], mf.inputs[0])
    mx = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(mf.outputs[0], mx.inputs[0]); nt.links.new(p.outputs[0], mx.inputs[1]); nt.links.new(add.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    GHOST[group].append(val)
    m['ghost_group'] = group


def emis_mat(name, color, strength):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(n)
    em = nt.nodes.new('ShaderNodeEmission'); em.name = 'em'
    em.inputs['Color'].default_value = (*color, 1); em.inputs['Strength'].default_value = strength
    nt.links.new(em.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
    M[name] = m
    return m


def set_active(o):
    bpy.context.view_layer.objects.active = o
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    o.select_set(True)


def finish(o, name, mat, cname, bevel=0.0, smooth=False, seg=2):
    o.name = name
    if mat:
        o.data.materials.clear(); o.data.materials.append(mat)
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = seg; b.limit_method = 'ANGLE'
    if smooth:
        for poly in o.data.polygons:
            poly.use_smooth = True
    link(o, cname)
    return o


def box(name, size, loc, rot=(0, 0, 0), mat=None, cname='Engine', bevel=0.0, seg=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, name, mat, cname, bevel, seg=seg)


def cyl(name, r, depth, loc, rot=(0, 0, 0), mat=None, cname='Engine', verts=32, bevel=0.0, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    f = finish(o, name, mat, cname, bevel, smooth=smooth)
    if smooth:
        try:
            bpy.ops.object.shade_auto_smooth(angle=math.radians(40))
        except Exception:
            pass
    return f


def sphere(name, r, loc, mat=None, cname='Engine', seg=16, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=seg // 2, radius=r, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    return finish(o, name, mat, cname, smooth=True)


def along(name, p0, p1, r, mat, cname='Engine', verts=24):
    """cylinder between two points"""
    p0, p1 = Vector(p0), Vector(p1)
    v = p1 - p0
    q = v.to_track_quat('Z', 'Y')
    o = cyl(name, r, v.length, (p0 + p1) / 2, q.to_euler(), mat, cname, verts)
    return o


def tube(name, pts, r, mat, cname='Engine', res=6, smooth_pts=True):
    """bevelled curve through points (kept as curve -> lighter for Cycles)."""
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new('NURBS' if smooth_pts and len(pts) > 2 else 'POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    if sp.type == 'NURBS':
        sp.use_endpoint_u = True; sp.order_u = min(4, len(pts))
    cu.bevel_depth = r; cu.bevel_resolution = res; cu.use_fill_caps = True; cu.resolution_u = 16
    o = bpy.data.objects.new(name, cu)
    coll(cname).objects.link(o)
    if mat:
        cu.materials.append(mat)
    return o


def boolean(target, cutter, op='DIFFERENCE'):
    mod = target.modifiers.new('bool', 'BOOLEAN'); mod.operation = op; mod.object = cutter
    try:
        mod.solver = 'EXACT'
    except Exception:
        pass
    set_active(target)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def apply_mods(o):
    set_active(o)
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


# ------------------------------------------------------------------ materials
def materials():
    alu = (0.62, 0.62, 0.64)
    make_mat('Block_CastAluminium', (0.40, 0.40, 0.42), 1.0, 0.45, ghost='shell', cast=0.5)
    make_mat('Head_Aluminium', (0.60, 0.60, 0.62), 1.0, 0.33, ghost='shell', cast=0.35)
    make_mat('ValveCover_Black', (0.02, 0.02, 0.022), 0.3, 0.38, coat=0.6, ghost='shell')
    make_mat('Coil_Black', (0.015, 0.015, 0.015), 0.0, 0.45, ghost='shell')
    make_mat('Intake_Composite', (0.03, 0.03, 0.032), 0.0, 0.42, coat=0.3, ghost='intake')
    make_mat('Throttle_Aluminium', alu, 1.0, 0.22, ghost='intake')
    make_mat('Exhaust_CastIron', (0.16, 0.12, 0.10), 0.85, 0.62, ghost='exhaust', cast=0.8)
    make_mat('Piston_Aluminium', (0.80, 0.80, 0.82), 1.0, 0.18)
    make_mat('Forged_Steel', (0.56, 0.57, 0.60), 1.0, 0.24, aniso=0.5)
    make_mat('Polished_Steel', (0.85, 0.86, 0.88), 1.0, 0.1)
    make_mat('Valve_Steel', (0.70, 0.70, 0.72), 1.0, 0.2)
    make_mat('Injector_Body', (0.06, 0.06, 0.07), 0.0, 0.35)
    make_mat('Injector_Seal', (0.05, 0.25, 0.08), 0.0, 0.5)
    make_mat('Connector_Grey', (0.25, 0.26, 0.28), 0.0, 0.5)
    make_mat('Sensor_Brass', (0.85, 0.62, 0.28), 1.0, 0.3)
    make_mat('Rubber', (0.012, 0.012, 0.012), 0.0, 0.7)
    make_mat('Duct_Rubber', (0.015, 0.015, 0.016), 0.0, 0.6, ghost='intake')
    make_mat('Belt_Rubber', (0.012, 0.012, 0.012), 0.0, 0.7, ghost='shell')
    make_mat('Pulley_Black', (0.03, 0.03, 0.03), 0.6, 0.35, ghost='shell')
    make_mat('Ring_Black', (0.03, 0.03, 0.03), 0.6, 0.35)
    make_mat('Pan_Aluminium', (0.45, 0.45, 0.47), 1.0, 0.5, cast=0.4, ghost='shell')
    make_mat('ECU_Case', (0.07, 0.075, 0.085), 1.0, 0.5)
    make_mat('ECU_Connector_Blue', (0.02, 0.10, 0.35), 0.0, 0.45)
    make_mat('ECU_Connector_Grey', (0.30, 0.30, 0.32), 0.0, 0.45)
    make_mat('Floor', (0.006, 0.0065, 0.008), 0.0, 0.28)
    make_mat('Pedestal', (0.02, 0.02, 0.024), 0.6, 0.3)
    make_mat('Backdrop', (0.004, 0.0045, 0.006), 0.0, 0.95)
    emis_mat('Spray_Fuel', (1.0, 0.72, 0.28), 0.0)
    emis_mat('Combustion', (1.0, 0.45, 0.08), 0.0)
    emis_mat('Spark', (0.6, 0.8, 1.0), 0.0)
    emis_mat('Air_Particle', (0.55, 0.85, 1.0), 4.0)
    emis_mat('Exhaust_Particle', (1.0, 0.42, 0.12), 4.0)
    emis_mat('O2_Tip', (1.0, 0.25, 0.05), 0.0)
    emis_mat('ECT_Glow', (0.2, 0.6, 1.0), 0.0)
    emis_mat('Pedestal_Ring', (1, 1, 1), 2.0)
    emis_mat('ECU_LED', (0.2, 0.7, 1.0), 0.0)
    emis_mat('Map_Marker', (1, 1, 1), 8.0)
    emis_mat('Map_Grid', (1.0, 0.45, 0.1), 1.5)
    # fuel map surface: colour from vertex attribute
    m = bpy.data.materials.new('FuelMap_Surface')
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree; p = principled(m)
    at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_name = 'height'
    cr = nt.nodes.new('ShaderNodeValToRGB')
    cr.color_ramp.elements[0].color = (0.25, 0.03, 0.0, 1); cr.color_ramp.elements[1].color = (1.0, 0.55, 0.05, 1)
    nt.links.new(at.outputs['Fac'], cr.inputs[0])
    nt.links.new(cr.outputs[0], p.inputs['Base Color']); nt.links.new(cr.outputs[0], p.inputs['Emission Color'])
    p.inputs['Emission Strength'].default_value = 0.6; p.inputs['Roughness'].default_value = 0.35
    p.inputs['Alpha'].default_value = 1.0
    M['FuelMap_Surface'] = m


# ------------------------------------------------------------------ engine
def build_block():
    mat = M['Block_CastAluminium']
    base = box('Block', (0.40, 0.60, 0.20), (0, 0, -0.02), mat=mat)
    for side in 'LR':
        d, u = A.bank(side)
        c = A.bp(side, 0.13, 0.0, 0.0)
        b = box('tmp', (0.16, 0.60, 0.21), c, A.bank_rot(side), mat=mat)
        mod = base.modifiers.new('u', 'BOOLEAN'); mod.operation = 'UNION'; mod.object = b
        try:
            mod.solver = 'EXACT'
        except Exception:
            pass
        set_active(base); bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(b, do_unlink=True)
    # cylinder bores (visible in x-ray mode)
    for n, cdat in A.CYL.items():
        side = cdat['side']
        c = A.bp(side, 0.17, 0, cdat['y'])
        cut = cyl('cut', A.BORE_R + 0.002, 0.16, c, A.bank_rot(side), verts=40)
        boolean(base, cut)
    # crank tunnel
    cut = cyl('cut', 0.11, 0.64, (0, 0, 0), (math.pi / 2, 0, 0), verts=40)
    boolean(base, cut)
    b = base.modifiers.new('bevel', 'BEVEL'); b.width = 0.006; b.segments = 2; b.limit_method = 'ANGLE'
    # oil pan (LS car-style aluminium pan), front cover, rear flange
    box('OilPan', (0.36, 0.56, 0.17), (0, -0.01, -0.205), mat=M['Pan_Aluminium'], bevel=0.02, seg=3)
    box('OilPanRail', (0.40, 0.60, 0.018), (0, -0.01, -0.12), mat=M['Pan_Aluminium'], bevel=0.004)
    box('FrontCover', (0.30, 0.03, 0.30), (0, 0.312, 0.02), mat=M['Block_CastAluminium'], bevel=0.02, seg=3)
    box('RearFlange', (0.50, 0.02, 0.50), (0, -0.312, 0.02), mat=M['Block_CastAluminium'], bevel=0.03, seg=3)
    # harmonic balancer, water pump, idler pulleys (front accessory drive, simplified)
    cyl('Balancer', 0.10, 0.05, (0, 0.36, 0), (math.pi / 2, 0, 0), M['Pulley_Black'], verts=48)
    cyl('BalancerHub', 0.04, 0.06, (0, 0.37, 0), (math.pi / 2, 0, 0), M['Forged_Steel'], verts=32)
    cyl('WaterPump', 0.075, 0.07, (0, 0.36, 0.20), (math.pi / 2, 0, 0), M['Throttle_Aluminium'], verts=48)
    cyl('WaterPumpPulley', 0.08, 0.025, (0, 0.40, 0.20), (math.pi / 2, 0, 0), M['Pulley_Black'], verts=48)
    cyl('Alternator', 0.07, 0.14, (-0.24, 0.30, 0.20), (math.pi / 2, 0, 0), M['Throttle_Aluminium'], verts=40)
    cyl('AltPulley', 0.035, 0.03, (-0.24, 0.39, 0.20), (math.pi / 2, 0, 0), M['Pulley_Black'], verts=32)
    cyl('PSPump', 0.06, 0.10, (0.25, 0.32, 0.26), (math.pi / 2, 0, 0), M['Pulley_Black'], verts=40)
    cyl('PSPulley', 0.07, 0.025, (0.25, 0.39, 0.26), (math.pi / 2, 0, 0), M['Pulley_Black'], verts=40)
    belt = [(0, 0.395, -0.10), (-0.10, 0.395, 0.02), (-0.27, 0.395, 0.20), (-0.08, 0.395, 0.28),
            (0.0, 0.395, 0.28), (0.17, 0.395, 0.33), (0.31, 0.395, 0.26), (0.10, 0.395, 0.0), (0, 0.395, -0.10)]
    tube('Belt', belt, 0.006, M['Belt_Rubber'])


def build_heads():
    for side in 'LR':
        rot = A.bank_rot(side)
        box(f'Head_{side}', (0.22, 0.58, 0.10), A.bp(side, 0.283, 0.0, 0.0), rot, M['Head_Aluminium'], bevel=0.01)
        box(f'ValveCover_{side}', (0.17, 0.56, 0.065), A.bp(side, 0.366, -0.005, 0.0), rot, M['ValveCover_Black'],
            bevel=0.022, seg=4)
        for n, c in A.CYL.items():
            if c['side'] != side:
                continue
            # coil-near-plug ignition: coil packs on the valve cover, short leads to plugs on the head side
            coil = A.bp(side, 0.41, 0.045, c['y'])
            box(f'Coil_{n}', (0.05, 0.06, 0.035), coil, rot, M['Coil_Black'], bevel=0.006)
            plug = A.bp(side, 0.29, 0.115, c['y'] + 0.012)
            tube(f'PlugWire_{n}', [coil + A.bank(side)[1] * 0.03, A.bp(side, 0.37, 0.14, c['y'] + 0.01), plug], 0.0045,
                 M['Rubber'], res=3)
            cyl(f'PlugBoot_{n}', 0.009, 0.03, plug, rot, M['Rubber'], verts=12)
    # ECT sensor: Gen III LS - front of the driver-side (left) cylinder head
    p = A.bp('L', 0.27, -0.05, 0.30)
    cyl('ECT_Sensor', 0.010, 0.035, p, (math.pi / 2, 0, 0), M['Sensor_Brass'], verts=6)
    sphere('ECT_Glow', 0.012, p + Vector((0, 0.02, 0)), M['ECT_Glow'])
    box('ECT_Plug', (0.018, 0.025, 0.02), p + Vector((0, 0.03, 0)), mat=M['Connector_Grey'], bevel=0.003)


def build_internals():
    # crankshaft as one object built around the Y axis (rotates about Y)
    mats = M['Forged_Steel']
    parts = []
    parts.append(cyl('crk', 0.0325, 0.60, (0, 0, 0), (math.pi / 2, 0, 0), mats, 'Internals', 32))
    for k in range(4):
        ang = math.radians(A.PIN_OFFSETS[k])
        ypin = (1.5 - k) * A.BORE_SPACING
        pc = Vector((A.CRANK_R * math.cos(ang), ypin, A.CRANK_R * math.sin(ang)))
        parts.append(cyl('crk', 0.0275, 0.05, pc, (math.pi / 2, 0, 0), mats, 'Internals', 24))
        for dy in (-0.032, 0.032):
            web = box('crk', (0.06, 0.016, 0.075), (pc.x / 2, ypin + dy, pc.z / 2),
                      (0, -(ang - math.pi / 2), 0), mats, 'Internals', bevel=0.008)
            # counterweight on the opposite side
            cw = Vector((-math.cos(ang), 0, -math.sin(ang))) * 0.045
            parts.append(box('crk', (0.12, 0.016, 0.05), (cw.x, ypin + dy, cw.z), (0, -(ang - math.pi / 2), 0), mats,
                             'Internals', bevel=0.012))
            parts.append(web)
    parts.append(cyl('crk', 0.035, 0.03, (0, 0.33, 0), (math.pi / 2, 0, 0), mats, 'Internals'))
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in parts)
    bpy.ops.object.join()
    crank = bpy.context.active_object; crank.name = 'Crankshaft'
    # camshaft in block (OHV) - rotates at half crank speed
    cam = cyl('Camshaft', 0.022, 0.58, (0, 0, 0.125), (math.pi / 2, 0, 0), M['Forged_Steel'], 'Internals', 24)
    lobes = []
    for n, c in A.CYL.items():
        for j, dy in enumerate((0.018, -0.018)):
            lob = sphere('lobe', 0.026, (0, c['y'] + dy, 0.125), M['Forged_Steel'], 'Internals', 16, (1.0, 0.35, 0.75))
            lob.rotation_euler = (0, math.radians(c['psi'] / 2 + j * 110), 0)
            lobes.append(lob)
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in lobes or ob == cam)
    bpy.context.view_layer.objects.active = cam
    bpy.ops.object.join()
    cam = bpy.context.active_object; cam.name = 'Camshaft'
    cam.location = (0, 0, 0.125)
    # move origin onto the cam axis
    me = cam.data
    # (cylinder was created at its location so origin already on axis)

    for n, c in A.CYL.items():
        side = c['side']; rot = A.bank_rot(side)
        # piston (origin at wrist pin)
        pm = bpy.data.meshes.new(f'Piston_{n}')
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=A.BORE_R - 0.0008, radius2=A.BORE_R - 0.0008,
                              depth=0.062, matrix=Matrix.Translation((0, 0, 0.0028)))
        bm.to_mesh(pm); bm.free()
        po = bpy.data.objects.new(f'Piston_{n}', pm); coll('Internals').objects.link(po)
        pm.materials.append(M['Piston_Aluminium'])
        for poly in pm.polygons:
            poly.use_smooth = True
        bv = po.modifiers.new('bevel', 'BEVEL'); bv.width = 0.003; bv.segments = 2; bv.limit_method = 'ANGLE'
        po.rotation_euler = rot
        # ring lands (dark bands) as children
        for i, z in enumerate((0.022, 0.016, 0.010)):
            ring = cyl(f'Ring_{n}_{i}', A.BORE_R - 0.0002, 0.0016, (0, 0, z), (0, 0, 0), M['Ring_Black'], 'Internals', 48)
            ring.parent = po
        pin = cyl(f'WristPin_{n}', 0.011, 0.07, (0, 0, 0), (math.pi / 2, 0, 0), M['Polished_Steel'], 'Internals', 16)
        pin.parent = po
        # connecting rod: origin at big end, +Z toward wrist pin
        parts = [cyl('rod', 0.03, 0.022, (0, 0, 0), (math.pi / 2, 0, 0), M['Forged_Steel'], 'Internals', 24),
                 box('rod', (0.022, 0.016, A.ROD_L - 0.04), (0, 0, A.ROD_L / 2), mat=M['Forged_Steel'],
                     cname='Internals', bevel=0.004),
                 cyl('rod', 0.017, 0.022, (0, 0, A.ROD_L), (math.pi / 2, 0, 0), M['Forged_Steel'], 'Internals', 20)]
        for ob in bpy.context.view_layer.objects:
            ob.select_set(ob in parts)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.join(); rod = bpy.context.active_object; rod.name = f'Rod_{n}'
        rod.rotation_mode = 'QUATERNION'
        # valves (parallel to bore axis, simplified), intake on the front half of each chamber pair
        for kind, dy, r in (('Intake', 0.021, 0.0254), ('Exhaust', -0.021, 0.0200)):
            parts = [cyl('v', r, 0.004, (0, 0, 0), (0, 0, 0), M['Valve_Steel'], 'Internals', 32),
                     cyl('v', 0.004, 0.13, (0, 0, 0.066), (0, 0, 0), M['Valve_Steel'], 'Internals', 12),
                     cyl('v', 0.014, 0.03, (0, 0, 0.10), (0, 0, 0), M['Polished_Steel'], 'Internals', 16)]
            for ob in bpy.context.view_layer.objects:
                ob.select_set(ob in parts)
            bpy.context.view_layer.objects.active = parts[0]
            bpy.ops.object.join(); v = bpy.context.active_object; v.name = f'{kind}Valve_{n}'
            v.rotation_euler = rot
            v['rest'] = tuple(A.bp(side, A.DECK + 0.004, 0.0, c['y'] + dy))
            v.location = v['rest']
            # pushrod from lifter (valley, above cam) to rocker on head
            top = A.bp(side, 0.345, -0.055, c['y'] + dy)
            bot = Vector((0.045 * (-1 if side == 'L' else 1), c['y'] + dy, 0.165))
            pr = along(f'Pushrod_{kind}_{n}', bot, top, 0.0042, M['Polished_Steel'], 'Internals', 10)
            pr['rest'] = tuple(pr.location); pr['dir'] = tuple((top - bot).normalized())
            rk = box(f'Rocker_{kind}_{n}', (0.012, 0.012, 0.065), (0, 0, 0), mat=M['Forged_Steel'], cname='Internals',
                     bevel=0.003)
            rk.location = A.bp(side, 0.352, -0.025, c['y'] + dy)
            rk.rotation_euler = (0, (-1 if side == 'L' else 1) * math.radians(45 + 90), 0)
            rk['rest'] = tuple(rk.rotation_euler)
        # combustion flash (flattened sphere in the chamber) + spark
        cf = sphere(f'Combustion_{n}', A.BORE_R * 0.92, A.bp(side, A.DECK - 0.006, 0, c['y']), M['Combustion'],
                    'Effects', 20, (1, 1, 0.25))
        cf.rotation_euler = rot
        sphere(f'Spark_{n}', 0.006, A.bp(side, A.DECK + 0.001, 0.012, c['y']), M['Spark'], 'Effects', 8)
        lt = bpy.data.lights.new(f'CombLight_{n}', 'POINT'); lt.color = (1.0, 0.5, 0.15); lt.shadow_soft_size = 0.03
        lo = bpy.data.objects.new(f'CombLight_{n}', lt); coll('Effects').objects.link(lo)
        lo.location = A.bp(side, A.DECK - 0.02, 0, c['y'])
    return crank, cam


def runner_points(n):
    c = A.CYL[n]; side = c['side']; s = -1 if side == 'L' else 1
    port = A.bp(side, 0.300, -0.112, c['y'])
    # LS runners rise from the port, arc over the valley and enter the centre plenum
    return [port + Vector((0, 0, -0.005)), port + Vector((-s * 0.012, 0, 0.045)), Vector((s * 0.10, c['y'], 0.395)),
            Vector((s * 0.07, c['y'] * 0.97, 0.415)), Vector((s * 0.03, c['y'] * 0.95, 0.415))]


def build_intake():
    mi = M['Intake_Composite']
    box('Plenum', (0.15, 0.46, 0.085), (0, -0.02, 0.415), mat=mi, bevel=0.032, seg=4)
    box('PlenumLid', (0.11, 0.40, 0.012), (0, -0.02, 0.46), mat=mi, bevel=0.005)
    for i in range(5):
        box(f'PlenumRib_{i}', (0.13, 0.008, 0.012), (0, 0.16 - i * 0.09, 0.462), mat=mi, bevel=0.003)
    for n in A.CYL:
        tube(f'Runner_{n}', runner_points(n), 0.024, mi, 'Intake')
    # throttle body (drive-by-wire), TPS on its side, MAF in the inlet duct, MAP at rear of manifold
    tb = Vector((0, 0.255, 0.415))
    cyl('ThrottleBody', 0.052, 0.07, tb, (math.pi / 2, 0, 0), M['Throttle_Aluminium'], 'Intake', 48, bevel=0.004)
    cyl('ThrottleNeck', 0.048, 0.04, tb + Vector((0, -0.05, 0)), (math.pi / 2, 0, 0), mi, 'Intake', 40)
    cyl('ThrottlePlate', 0.044, 0.003, tb, (math.pi / 2, 0, 0), M['Polished_Steel'], 'Intake', 32)
    box('ETC_Motor', (0.05, 0.05, 0.07), tb + Vector((0.075, 0, -0.01)), mat=M['Throttle_Aluminium'], cname='Intake',
        bevel=0.008)
    box('TPS_Sensor', (0.02, 0.04, 0.04), tb + Vector((-0.062, 0, 0)), mat=M['Connector_Grey'], cname='Intake',
        bevel=0.004)
    tube('IntakeDuct', [tb + Vector((0, 0.035, 0)), tb + Vector((0, 0.16, 0.0)), tb + Vector((0, 0.27, 0.03)),
                        tb + Vector((0, 0.40, 0.05))], 0.05, M['Duct_Rubber'], 'Intake')
    maf = tb + Vector((0, 0.27, 0.03))
    cyl('MAF_Housing', 0.056, 0.08, maf, (math.pi / 2, 0, 0), M['Intake_Composite'], 'Intake', 40)
    box('MAF_Sensor', (0.035, 0.05, 0.035), maf + Vector((0, 0, 0.062)), mat=M['Connector_Grey'], cname='Intake',
        bevel=0.005)
    box('MAP_Sensor', (0.035, 0.035, 0.025), (0, -0.23, 0.47), mat=M['Connector_Grey'], cname='Intake', bevel=0.005)
    # fuel rails + 8 port injectors aimed at the intake valves
    for side in 'LR':
        s = -1 if side == 'L' else 1
        ys = [c['y'] for c in A.CYL.values() if c['side'] == side]
        rail_pts = []
        for n, c in A.CYL.items():
            if c['side'] != side:
                continue
            port = A.bp(side, 0.300, -0.112, c['y'])
            dirv = Vector((-s * 0.42, 0, 0.91)).normalized()
            tip = port + Vector((-s * 0.012, 0, 0.032))
            top = tip + dirv * 0.075
            along(f'Injector_{n}', tip, tip + dirv * 0.06, 0.009, M['Injector_Body'], 'Intake', 20)
            along(f'InjectorSeal_{n}', tip + dirv * 0.005, tip + dirv * 0.012, 0.0105, M['Injector_Seal'], 'Intake', 20)
            box(f'InjectorPlug_{n}', (0.02, 0.022, 0.016), tip + dirv * 0.045 + Vector((s * 0.018, 0, 0)),
                mat=M['Connector_Grey'], cname='Intake', bevel=0.003)
            # spray cone: origin at tip, -Z of local axis points into the port toward the valve
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.016, radius2=0.0015, depth=0.05,
                                            location=(0, 0, 0))
            sp = bpy.context.active_object
            sp.data.transform(Matrix.Translation((0, 0, -0.025)))
            finish(sp, f'Spray_{n}', M['Spray_Fuel'], 'Effects')
            sp.location = tip
            sp.rotation_mode = 'QUATERNION'
            sp.rotation_quaternion = (-(port - Vector((0, 0, 0.01)) - tip).normalized() * -1).to_track_quat('-Z', 'Y')
            sp['rest_scale'] = 1.0
            rail_pts.append(top)
        rail_pts.sort(key=lambda v: -v.y)
        a, b = rail_pts[0] + Vector((0, 0.05, 0)), rail_pts[-1] + Vector((0, -0.05, 0))
        along(f'FuelRail_{side}', a, b, 0.011, M['Polished_Steel'], 'Intake', 24)
    tube('FuelCrossover', [(-0.15, -0.24, 0.38), (0, -0.30, 0.44), (0.15, -0.24, 0.38)], 0.005, M['Polished_Steel'],
         'Intake')


def exhaust_points(n):
    c = A.CYL[n]; side = c['side']
    port = A.bp(side, 0.272, 0.112, c['y'])
    coll_pt = A.bp(side, 0.235, 0.205, c['y'] * 0.85 - 0.02)
    return [port, A.bp(side, 0.265, 0.165, c['y']), coll_pt]


def downpipe_points(side):
    s = -1 if side == 'L' else 1
    start = A.bp(side, 0.22, 0.215, -0.10)
    return [start, start + Vector((s * 0.03, -0.04, -0.12)), Vector((s * 0.33, -0.28, -0.20)),
            Vector((s * 0.30, -0.45, -0.24))]


def o2_location(side):
    s = -1 if side == 'L' else 1
    return downpipe_points(side)[1] + Vector((s * 0.005, -0.02, -0.03))


def build_exhaust():
    me = M['Exhaust_CastIron']
    for side in 'LR':
        s = -1 if side == 'L' else 1
        for n, c in A.CYL.items():
            if c['side'] == side:
                tube(f'Primary_{n}', exhaust_points(n), 0.021, me, 'Exhaust')
        ys = [c['y'] for c in A.CYL.values() if c['side'] == side]
        front = A.bp(side, 0.235, 0.205, max(ys) * 0.85 - 0.02)
        rear = A.bp(side, 0.22, 0.215, -0.10)
        tube(f'Log_{side}', [front + Vector((0, 0.02, 0)), (front + rear) / 2, rear], 0.03, me, 'Exhaust')
        tube(f'Downpipe_{side}', downpipe_points(side), 0.03, me, 'Exhaust')
        # upstream O2 sensor (Bank 1 Sensor 1 = left/odd bank, Bank 2 Sensor 1 = right)
        p = o2_location(side)
        out = Vector((s, 0, 0.35)).normalized()
        along(f'O2_Sensor_{side}', p, p + out * 0.06, 0.011, M['Polished_Steel'], 'Sensors', 6)
        along(f'O2_Boss_{side}', p - out * 0.005, p + out * 0.015, 0.015, M['Polished_Steel'], 'Sensors', 6)
        sphere(f'O2_Tip_{side}', 0.009, p - out * 0.012, M['O2_Tip'], 'Sensors', 12)
        tube(f'O2_Lead_{side}', [p + out * 0.06, p + out * 0.11 + Vector((0, 0.03, 0.04)),
                                  p + out * 0.13 + Vector((0, 0.10, 0.12))], 0.004, M['Rubber'], 'Sensors', res=3)
    # crank position sensor (58X reluctor) - simplified location on lower block side
    cyl('CKP_Sensor', 0.011, 0.04, (0.205, -0.20, -0.06), (0, math.pi / 2, 0), M['Connector_Grey'], 'Sensors', 12)


def build_ecu():
    """Generic GM-style (E38/E67-like) engine control module - original geometry, no logos."""
    base = Vector((-0.78, 0.74, 0.50))
    rot = (math.radians(-70), 0, math.radians(35))
    parts = [box('ecu', (0.24, 0.20, 0.045), (0, 0, 0), mat=M['ECU_Case'], cname='ECU', bevel=0.008, seg=3)]
    for i in range(9):
        parts.append(box('ecu', (0.006, 0.17, 0.014), (-0.10 + i * 0.025, 0.0, 0.029), mat=M['ECU_Case'], cname='ECU',
                         bevel=0.002))
    parts.append(box('ecu', (0.075, 0.04, 0.05), (-0.05, -0.115, 0.0), mat=M['ECU_Connector_Blue'], cname='ECU',
                     bevel=0.005))
    parts.append(box('ecu', (0.075, 0.04, 0.05), (0.05, -0.115, 0.0), mat=M['ECU_Connector_Grey'], cname='ECU',
                     bevel=0.005))
    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in parts)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join(); ecu = bpy.context.active_object; ecu.name = 'ECU'
    ecu.location = base; ecu.rotation_euler = rot
    led = sphere('ECU_LED', 0.006, (0.10, 0.08, 0.026), M['ECU_LED'], 'ECU', 8)
    led.parent = ecu
    return ecu


def ecu_port(ecu, k):
    """world location of the ECU harness exit (k=0 blue, 1 grey)."""
    mw = ecu.matrix_world
    return mw @ Vector((-0.05 + 0.1 * k, -0.15, 0.0))


def sensor_points():
    tb = Vector((0, 0.255, 0.415))
    return {
        'MAF': tb + Vector((0, 0.27, 0.03)) + Vector((0, 0, 0.08)),
        'MAP': Vector((0, -0.23, 0.49)),
        'ECT': A.bp('L', 0.27, -0.05, 0.30) + Vector((0, 0.04, 0)),
        'TPS': tb + Vector((-0.075, 0, 0)),
        'CKP': Vector((0.23, -0.20, -0.06)),
        'O2_L': o2_location('L') + Vector((-1, 0, 0.35)).normalized() * 0.13 + Vector((0, 0.10, 0.12)),
        'O2_R': o2_location('R') + Vector((1, 0, 0.35)).normalized() * 0.13 + Vector((0, 0.10, 0.12)),
        'RAIL_L': Vector((-0.155, 0.25, 0.40)),
        'RAIL_R': Vector((0.155, 0.25, 0.40)),
    }


def wire_path(a, b, lift=0.25, n=40):
    """smooth arc from a to b (quadratic bezier lifted above both ends)."""
    a, b = Vector(a), Vector(b)
    mid = (a + b) / 2 + Vector((0, 0.05, lift))
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append(a * (1 - t) ** 2 + mid * 2 * t * (1 - t) + b * t * t)
    return pts


WIRES = {}


def build_wires(ecu):
    sp = sensor_points()
    defs = {
        'MAF': (sp['MAF'], ecu_port(ecu, 0), 0.25),
        'TPS': (sp['TPS'], ecu_port(ecu, 0), 0.18),
        'ECT': (sp['ECT'], ecu_port(ecu, 0), 0.12),
        'MAP': (sp['MAP'], ecu_port(ecu, 0), 0.35),
        'CKP': (sp['CKP'], ecu_port(ecu, 1), 0.30),
        'O2_L': (sp['O2_L'], ecu_port(ecu, 1), 0.10),
        'O2_R': (sp['O2_R'], ecu_port(ecu, 1), 0.45),
        'INJ_L': (ecu_port(ecu, 1), sp['RAIL_L'], 0.15),
        'INJ_R': (ecu_port(ecu, 1), sp['RAIL_R'], 0.30),
    }
    for name, (a, b, lift) in defs.items():
        pts = wire_path(a, b, lift)
        m = emis_mat(f'Wire_{name}', (0.5, 0.5, 0.5), 0.0)
        # wire = dark sheath + emissive core: use a mix in one material via principled emission
        mm = make_mat(f'WireSheath_{name}', (0.02, 0.02, 0.025), 0.0, 0.4, emit=(1, 1, 1), strength=0.0)
        tube(f'Wire_{name}', [tuple(p) for p in pts], 0.0024, mm, 'Signals', res=3, smooth_pts=False)
        WIRES[name] = [tuple(p) for p in pts]
        for k in range(4):
            sphere(f'Pulse_{name}_{k}', 0.0075, pts[0], m, 'Signals', 10)
    return WIRES


def build_particles():
    air = M['Air_Particle']; exh = M['Exhaust_Particle']
    base_air = sphere('AirParticleProto', 0.0065, (0, 0, -5), air, 'Effects', 8)
    base_exh = sphere('ExhParticleProto', 0.008, (0, 0, -5), exh, 'Effects', 8)
    for n in A.CYL:
        for k in range(9):
            o = bpy.data.objects.new(f'Air_{n}_{k}', base_air.data); coll('Effects').objects.link(o)
        for k in range(7):
            o = bpy.data.objects.new(f'Exh_{n}_{k}', base_exh.data); coll('Effects').objects.link(o)


def build_fuel_map():
    """3D fuel table surface (RPM x load -> commanded fuel), generic shape, no real calibration values."""
    N = 22
    me = bpy.data.meshes.new('FuelMap')
    verts, faces, h = [], [], []
    for i in range(N):
        for j in range(N):
            x, y = i / (N - 1), j / (N - 1)
            z = 0.15 + 0.65 * y ** 1.15 * (0.85 + 0.25 * math.sin(math.pi * (0.2 + 0.7 * x))) + 0.08 * (1 - x) * (1 - y)
            verts.append(((x - 0.5) * 0.5, (y - 0.5) * 0.5, z * 0.28)); h.append(min(1, z))
    for i in range(N - 1):
        for j in range(N - 1):
            a = i * N + j
            faces.append((a, a + N, a + N + 1, a + 1))
    me.from_pydata(verts, [], faces)
    attr = me.attributes.new('height', 'FLOAT', 'POINT')
    for k, v in enumerate(h):
        attr.data[k].value = v
    o = bpy.data.objects.new('FuelMap', me); coll('FuelMap').objects.link(o)
    me.materials.append(M['FuelMap_Surface'])
    for p in me.polygons:
        p.use_smooth = True
    g = bpy.data.objects.new('FuelMapGrid', me.copy()); coll('FuelMap').objects.link(g)
    g.data.materials.clear(); g.data.materials.append(M['Map_Grid'])
    w = g.modifiers.new('wire', 'WIREFRAME'); w.thickness = 0.0025; w.offset = 1
    g.parent = o
    box('FuelMapBase', (0.52, 0.52, 0.006), (0, 0, -0.004), mat=M['Pedestal'], cname='FuelMap').parent = o
    for i, (p0, p1) in enumerate((((-0.26, -0.26, 0), (0.28, -0.26, 0)), ((-0.26, -0.26, 0), (-0.26, 0.28, 0)),
                                  ((-0.26, -0.26, 0), (-0.26, -0.26, 0.28)))):
        along(f'FuelMapAxis_{i}', p0, p1, 0.003, M['Map_Grid'], 'FuelMap', 8).parent = o
    mk = sphere('FuelMapMarker', 0.014, (0, 0, 0), M['Map_Marker'], 'FuelMap', 12); mk.parent = o
    o.location = (1.0, 0.1, 0.16)
    o.scale = (1.35, 1.35, 1.35)
    o.rotation_euler = (math.radians(14), 0, math.radians(-28))
    return o


def build_studio():
    s = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -0.45))
    finish(bpy.context.active_object, 'Floor', M['Floor'], 'Studio')
    # curved cyclorama
    me = bpy.data.meshes.new('Cyc')
    faces = []
    verts = []
    for i, a in enumerate(range(0, 91, 10)):
        y = -3.0 - 2.4 * math.sin(math.radians(a))
        z = -0.45 + 2.4 * (1 - math.cos(math.radians(a)))
        verts += [(-12, y, z), (12, y, z)]
    verts += [(-12, -5.4, 8), (12, -5.4, 8)]
    for i in range(len(verts) // 2 - 1):
        faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    me.from_pydata(verts, [], faces)
    o = bpy.data.objects.new('Cyclorama', me); coll('Studio').objects.link(o); me.materials.append(M['Backdrop'])
    cyl('Pedestal', 0.62, 0.12, (0, -0.02, -0.39), mat=M['Pedestal'], cname='Studio', verts=96, bevel=0.01)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.62, minor_radius=0.006, major_segments=128, minor_segments=8,
                                     location=(0, -0.02, -0.33))
    finish(bpy.context.active_object, 'PedestalRing', M['Pedestal_Ring'], 'Studio')
    # engine support stands (engine "floats" on two short posts)
    for x in (-0.12, 0.12):
        cyl('Stand', 0.03, 0.06, (x, 0.0, -0.31), mat=M['Pedestal'], cname='Studio', verts=24)

    def area(name, loc, rot, energy, size, size_y=None, color=(1, 1, 1)):
        L = bpy.data.lights.new(name, 'AREA'); L.energy = energy; L.color = color
        if size_y:
            L.shape = 'RECTANGLE'; L.size = size; L.size_y = size_y
        else:
            L.size = size
        o = bpy.data.objects.new(name, L); coll('Lights').objects.link(o)
        o.location = loc; o.rotation_euler = rot
        o['base_energy'] = energy
        return o

    area('Key', (-1.6, 1.8, 2.4), (math.radians(-40), math.radians(-30), math.radians(-40)), 380, 1.6,
         color=(1.0, 0.97, 0.93))
    area('Fill', (2.2, 1.6, 0.9), (math.radians(-75), 0, math.radians(55)), 120, 2.0, color=(0.85, 0.9, 1.0))
    area('RimL', (-1.7, -1.6, 1.4), (math.radians(55), math.radians(-35), 0), 420, 2.4, 0.18, (1, 1, 1))
    area('RimR', (1.7, -1.6, 1.4), (math.radians(55), math.radians(35), 0), 420, 2.4, 0.18, (1, 1, 1))
    area('Top', (0, 0, 2.6), (0, 0, 0), 110, 1.2, 2.0)
    area('AccentL', (-1.5, 0.4, 0.1), (0, math.radians(-90), 0), 0, 1.0, 0.5, (1, 0.35, 0.05))
    area('AccentR', (1.5, 0.2, 0.1), (0, math.radians(90), 0), 0, 1.0, 0.5, (1, 0.35, 0.05))
    area('Under', (0, 0.6, -0.30), (math.radians(180), 0, 0), 0, 0.8, 0.3, (1, 0.35, 0.05))
    # world
    w = bpy.data.worlds.new('StudioWorld'); s.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = w.node_tree.nodes.get('Background')
    bg.inputs[0].default_value = (0.004, 0.005, 0.007, 1); bg.inputs[1].default_value = 1.0


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials()
    build_block()
    build_heads()
    crank, cam = build_internals()
    build_intake()
    build_exhaust()
    ecu = build_ecu()
    build_wires(ecu)
    build_particles()
    build_fuel_map()
    build_studio()
    # store wire paths & particle paths on the scene for the runtime animator
    import json
    paths = {'wires': WIRES,
             'air': {str(n): [tuple(p) for p in sample_air_path(n)] for n in A.CYL},
             'exh': {str(n): [tuple(p) for p in sample_exh_path(n)] for n in A.CYL},
             'anchors': {k: tuple(v) for k, v in sensor_points().items()}}
    paths['anchors'].update({'ECU': tuple(bpy.data.objects['ECU'].location),
                             'O2_L_tip': tuple(o2_location('L')), 'O2_R_tip': tuple(o2_location('R')),
                             'ThrottleBody': (0, 0.255, 0.415), 'FuelMap': tuple(bpy.data.objects['FuelMap'].location),
                             'Injector_1': tuple(bpy.data.objects['Injector_1'].location),
                             'Injector_2': tuple(bpy.data.objects['Injector_2'].location),
                             'Cyl_1': tuple(A.bp('L', 0.2, 0, A.CYL[1]['y'])),
                             'Cyl_3': tuple(A.bp('L', 0.2, 0, A.CYL[3]['y'])),
                             'Plenum': (0, -0.02, 0.46), 'Crank': (0, 0.2, -0.02)})
    t = bpy.data.texts.new('ls_paths.json'); t.write(json.dumps(paths))
    return paths


def polyline_resample(pts, n):
    pts = [Vector(p) for p in pts]
    L = [0.0]
    for a, b in zip(pts, pts[1:]):
        L.append(L[-1] + (b - a).length)
    out = []
    for i in range(n):
        s = L[-1] * i / (n - 1)
        for k in range(len(L) - 1):
            if L[k + 1] >= s:
                f = (s - L[k]) / max(1e-9, L[k + 1] - L[k])
                out.append(pts[k].lerp(pts[k + 1], f)); break
    return out


def bez(pts, n=60):
    """Catmull-Rom through points -> dense polyline"""
    P = [Vector(p) for p in pts]
    P = [P[0]] + P + [P[-1]]
    out = []
    for i in range(1, len(P) - 2):
        for k in range(12):
            t = k / 12
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return polyline_resample(out, n)


def sample_air_path(n):
    tb = Vector((0, 0.255, 0.415))
    c = A.CYL[n]
    rp = runner_points(n)[::-1]          # plenum -> port
    port = rp[-1]
    valve = A.bp(c['side'], A.DECK + 0.01, 0.0, c['y'] + 0.021)
    pts = [tb + Vector((0, 0.30, 0.03)), tb + Vector((0, 0.1, 0)), tb, Vector((0, c['y'] * 0.5 + 0.05, 0.42))] + rp[1:] + \
          [valve]
    return bez(pts, 60)


def sample_exh_path(n):
    c = A.CYL[n]; side = c['side']
    ex_valve = A.bp(side, A.DECK + 0.01, 0.0, c['y'] - 0.021)
    pts = [ex_valve] + exhaust_points(n) + [A.bp(side, 0.22, 0.215, -0.10)] + downpipe_points(side)[1:]
    return bez(pts, 60)


if __name__ == '__main__':
    build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine_only_test.blend')
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print('saved', out)
