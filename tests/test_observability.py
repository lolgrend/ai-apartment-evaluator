from __future__ import annotations

import unittest

from app import observability


class ObservabilityTests(unittest.TestCase):
    def test_payload_summary_redacts_text_and_omits_image_data(self):
        payload = {
            "model": "openai/gpt-5.5",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Kontakt: test@example.com, +48 123 456 789"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,SECRET_IMAGE"},
                        },
                    ],
                }
            ],
        }

        summary = observability.summarize_payload(payload)

        content = summary["messages"][0]["content"]
        self.assertEqual(content["image_count"], 1)
        self.assertIn("[email]", content["text"])
        self.assertIn("[phone]", content["text"])
        self.assertNotIn("SECRET_IMAGE", str(summary))


if __name__ == "__main__":
    unittest.main()
