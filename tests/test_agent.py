import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

from control import ACTIONS


class Driver:
    def __init__(self):
        self.held, self.presses, self.moves = set(), [], []

    def press(self, key):
        self.held.add(key)
        self.presses.append(key)

    def release(self, key):
        self.held.discard(key)

    def move(self, dx, dy):
        self.moves.append((dx, dy))


class AgentTests(unittest.TestCase):
    def test_full_loop_decides_acts_logs_and_releases_on_stop(self):
        from agent import play
        torch.set_num_threads(1)
        driver = Driver()
        keys = SimpleNamespace(f8='f8', f9='f9')
        listeners = []

        class Listener:
            def __init__(self, on_release):
                self.callback = on_release
                listeners.append(self)

            def __enter__(self):
                self.callback(keys.f8)
                return self

            def __exit__(self, *args):
                pass

            def is_alive(self):
                return True

        class Screen:
            def __init__(self):
                self.count = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def grab(self, region):
                self.count += 1
                if self.count >= 3:
                    listeners[0].callback(keys.f9)
                return SimpleNamespace(size=(160, 90), rgb=bytes(160 * 90 * 3))

        class Net(torch.nn.Module):
            def forward(self, batch):
                result = torch.full((len(batch), len(ACTIONS) + 2), -10.0, device=batch.device)
                result[:, 0] = 10
                result[:, -2:] = 0.1
                return result

        region = {'left': 0, 'top': 0, 'width': 160, 'height': 90}
        windows = SimpleNamespace(Driver=lambda: driver, dpi_aware=lambda: None,
                                  focused=lambda: True, game_region=lambda: region)
        modules = {'windows_io': windows, 'mss': SimpleNamespace(mss=Screen),
                   'pynput': SimpleNamespace(keyboard=SimpleNamespace(Listener=Listener, Key=keys))}
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, modules), patch('policy.load_policy', return_value=(Net(), {'fps': 10})), contextlib.redirect_stdout(io.StringIO()):
            play(SimpleNamespace(model='fake.pt', execute=True, logs=temp, threshold=0.55, mouse_scale=1))
            rows = [json.loads(line) for p in Path(temp).glob('*.jsonl') for line in p.read_text().splitlines()]
        self.assertTrue(any(row['applied'] and row['actions'] == ['w'] for row in rows))
        self.assertIn('w', driver.presses)
        self.assertTrue(driver.moves)
        self.assertFalse(driver.held)


if __name__ == '__main__':
    unittest.main()
