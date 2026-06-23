from __future__ import annotations

import unittest

from app.templating import _chat_markdown


class ChatMarkdownTests(unittest.TestCase):
    def test_renders_formatting_and_internal_listing_link(self):
        html = str(_chat_markdown(
            "**Wniosek:** warto zobaczyć.\n\n- dobra cena\n- [Ołbin](/listing/7)"
        ))

        self.assertIn("<strong>Wniosek:</strong>", html)
        self.assertIn("<li>dobra cena</li>", html)
        self.assertIn('<a href="/listing/7">Ołbin</a>', html)

    def test_removes_script_and_unsafe_link(self):
        html = str(_chat_markdown(
            '<script>alert("x")</script> [klik](javascript:alert(1))'
        ))

        self.assertNotIn("<script", html)
        self.assertNotIn("javascript:", html)


if __name__ == "__main__":
    unittest.main()
