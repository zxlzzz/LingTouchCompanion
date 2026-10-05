"""Exact directional skin queries on the unchanged, registered head triangles.

Units are mm. X is lateral, +Y posterior, +Z superior. The actual head surface
is queried without dilation or an added clearance. Requires NumPy and VTK.
"""
from pathlib import Path
from functools import lru_cache
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray


class HeadSurface:
    def __init__(self, path=None):
        self.path=Path(path) if path is not None else Path(__file__).with_name('Medium_Trial_Registered.npz')
        source=np.load(self.path)
        self.vertices=np.asarray(source['v'],dtype=np.float64)
        self.faces=np.asarray(source['f'],dtype=np.int64)
        self.bounds=np.array([self.vertices.min(0),self.vertices.max(0)])
        points=vtk.vtkPoints()
        points.SetData(numpy_to_vtk(np.ascontiguousarray(self.vertices),deep=True))
        cells=vtk.vtkCellArray()
        cells.SetData(
            numpy_to_vtkIdTypeArray(np.arange(0,3*len(self.faces)+1,3,dtype=np.int64),deep=True),
            numpy_to_vtkIdTypeArray(np.ascontiguousarray(self.faces.ravel()),deep=True))
        self.polydata=vtk.vtkPolyData()
        self.polydata.SetPoints(points)
        self.polydata.SetPolys(cells)
        self.locator=vtk.vtkStaticCellLocator()
        self.locator.SetDataSet(self.polydata)
        self.locator.BuildLocator()
        self._t=vtk.mutable(0.)
        self._subid=vtk.mutable(0)
        self._cellid=vtk.mutable(0)
        self._point=[0.,0.,0.]
        self._pcoords=[0.,0.,0.]
        self._cell=vtk.vtkGenericCell()

    def first_hit(self, start, end):
        """Return the first true triangle intersection, or None when no hit."""
        result=self.locator.IntersectWithLine(
            tuple(float(x) for x in start),tuple(float(x) for x in end),1e-8,
            self._t,self._point,self._pcoords,self._subid,self._cellid,self._cell)
        return np.array(self._point,dtype=float) if result else None

    def front_y(self, x, z):
        """First skin Y seen from anterior along +Y; NaN outside the head."""
        x=float(x);z=float(z)
        if not (self.bounds[0,0]-1e-8<=x<=self.bounds[1,0]+1e-8 and
                self.bounds[0,2]-1e-8<=z<=self.bounds[1,2]+1e-8):return float('nan')
        hit=self.first_hit([x,self.bounds[0,1]-100,z],[x,self.bounds[1,1]+100,z])
        return float(hit[1]) if hit is not None else float('nan')

    def lateral_x(self, y, z, side):
        """First exterior skin X from the chosen side (-1 left / +1 right)."""
        y=float(y);z=float(z)
        if side in ('left','L','-'):side=-1
        elif side in ('right','R','+'):side=1
        if side not in (-1,1):raise ValueError('side must be -1/left or +1/right')
        if not (self.bounds[0,1]-1e-8<=y<=self.bounds[1,1]+1e-8 and
                self.bounds[0,2]-1e-8<=z<=self.bounds[1,2]+1e-8):return float('nan')
        lo=self.bounds[0,0]-100;hi=self.bounds[1,0]+100
        hit=self.first_hit([lo if side<0 else hi,y,z],[hi if side<0 else lo,y,z])
        return float(hit[0]) if hit is not None else float('nan')

    def front_grid(self, xs, zs, missing=np.nan):
        """Y map indexed [X index, Z index], preserving caller grid samples."""
        xs=np.asarray(xs,dtype=float);zs=np.asarray(zs,dtype=float)
        result=np.empty((len(xs),len(zs)),dtype=float)
        for ix,x in enumerate(xs):
            for iz,z in enumerate(zs):
                y=self.front_y(x,z)
                result[ix,iz]=y if np.isfinite(y) else missing
        return result

    def lateral_grid(self, ys, zs, side, missing=np.nan):
        """X map indexed [Y index, Z index] for one exterior lateral side."""
        ys=np.asarray(ys,dtype=float);zs=np.asarray(zs,dtype=float)
        result=np.empty((len(ys),len(zs)),dtype=float)
        for iy,y in enumerate(ys):
            for iz,z in enumerate(zs):
                x=self.lateral_x(y,z,side)
                result[iy,iz]=x if np.isfinite(x) else missing
        return result


@lru_cache(maxsize=1)
def get_surface():return HeadSurface()

def front_y(x,z):return get_surface().front_y(x,z)
def lateral_x(y,z,side):return get_surface().lateral_x(y,z,side)
def front_grid(xs,zs,missing=np.nan):return get_surface().front_grid(xs,zs,missing)
def lateral_grid(ys,zs,side,missing=np.nan):return get_surface().lateral_grid(ys,zs,side,missing)
