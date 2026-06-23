from __future__ import annotations

import os
import unittest

from pydantic import ValidationError

os.environ.setdefault("LITE_LLM_KEY", "test-key")
os.environ.setdefault("LITE_LLM_BASE_URL", "http://litellm.test:4000")

from app.config import MODEL_OPTIONS, Settings  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_litellm_configuration_cannot_be_empty(self):
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                lite_llm_key="",
                lite_llm_base_url="",
            )

    def test_gpt_5_5_is_available(self):
        self.assertIn("gpt-5.5", MODEL_OPTIONS)


if __name__ == "__main__":
    unittest.main()
