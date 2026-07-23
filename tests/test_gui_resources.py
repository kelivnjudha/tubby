from __future__ import annotations

import unittest

from tubby.gui import APP_ICON_NAME, _app_icon_path


class GuiResourceTests(unittest.TestCase):
    def test_desktop_icon_is_available(self) -> None:
        icon_path = _app_icon_path()

        self.assertIsNotNone(icon_path)
        assert icon_path is not None
        self.assertEqual(icon_path.name, APP_ICON_NAME)
        self.assertGreater(icon_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
