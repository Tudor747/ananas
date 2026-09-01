from io import StringIO
import unittest

from pi_ot_probe.ui.lcd import MockLCD


class MockLCDTests(unittest.TestCase):
    def test_frame_is_exactly_sixteen_columns(self) -> None:
        output = StringIO()
        lcd = MockLCD(output)
        frame = lcd.display("QUICK AUDIT IS LONG", "> START")
        lines = frame.splitlines()
        self.assertEqual(lines[0], "+----------------+")
        self.assertEqual(lines[1], "|QUICK AUDIT IS L|")
        self.assertEqual(lines[2], "|> START         |")
        self.assertTrue(output.getvalue().endswith("\n"))


if __name__ == "__main__":
    unittest.main()

