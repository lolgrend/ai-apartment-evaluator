import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("LITE_LLM_KEY", "test-key")
os.environ.setdefault("LITE_LLM_BASE_URL", "http://litellm.test:4000")

from app.routers.listings import _apply_floorplan_detection


class FloorplanDetectionTests(unittest.TestCase):
    def test_keeps_scraper_matches_and_adds_model_matches(self):
        images = [
            SimpleNamespace(is_floorplan=True),
            SimpleNamespace(is_floorplan=False),
            SimpleNamespace(is_floorplan=False),
        ]

        _apply_floorplan_detection(images, [2, 0, 99])


        self.assertEqual(
            [image.is_floorplan for image in images], [True, True, False]
        )


if __name__ == "__main__":
    unittest.main()
