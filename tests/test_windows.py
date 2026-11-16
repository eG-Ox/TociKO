import ctypes
import sys
import unittest


@unittest.skipUnless(sys.platform == 'win32', 'Solo Windows')
class WindowsTests(unittest.TestCase):
    def test_input_structures_match_windows_abi(self):
        import windows_io as win
        self.assertEqual(ctypes.sizeof(win.Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertEqual(ctypes.sizeof(win.RawMouseData), 24)

    def test_raw_mouse_start_stop_without_sending_input(self):
        from windows_io import RawMouse
        with RawMouse() as mouse:
            self.assertEqual(len(mouse.take()), 2)
            self.assertIsNone(mouse.error)
        self.assertFalse(mouse.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
