"""table.refresh の所要時間を測る（約 2 万頂点・1000 頂点選択・50 グループ）。

実行: blender --background --factory-startup --python tests/blender_perf.py
"""

import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import si_weight_editor as siwe  # noqa: E402
from si_weight_editor import mesh_io, table  # noqa: E402

siwe.register()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=140, y_subdivisions=140, size=2)
obj = bpy.context.object
n = len(obj.data.vertices)
for g in range(50):
    vg = obj.vertex_groups.new(name=f"g{g:02d}")
    vg.add(list(range(g * 300 % n, min(g * 300 % n + 600, n))), 0.5, "REPLACE")
mesh_io.set_selected_vertices(obj, set(range(1000)))
for mode in ("OBJECT", "EDIT"):
    bpy.ops.object.mode_set(mode=mode)
    t = time.perf_counter()
    table.refresh(bpy.context)
    dt = time.perf_counter() - t
    s = bpy.context.window_manager.siwe
    print(f"PERF {mode}: verts={n} rows={len(s.rows)} cols={len(s.cols)} refresh={dt * 1000:.0f} ms")
siwe.unregister()

if "--profile" in sys.argv:
    import cProfile
    import pstats

    siwe.register()
    bpy.ops.object.mode_set(mode="EDIT")
    prof = cProfile.Profile()
    prof.runcall(table.refresh, bpy.context)
    pstats.Stats(prof).sort_stats("cumtime").print_stats(8)
