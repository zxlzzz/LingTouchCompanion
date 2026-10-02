"""25 mm ribbon geometry for the approved unchanged front and relocated rear slots.

The 0.8 mm outward extrusion is visualization thickness, not a measured elastic.
Free length excludes the portion supported on the front ear tab and slot tails.
"""
from pathlib import Path
import json
import numpy as np
import manifold3d as md

HERE = Path(__file__).resolve().parent
M = md.Manifold
ZLO, ZHI = 26.7, 51.7
THICKNESS = .8

def segment(p, q, outward):
    p, q, outward = np.array(p), np.array(q), np.array(outward)
    outward = outward / np.linalg.norm(outward) * THICKNESS
    vertices = np.array([[*p, ZLO], [*q, ZLO], [*(q+outward), ZLO],
                         [*(p+outward), ZLO], [*p, ZHI], [*q, ZHI],
                         [*(q+outward), ZHI], [*(p+outward), ZHI]])
    faces = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],
                      [0,1,5],[0,5,4],[1,2,6],[1,6,5],
                      [2,3,7],[2,7,6],[3,0,4],[3,4,7]])
    # Reflection across X can reverse orientation.
    volume = np.sum(np.einsum('ij,ij->i', vertices[faces[:,0]],
                            np.cross(vertices[faces[:,1]],vertices[faces[:,2]])))/6
    if volume < 0: faces = faces[:,::-1]
    return M(md.Mesh64(vert_properties=np.ascontiguousarray(vertices,dtype=np.float64),
                       tri_verts=np.ascontiguousarray(faces,dtype=np.uint64)))

def save(name, manifold):
    mesh=manifold.to_mesh64()
    np.savez_compressed(HERE/(name+'.npz'),v=np.asarray(mesh.vert_properties)[:,:3],f=np.asarray(mesh.tri_verts))

records = {}
all_parts, free_parts = [], []
paths = {}
for side, sign, xi, xo in [('left',-1,-67.8384247,-71.0974706),
                           ('right',1,67.6905112,71.1061337)]:
    a = np.array([xo,154.5703299])  # Last supporting edge of front slot.
    b = np.array([xo,159.0703299])  # Physical rear edge of front ear tab.
    c = np.array([sign*68.3,203.3]) # Front edge of rear slot at outside face.
    d = np.array([sign*65.3,203.3]) # Rear slot tail crosses the plate in the opening.
    direction = c-b
    outward = np.array([sign*direction[1],-sign*direction[0]])
    supported = segment(a,b,[sign,0])
    free = segment(b,c,outward)
    front_tail = segment([xi,154.5703299],a,[0,-1])
    rear_tail = segment(c,d,[0,1])
    parts = [front_tail,supported,free,rear_tail]
    for part in parts: assert part.status()==md.Error.NoError
    all_parts.extend(parts); free_parts.append(free)
    save(side+'_free_ribbon',free)
    paths[side] = np.array([[*p,39.2] for p in [a,b,c,d]])
    records[side] = {
        'front_slot_exit_xyz_mm':[*a,39.2],
        'free_start_xyz_mm':[*b,39.2],
        'free_end_xyz_mm':[*c,39.2],
        'free_centerline_length_mm':float(np.linalg.norm(c-b)),
        'front_supported_length_mm':float(np.linalg.norm(b-a)),
        'slot_to_slot_centerline_length_mm':float(np.linalg.norm(c-b)+np.linalg.norm(b-a)),
        'ribbon_width_mm':25., 'ribbon_z_limits_mm':[ZLO,ZHI],
        'front_arm_shortening_mm':0.,
        'target40to60_pass':40<=float(np.linalg.norm(c-b))<=60,
        'tail_length_not_included':True,
    }
save('straps_preview',M.batch_boolean(all_parts,md.OpType.Add))
save('free_straps_preview',M.batch_boolean(free_parts,md.OpType.Add))
np.savez_compressed(HERE/'strap_paths.npz',**paths)
report={'sides':records,'free_length_definition':'Straight suspended centerline from front-tab rear edge to rear-slot front edge; no supported ear-tab length or threading tails.',
        'geometric_25mm_width_checked':True,'elastic_actual_thickness_mm':'not checked',
        'visualization_outward_thickness_mm':THICKNESS,
        'fabric_bend_radius_and_unstretched_cut_length':'not checked; free length is worn-position geometry, not a cutting length'}
(HERE/'strap_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
