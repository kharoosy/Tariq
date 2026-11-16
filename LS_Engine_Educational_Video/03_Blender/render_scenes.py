"""Resume-capable frame renderer.

  python3 03_Blender/render_scenes.py --frames 0-3599 [--step 1] [--pass main|s8a|s8b] [--res 1920x1080]
                                      [--samples 16] [--out DIR]

* Loads LS_Engine_Master.blend, poses every element with animate_engine.apply_frame(), renders
  each frame to <out>/<pass>/f_####.png and writes projected label anchors to <out>/anchors/.
* Existing frames are skipped -> a killed job can simply be restarted.
* Pass s8a / s8b render scene 8 (split screen) in forced Open-Loop / Closed-Loop state at half
  width (centre crop of the same camera, sensor_fit = VERTICAL keeps the field of view identical).
"""
import os, sys, json, time, argparse
import bpy
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import animate_engine as A

ap = argparse.ArgumentParser()
ap.add_argument('--frames', default='0-3599')
ap.add_argument('--step', type=int, default=1)
ap.add_argument('--pass', dest='pss', default='main')
ap.add_argument('--res', default=None)
ap.add_argument('--samples', type=int, default=None)
ap.add_argument('--out', default=os.path.join(ROOT, '06_Rendered_Scenes', 'frames'))
ap.add_argument('--threads', type=int, default=0)
args = ap.parse_args([a for a in sys.argv[1:] if a != '--'])

bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, 'LS_Engine_Master.blend'))
scene = bpy.context.scene
# the camera path is driven by apply_frame directly; drop baked keys so they cannot fight it
if scene.camera.animation_data:
    scene.camera.animation_data_clear()
    scene.camera.data.animation_data_clear()
if args.res:
    w, h = map(int, args.res.split('x'))
    scene.render.resolution_x, scene.render.resolution_y = w, h
if args.samples:
    scene.cycles.samples = args.samples
if args.threads:
    scene.render.threads_mode = 'FIXED'; scene.render.threads = args.threads
force = None
if args.pss in ('s8a', 's8b'):
    force = 0.0 if args.pss == 's8a' else 1.0
    scene.render.resolution_x //= 2
a, b = map(int, args.frames.split('-'))
od = os.path.join(args.out, args.pss); os.makedirs(od, exist_ok=True)
ad = os.path.join(args.out, 'anchors'); os.makedirs(ad, exist_ok=True)
log = open(os.path.join(ROOT, '08_QA', f'render_log_{args.pss}.txt'), 'a')
for f in range(a, b + 1, args.step):
    fn = os.path.join(od, f'f_{f:04d}.png')
    if os.path.exists(fn) and os.path.getsize(fn) > 1000:
        continue
    t0 = time.time()
    scene.frame_set(f)
    e = A.apply_frame(scene, f, force)
    if args.pss == 'main':
        json.dump(A.anchors_2d(scene), open(os.path.join(ad, f'f_{f:04d}.json'), 'w'))
    scene.render.filepath = fn + '.tmp.png'
    bpy.ops.render.render(write_still=True)
    os.replace(fn + '.tmp.png', fn)
    msg = f'{args.pss} frame {f} {time.time() - t0:.1f}s'
    print(msg, flush=True); log.write(msg + '\n'); log.flush()
