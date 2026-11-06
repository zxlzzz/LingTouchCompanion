"""Measurement-level depth filtering and nested 10cm -> 40cm evidence grids."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class DepthFilterParams:
    min_depth_m: float = .1
    max_depth_m: float = 5.
    absolute_tolerance_m: float = .02
    relative_tolerance: float = .01
    min_consistent_neighbors: int = 1


@dataclass(frozen=True)
class NestedGridParams:
    height_min_m: float = .1
    height_max_m: float = 1.9
    ground_tolerance_m: float = .05
    fine_min_supported_points: int = 1
    coarse_min_obstacle_subcells: int = 1


def filter_depth_measurements(depth, params=DepthFilterParams()):
    """Reject unsupported 3x3 depth jumps; do not fill or smooth rejected pixels.

    A thin surface can be supported along either direction. No connected-component
    size cutoff is used. Coherent artifacts can still pass a single-frame test.
    """
    depth=np.asarray(depth)
    if depth.ndim != 2:
        raise ValueError('Depth must be a 2D numeric image')
    if not 0<=params.min_consistent_neighbors<=8:
        raise ValueError('Neighbor support must be between 0 and 8')
    if params.absolute_tolerance_m<0 or params.relative_tolerance<0:
        raise ValueError('Depth tolerances must be nonnegative')
    raw_valid=np.isfinite(depth)&(depth>=params.min_depth_m)&(depth<=params.max_depth_m)
    supported=np.zeros(depth.shape,dtype=np.uint8)
    h,w=depth.shape
    safe=np.where(raw_valid,depth,0).astype(np.float32)
    for dy in [-1,0,1]:
        for dx in [-1,0,1]:
            if not dx and not dy:
                continue
            y0,y1=max(0,-dy),min(h,h-dy)
            x0,x1=max(0,-dx),min(w,w-dx)
            center=safe[y0:y1,x0:x1]
            neighbor=safe[y0+dy:y1+dy,x0+dx:x1+dx]
            # Symmetric tolerance gives the same support relation in both directions.
            tolerance=np.maximum(params.absolute_tolerance_m,params.relative_tolerance*np.minimum(center,neighbor))
            consistent=(raw_valid[y0:y1,x0:x1]&raw_valid[y0+dy:y1+dy,x0+dx:x1+dx]
                        &(np.abs(center-neighbor)<=tolerance))
            supported[y0:y1,x0:x1]+=consistent.astype(np.uint8)
    valid=raw_valid&(supported>=params.min_consistent_neighbors)
    return {'raw_valid':raw_valid,'valid':valid,'rejected':raw_valid&~valid,'consistent_neighbors':supported}


def aggregate_fine_states(fine_states, threshold=1):
    if np.shape(fine_states)!=(24,36) or not np.isin(fine_states,[0,1,2]).all():
        raise ValueError('Fine states must be 24x36 values in {0,1,2}, far row first')
    if not 1<=threshold<=16:
        raise ValueError('Coarse threshold must be in 1..16')
    blocks=np.asarray(fine_states).reshape(6,4,9,4)
    occupied=(blocks==1).sum(axis=(1,3))
    free=(blocks==0).sum(axis=(1,3))
    unknown=(blocks==2).sum(axis=(1,3))
    grid=np.full((6,9),2,dtype=np.uint8)
    grid[(occupied==0)&(free==16)]=0
    grid[occupied>=threshold]=1
    # Existing small obstacles are never made free by a higher coarse threshold.
    small=(occupied>0)&(occupied<threshold)
    return {'grid':grid,'coarse_obstacle_subcells':occupied,'coarse_free_subcells':free,
            'coarse_unknown_subcells':unknown,'small_obstacle_present':small}


def build_nested_grid(points, params=NestedGridParams()):
    """Input must already contain quality-filtered, ground-frame measured points.

    One accepted point can occupy a 10cm cell: measurement support was checked
    before binning. Splitting a tiny supported surface across a cell boundary
    must not erase it via a second arbitrary area/point-count cutoff.
    """
    if params.fine_min_supported_points<1:
        raise ValueError('Fine-cell support must be positive')
    p=np.asarray(points,dtype=np.float64)
    if p.ndim!=2 or p.shape[1]!=3:
        raise ValueError('Expected Nx3 ground-frame points')
    p=p[np.isfinite(p).all(axis=1)]
    inside=(p[:,0]>=-1.8)&(p[:,0]<1.8)&(p[:,1]>=1)&(p[:,1]<3.4)
    p=p[inside]
    sx=np.floor((p[:,0]+1.8)/.1).astype(int)
    sy=np.floor((p[:,1]-1)/.1).astype(int)
    good=(sx>=0)&(sx<36)&(sy>=0)&(sy<24)
    sx,sy,p=sx[good],sy[good],p[good]
    obstacle=(p[:,2]>=params.height_min_m)&(p[:,2]<=params.height_max_m)
    floor=np.abs(p[:,2])<=params.ground_tolerance_m
    hits=np.zeros((24,36),dtype=np.int32)
    ground_hits=np.zeros_like(hits)
    np.add.at(hits,(sy[obstacle],sx[obstacle]),1)
    np.add.at(ground_hits,(sy[floor],sx[floor]),1)
    states=np.full((24,36),2,dtype=np.uint8)
    states[(hits==0)&(ground_hits>0)]=0
    states[hits>=params.fine_min_supported_points]=1
    states=states[::-1].copy()
    result=aggregate_fine_states(states,params.coarse_min_obstacle_subcells)
    result.update(fine_grid=states,fine_obstacle_hits=hits[::-1].copy(),fine_ground_hits=ground_hits[::-1].copy(),
                  band_hits=hits.reshape(6,4,9,4).sum(axis=(1,3))[::-1].copy(),
                  floor_subblocks=(ground_hits>0).reshape(6,4,9,4).sum(axis=(1,3))[::-1].copy())
    return result
