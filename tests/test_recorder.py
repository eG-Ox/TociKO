import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from recorder import key_name, record


class RecorderTests(unittest.TestCase):
    def test_uppercase_and_shift_normalization(self):
        self.assertEqual(key_name(SimpleNamespace(char='W')), 'w')
        self.assertEqual(key_name(SimpleNamespace(char=None, name='shift_r')), 'shift')

    def test_records_short_taps_after_frame_and_stops_on_f9(self):
        keys = SimpleNamespace(f8='F8', f9='F9')
        listeners = []

        class Listener:
            def __init__(self, **callbacks):
                self.callbacks = callbacks
                listeners.append(self)

            def __enter__(self):
                if 'on_release' in self.callbacks:
                    self.callbacks['on_release'](keys.f8)
                return self

            def __exit__(self, *args):
                pass

            def is_alive(self):
                return True

        class Screen:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def grab(self, region):
                return SimpleNamespace(size=(160, 90), rgb=bytes(160 * 90 * 3))

        class RawMouse(Screen):
            error = None

            def take(self):
                return [6, -4]

        sleeps = []
        def interval(seconds):
            sleeps.append(seconds)
            keyboard, mouse = listeners
            if len(sleeps) == 1:
                key = SimpleNamespace(char='w')
                keyboard.callbacks['on_press'](key)
                keyboard.callbacks['on_release'](key)
                button = SimpleNamespace(name='left')
                mouse.callbacks['on_click'](0, 0, button, True)
                mouse.callbacks['on_click'](0, 0, button, False)
            else:
                keyboard.callbacks['on_release'](keys.f9)

        windows = SimpleNamespace(RawMouse=RawMouse, dpi_aware=lambda: None,
                                  game_region=lambda: {'left': 0, 'top': 0, 'width': 160, 'height': 90})
        modules = {'windows_io': windows, 'mss': SimpleNamespace(mss=Screen),
                   'pynput': SimpleNamespace(keyboard=SimpleNamespace(Listener=Listener, Key=keys),
                                             mouse=SimpleNamespace(Listener=Listener))}
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, modules), patch('recorder.time.sleep', side_effect=interval), contextlib.redirect_stdout(io.StringIO()):
            record(SimpleNamespace(data=temp, fps=10))
            files = list(Path(temp).glob('*/samples.jsonl'))
            rows = [json.loads(line) for line in files[0].read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['buttons'][0], 1)
            self.assertEqual(rows[0]['buttons'][-2], 1)
            self.assertEqual(rows[0]['mouse'], [6, -4])
            self.assertTrue((files[0].parent / rows[0]['image']).exists())


if __name__ == '__main__':
    unittest.main()
