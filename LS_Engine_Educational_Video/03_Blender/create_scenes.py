"""Build the full production scene and save 03_Blender/LS_Engine_Master.blend.

  python3 03_Blender/create_scenes.py [--quality preview|final]

* builds the procedural engine/studio (build_engine.py)
* creates the camera (path from animate_engine.CAM_KEYS, baked as keyframes every 2 frames so the
  .blend can be scrubbed/edited in Blender), render settings, and a text block with the animator
"""
import os, sys, math
import bpy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_engine as B
import animate_engine as A

QUALITY = {
    'preview': dict(res=(640, 360), samples=2, threshold=0.1),
    'final': dict(res=(1280, 720), samples=4, threshold=0.05),
}


def setup_render(scene, q):
    r = scene.render
    r.engine = 'CYCLES'
    r.resolution_x, r.resolution_y = q['res']; r.resolution_percentage = 100
    r.fps = A.FPS
    scene.frame_start, scene.frame_end = 0, A.TOTAL_FRAMES - 1
    c = scene.cycles
    c.device = 'CPU'
    c.samples = q['samples']
    c.use_adaptive_sampling = True; c.adaptive_threshold = q['threshold']
    c.use_denoising = True
    try:
        c.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    c.max_bounces = 3; c.diffuse_bounces = 1; c.glossy_bounces = 1; c.transmission_bounces = 1
    c.transparent_max_bounces = 5; c.volume_bounces = 0
    try:
        c.denoising_quality = 'BALANCED'; c.denoising_prefilter = 'FAST'
    except Exception:
        pass
    # small emitters (particles, wires, x-ray rim glow) must not become light-tree lights: huge speed-up on CPU
    for m in bpy.data.materials:
        if m.name != 'Combustion':
            m.cycles.emission_sampling = 'NONE'
    c.caustics_reflective = False; c.caustics_refractive = False
    c.sample_clamp_indirect = 4.0
    c.use_light_tree = True
    r.use_persistent_data = True
    r.image_settings.file_format = 'PNG'; r.image_settings.color_depth = '8'
    vs = scene.view_settings
    vs.view_transform = 'AgX'
    for look in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            vs.look = look; break
        except Exception:
            pass
    vs.exposure = 0.15


def make_camera(scene):
    cd = bpy.data.cameras.new('CineCam')
    cd.sensor_fit = 'VERTICAL'; cd.sensor_height = 20.25      # = 36 mm horizontal at 16:9
    cd.clip_start = 0.02; cd.clip_end = 60
    cd.dof.use_dof = True; cd.dof.aperture_fstop = 5.6
    cam = bpy.data.objects.new('CineCam', cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for f in range(0, A.TOTAL_FRAMES, 2):
        loc, tgt, lens = A.camera_at(f / A.FPS)
        cam.location = loc
        cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
        cd.lens = lens
        cam.keyframe_insert('location', frame=f)
        cam.keyframe_insert('rotation_euler', frame=f)
        cd.keyframe_insert('lens', frame=f)
    return cam


def main():
    q = QUALITY['final']
    if '--quality' in sys.argv:
        q = QUALITY[sys.argv[sys.argv.index('--quality') + 1]]
    B.build()
    scene = bpy.context.scene
    setup_render(scene, q)
    make_camera(scene)
    # embed the animator so the .blend is self-contained (Text editor > Run Script registers the handler)
    t = bpy.data.texts.new('animate_engine.py')
    t.write(open(os.path.join(HERE, 'animate_engine.py')).read())
    t2 = bpy.data.texts.new('register_handler.py')
    t2.write("import bpy, sys, importlib\n"
             "mod = bpy.data.texts['animate_engine.py'].as_module()\n"
             "def _h(scene, *a):\n    mod.apply_frame(scene, scene.frame_current)\n"
             "bpy.app.handlers.frame_change_pre.clear()\nbpy.app.handlers.frame_change_pre.append(_h)\n")
    A.apply_frame(scene, 0)
    out = os.path.join(HERE, 'LS_Engine_Master.blend')
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print('saved', out)


if __name__ == '__main__':
    main()
