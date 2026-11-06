"""Small structures, isolated spikes, bin boundaries and threshold behavior."""
import unittest
import numpy as np
from spatial_grid import filter_depth_measurements,build_nested_grid,NestedGridParams,aggregate_fine_states


class NoiseAndSmallObjectTests(unittest.TestCase):
    def test_single_unsupported_depth_spike_removed_without_filling(self):
        depth=np.full((15,15),2.,dtype=np.float32)
        depth[7,7]=1.2
        result=filter_depth_measurements(depth)
        self.assertTrue(result['rejected'][7,7])
        self.assertFalse(result['valid'][7,7])
        self.assertEqual(depth[7,7],np.float32(1.2))
        self.assertEqual(int(result['rejected'].sum()),1)

    def test_one_pixel_wide_continuous_pole_is_kept(self):
        depth=np.full((15,15),2.,dtype=np.float32)
        depth[3:12,7]=1.2
        result=filter_depth_measurements(depth)
        self.assertTrue(result['valid'][3:12,7].all())

    def test_two_by_two_small_surface_is_kept(self):
        depth=np.full((15,15),2.,dtype=np.float32)
        depth[6:8,6:8]=1.2
        result=filter_depth_measurements(depth)
        self.assertTrue(result['valid'][6:8,6:8].all())

    def test_invalid_neighborhood_cannot_support_spike(self):
        depth=np.zeros((9,9),dtype=np.float32)
        depth[4,4]=1.5
        result=filter_depth_measurements(depth)
        self.assertFalse(result['valid'].any())

    def test_smooth_depth_gradient_survives(self):
        depth=np.tile(np.linspace(1.,1.03,15,dtype=np.float32),(15,1))
        self.assertTrue(filter_depth_measurements(depth)['valid'].all())


class NestedGridTests(unittest.TestCase):
    def floor_points(self):
        x,y=np.meshgrid([-.15,-.05,.05,.15],[1.05,1.15,1.25,1.35])
        return np.column_stack([x.ravel(),y.ravel(),np.zeros(16)])

    def test_only_floor_yields_no_obstacle_subcells(self):
        result=build_nested_grid(self.floor_points())
        self.assertEqual(result['coarse_obstacle_subcells'][5,4],0)
        self.assertEqual(result['coarse_free_subcells'][5,4],16)
        self.assertEqual(result['grid'][5,4],0)

    def test_many_pixels_in_one_small_cell_count_once(self):
        points=np.concatenate([self.floor_points(),np.repeat([[.05,1.15,.3]],1000,axis=0)])
        result=build_nested_grid(points)
        self.assertEqual(result['coarse_obstacle_subcells'][5,4],1)
        self.assertEqual(result['coarse_free_subcells'][5,4],15)
        self.assertEqual(result['grid'][5,4],1)

    def test_coarse_threshold_does_not_erase_small_obstacle_as_free(self):
        points=np.concatenate([self.floor_points(),[[.05,1.15,.3]]])
        result=build_nested_grid(points,NestedGridParams(coarse_min_obstacle_subcells=2))
        self.assertEqual(result['coarse_obstacle_subcells'][5,4],1)
        self.assertEqual(result['grid'][5,4],2)
        self.assertTrue(result['small_obstacle_present'][5,4])

    def test_supported_surface_across_small_cell_boundary_is_not_lost(self):
        result=build_nested_grid(np.array([[.099,1.15,.3],[.101,1.15,.3]]))
        self.assertEqual(result['coarse_obstacle_subcells'][5,4],2)

    def test_unknown_subcells_are_not_assumed_empty(self):
        result=build_nested_grid(np.array([[.05,1.15,0.]]))
        self.assertEqual(result['coarse_unknown_subcells'][5,4],15)
        self.assertEqual(result['grid'][5,4],2)

    def test_fine_counts_conserve_all_16_subcells(self):
        result=build_nested_grid(np.concatenate([self.floor_points(),[[.05,1.15,.3]]]))
        total=result['coarse_obstacle_subcells']+result['coarse_free_subcells']+result['coarse_unknown_subcells']
        np.testing.assert_array_equal(total,np.full((6,9),16))


if __name__=='__main__':unittest.main()
