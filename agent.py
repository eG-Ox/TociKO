"""Bucle autónomo de observación, política temporal y actuación con watchdog."""
from collections import deque
import json
from pathlib import Path
import threading
import time

from control import Actuator, choose


def play(args):
    import mss
    import torch
    from PIL import Image
    from pynput import keyboard
    from policy import ACTIONS, HISTORY, image_tensor, load_policy
    from windows_io import Driver, dpi_aware, game_region, focused

    dpi_aware()
    net, metadata = load_policy(args.model)
    fps = metadata['fps']
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net.to(device)
    # Calienta la inferencia antes de permitir controles reales.
    with torch.inference_mode():
        net(torch.zeros(1, HISTORY * 3, 90, 160, device=device))
    driver = Driver() if args.execute else NullDriver()
    actuator = Actuator(driver, focused)
    stopped = threading.Event()
    errors = []

    def release(key):
        if key == keyboard.Key.f9:
            stopped.set()
        elif key == keyboard.Key.f8:
            # Solo señal: el watchdog verifica el foco y libera en su propio hilo.
            with actuator.lock:
                if actuator.enabled:
                    actuator.pause()
                elif focused():
                    actuator.arm()
                    print('Autónomo activo' if args.execute else 'Vista previa activa', flush=True)

    def watchdog():
        try:
            while not stopped.wait(0.02):
                if not listener.is_alive():
                    raise RuntimeError('Se perdió el listener de parada.')
                actuator.tick()
        except Exception as exc:
            errors.append(exc)
            stopped.set()
        finally:
            actuator.pause()

    history = deque(maxlen=HISTORY)
    logs = Path(args.logs)
    logs.mkdir(parents=True, exist_ok=True)
    logfile = logs / f'{time.time_ns()}.jsonl'
    mode = 'CONTROL REAL' if args.execute else 'VISTA PREVIA: no envía controles'
    print(f'{mode}. F8: activar/pausar dentro de Roblox; F9: terminar.', flush=True)
    print('Al perder foco o tardar >0.5 s, se pausa. Reactiva con F8.', flush=True)
    previous_generation = None
    previous_region = None
    with keyboard.Listener(on_release=release) as listener, mss.mss() as screen, logfile.open('w', encoding='utf-8') as output:
        worker = threading.Thread(target=watchdog, daemon=True)
        worker.start()
        try:
            while not stopped.is_set():
                with actuator.lock:
                    active, generation = actuator.enabled, actuator.generation
                region = game_region() if active else None
                if not region:
                    history.clear()
                    stopped.wait(0.05)
                    continue
                if generation != previous_generation or region != previous_region:
                    history.clear()
                    previous_generation = generation
                    previous_region = region
                tick = time.monotonic()
                shot = screen.grab(region)
                image = Image.frombytes('RGB', shot.size, shot.rgb)
                frame = image_tensor(image)
                if not history:
                    history.extend([frame] * HISTORY)
                else:
                    history.append(frame)
                with torch.inference_mode():
                    result = net(torch.cat(list(history)).unsqueeze(0).to(device))[0].cpu()
                probabilities = result[:len(ACTIONS)].sigmoid().tolist()
                movement = (result[len(ACTIONS):].clamp(-1, 1) * 100 * args.mouse_scale).tolist()
                selected, delta = choose(probabilities, movement, args.threshold)
                # El watchdog puede haber pausado durante captura/inferencia.
                applied = actuator.apply(selected, delta, generation) if not stopped.is_set() else False
                output.write(json.dumps({'time': tick, 'actions': sorted(selected), 'mouse': delta,
                                         'probabilities': probabilities, 'applied': applied,
                                         'execute': args.execute, 'latency': time.monotonic() - tick}) + '\n')
                output.flush()
                stopped.wait(max(0, 1 / fps - (time.monotonic() - tick)))
        finally:
            stopped.set()
            worker.join(timeout=2)
            actuator.pause()
    if errors:
        raise errors[0]
    print(f'Sesión terminada. Decisiones en {logfile}')


class NullDriver:
    def press(self, key):
        pass

    def release(self, key):
        pass

    def move(self, dx, dy):
        pass
