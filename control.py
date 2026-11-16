"""Selección de acciones y liberación por pausa, pérdida de foco o datos obsoletos."""
import math
import threading
import time

ACTIONS = ['w', 'a', 's', 'd', 'space', 'shift', 'e', 'r', '1', '2', '3', 'left', 'right']


def choose(probabilities, movement, threshold=0.55, mouse_limit=40):
    if len(probabilities) != len(ACTIONS) or len(movement) != 2:
        raise ValueError('Dimensiones de política inválidas.')
    if not all(math.isfinite(x) for x in [*probabilities, *movement]):
        raise ValueError('El modelo devolvió valores no finitos.')
    scores = dict(zip(ACTIONS, probabilities))
    selected = {key for key, value in scores.items() if value >= threshold}
    for group in [('w', 's'), ('a', 'd'), ('1', '2', '3')]:
        candidates = selected.intersection(group)
        if len(candidates) > 1:
            winner = max(group, key=lambda key: scores[key])
            selected.difference_update(group)
            selected.add(winner)
    return selected, tuple(round(max(-mouse_limit, min(mouse_limit, v))) for v in movement)


class Actuator:
    """El watchdog puede soltar controles aunque la inferencia tarde demasiado."""
    def __init__(self, driver, focused, timeout=0.5, clock=time.monotonic):
        self.driver, self.focused, self.timeout, self.clock = driver, focused, timeout, clock
        self.lock = threading.RLock()
        self.enabled = False
        self.held = set()
        self.deadline = 0.0
        self.generation = 0

    def release(self):
        with self.lock:
            errors = []
            for key in list(self.held):
                try:
                    self.driver.release(key)
                    self.held.discard(key)
                except Exception as exc:
                    errors.append(exc)
            if errors:
                raise errors[0]

    def pause(self):
        with self.lock:
            self.enabled = False
            self.generation += 1
            self.release()

    def arm(self):
        with self.lock:
            self.release()
            self.generation += 1
            self.enabled = True
            self.deadline = self.clock() + self.timeout
            return self.generation

    def tick(self):
        with self.lock:
            if self.enabled and (not self.focused() or self.clock() >= self.deadline):
                self.pause()

    def apply(self, selected, movement, generation):
        with self.lock:
            self.tick()
            if not self.enabled or generation != self.generation:
                return False
            if not set(selected).issubset(ACTIONS):
                self.pause()
                raise ValueError('Acción no permitida.')
            # Cada tecla se registra antes de pulsar para intentar liberarla si el driver falla.
            for key in self.held - selected:
                self.driver.release(key)
            self.held.intersection_update(selected)
            for key in selected - self.held:
                self.held.add(key)
                self.driver.press(key)
            self.driver.move(*movement)
            self.deadline = self.clock() + self.timeout
            return True
