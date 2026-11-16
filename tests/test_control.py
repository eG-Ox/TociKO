import unittest
from control import ACTIONS, Actuator, choose


class Driver:
    def __init__(self):
        self.held, self.moves = set(), []

    def press(self, key):
        self.held.add(key)

    def release(self, key):
        self.held.discard(key)

    def move(self, dx, dy):
        self.moves.append((dx, dy))


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.time = 0
        self.focus = True
        self.driver = Driver()
        self.actor = Actuator(self.driver, lambda: self.focus, clock=lambda: self.time)

    def test_conflicts_and_camera_limit(self):
        scores = dict.fromkeys(ACTIONS, 0)
        scores.update(w=0.8, s=0.9, a=0.7, d=0.6, **{'1': 0.6, '2': 0.9, '3': 0.7})
        selected, movement = choose([scores[k] for k in ACTIONS], [900, -900])
        self.assertEqual(selected, {'s', 'a', '2'})
        self.assertEqual(movement, (40, -40))

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            choose([float('nan')] * len(ACTIONS), [0, 0])

    def test_no_control_until_armed(self):
        self.assertFalse(self.actor.apply({'w'}, (3, 4), 0))
        self.assertFalse(self.driver.held)

    def test_focus_loss_releases_and_requires_rearm(self):
        generation = self.actor.arm()
        self.assertTrue(self.actor.apply({'w', 'left'}, (3, 4), generation))
        self.focus = False
        self.actor.tick()
        self.assertFalse(self.driver.held)
        self.focus = True
        self.assertFalse(self.actor.apply({'w'}, (0, 0), generation))

    def test_stalled_inference_releases(self):
        generation = self.actor.arm()
        self.actor.apply({'w'}, (0, 0), generation)
        self.time = 0.6
        self.actor.tick()
        self.assertFalse(self.driver.held)
        self.assertFalse(self.actor.enabled)

    def test_stale_result_after_pause_and_rearm_rejected(self):
        old = self.actor.arm()
        self.actor.pause()
        self.actor.arm()
        self.assertFalse(self.actor.apply({'left'}, (0, 0), old))
        self.assertFalse(self.driver.held)

    def test_release_attempts_all_keys_on_failure(self):
        generation = self.actor.arm()
        self.actor.apply({'w', 'left'}, (0, 0), generation)
        original = self.driver.release
        def failing(key):
            if key == 'w':
                raise OSError('fallo de dispositivo')
            original(key)
        self.driver.release = failing
        with self.assertRaises(OSError):
            self.actor.pause()
        self.assertNotIn('left', self.driver.held)


if __name__ == '__main__':
    unittest.main()
