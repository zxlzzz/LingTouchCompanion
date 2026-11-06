"""Physical-coordinate and unknown-state checks for the RGB-D demo."""
import unittest
import numpy as np
from test_geometry import scene
from rgbd_floor_demo import geometry, fit_plane
from geometry import unproject


class RGBDFloorTests(unittest.TestCase):
    def test_floor_prior_keeps_box_and_metric_grid(self):
        k,depth=scene()
        xyz=unproject(depth,k)
        normal=np.array([0.,-np.cos(np.deg2rad(30)),-np.sin(np.deg2rad(30))])
        prior=(depth>0)&(np.abs(xyz@normal+1.25)<.02)
        result=geometry(depth,k,prior)
        self.assertIsNotNone(result['ground'],result['attempts'])
        self.assertEqual(result['ground_source'],'segformer_floor')
        self.assertAlmostEqual(result['ground']['height_m'],1.25,places=2)
        self.assertEqual(result['grid'][3,5],1)
        self.assertTrue(result['obstacle'].any())
        self.assertTrue((result['grid']==0).any())
        self.assertTrue((result['grid']==2).any())

    def test_missing_depth_stays_unknown(self):
        k,depth=scene()
        depth[:]=0
        depth[0,0]=np.nan
        result=geometry(depth,k,np.ones(depth.shape,dtype=bool))
        self.assertIsNone(result['ground'])
        self.assertTrue((result['grid']==2).all())
        self.assertFalse(result['obstacle'].any())

    def test_candidate_plane_must_pass_global_below_check(self):
        x,z=np.meshgrid(np.linspace(-1,1,40),np.linspace(1,3,40))
        plane=np.column_stack([x.ravel(),np.ones(x.size),z.ravel()])
        below=plane.copy()
        below[:,1]=1.5
        ground,status=fit_plane(plane,np.concatenate([plane,below]))
        self.assertIsNone(ground)
        self.assertIn('全图',status)

    def test_calibration_shape_mismatch_rejected(self):
        k,depth=scene()
        with self.assertRaises(ValueError):
            geometry(depth[:20],k,np.zeros(depth[:20].shape,dtype=bool))


if __name__=='__main__':
    unittest.main()
