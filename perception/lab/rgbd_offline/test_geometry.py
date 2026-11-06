import unittest

import numpy as np

from geometry import Config, Intrinsics, process_depth


def scene():
    k = Intrinsics(160, 120, 150., 150., 79.5, 59.5)
    v, u = np.indices((k.height, k.width))
    pitch = np.deg2rad(30)
    camera_ray = np.stack(((u - k.cx) / k.fx, (v - k.cy) / k.fy, np.ones_like(u)), axis=-1)
    basis = np.array([[1, 0, 0], [0, -np.sin(pitch), -np.cos(pitch)], [0, np.cos(pitch), -np.sin(pitch)]])
    rays = camera_ray @ basis
    origin = np.array([0, 0, 1.25])
    with np.errstate(divide='ignore', invalid='ignore'):
        floor_t = -origin[2] / rays[..., 2]
        lower = (np.array([.25, 1.90, 0.]) - origin) / rays
        upper = (np.array([.55, 2.10, .60]) - origin) / rays
    near = np.minimum(lower, upper).max(axis=-1)
    far = np.maximum(lower, upper).min(axis=-1)
    hit = (far >= near) & (near > 0)
    depth = np.where(hit, np.minimum(near, floor_t), floor_t)
    depth[(depth <= 0) | (depth > 5)] = 0
    return k, depth.astype(np.float32)


class GeometryTests(unittest.TestCase):
    def test_physical_box_occupies_expected_cell(self):
        k, depth = scene()
        result = process_depth(depth, k, Config(stride=1))
        self.assertIsNotNone(result['ground'], result['status'])
        self.assertAlmostEqual(result['ground']['height_m'], 1.25, places=2)
        self.assertEqual(int(result['grid'][3, 5]), 1)
        # Some free ground and some unknown support must coexist in this view.
        self.assertTrue((result['grid'] == 0).any())
        self.assertTrue((result['grid'] == 2).any())

    def test_no_measurement_is_unknown(self):
        k, _ = scene()
        depth = np.zeros((k.height, k.width), dtype=np.float32)
        depth[0, 0], depth[0, 1] = np.nan, np.inf
        result = process_depth(depth, k)
        self.assertIsNone(result['ground'])
        self.assertTrue((result['grid'] == 2).all())

    def test_calibration_mismatch_rejected(self):
        k, depth = scene()
        with self.assertRaises(ValueError):
            process_depth(depth[:20], k)


if __name__ == '__main__':
    unittest.main()
