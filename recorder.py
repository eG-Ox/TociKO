"""Demostraciones alineadas: imagen inicial y acciones del intervalo siguiente."""
import json
import threading
import time
from pathlib import Path


def key_name(key):
    name = (getattr(key, 'char', None) or getattr(key, 'name', '')).lower()
    return 'shift' if name in ('shift_l', 'shift_r', 'shift') else name


def record(args):
    import mss
    from PIL import Image
    from pynput import keyboard, mouse
    from policy import ACTIONS, KEYS, SIZE, FORMAT
    from windows_io import RawMouse, game_region, dpi_aware
    dpi_aware()
    root = Path(args.data) / str(time.time_ns())
    root.mkdir(parents=True)
    state = {'active': False, 'stop': False, 'segment': 0, 'scroll': 0, 'region': None}
    held, taps = set(), set()
    lock = threading.Lock()

    def press(key):
        with lock:
            if state['active'] and key_name(key) in KEYS:
                held.add(key_name(key))
                taps.add(key_name(key))

    def release(key):
        with lock:
            held.discard(key_name(key))
            # Toggle al soltar: la repetición de teclas no activa/desactiva muchas veces.
            if key == keyboard.Key.f8:
                state['active'] = not state['active']
                state['segment'] += 1
                held.clear()
                taps.clear()
                print('Grabando' if state['active'] else 'Pausa', flush=True)
            elif key == keyboard.Key.f9:
                state['stop'] = True

    def click(x, y, button, down):
        with lock:
            if state['active'] and button.name in ('left', 'right'):
                if down:
                    held.add(button.name)
                    taps.add(button.name)
                else:
                    held.discard(button.name)

    def scroll(x, y, dx, dy):
        with lock:
            if state['active']:
                state['scroll'] += dy

    count = 0
    print('F8: iniciar/pausar; F9: terminar. Abre Roblox y activa F8.')
    with RawMouse() as raw, keyboard.Listener(on_press=press, on_release=release) as kl, mouse.Listener(on_click=click, on_scroll=scroll) as ml, mss.mss() as screen, (root / 'samples.jsonl').open('w', encoding='utf-8') as output:
        metadata = {'format': FORMAT, 'fps': args.fps, 'size': SIZE, 'actions': ACTIONS,
                    'mouse_source': 'windows_raw_relative', 'regions': []}
        while True:
            with lock:
                if state['stop']:
                    break
                active, segment = state['active'], state['segment']
            if not kl.is_alive() or not ml.is_alive():
                raise RuntimeError('Se detuvo el listener de entrada.')
            if raw.error:
                raise raw.error
            region = game_region() if active else None
            if not region:
                with lock:
                    if active:
                        state['active'] = False
                        state['segment'] += 1
                        print('Roblox perdió el foco. Vuelve al juego y pulsa F8.', flush=True)
                    held.clear()
                    taps.clear()
                    state['scroll'] = 0
                raw.take()
                time.sleep(0.05)
                continue
            if state['region'] != region:
                state['region'] = region
                with lock:
                    state['segment'] += 1
                    segment = state['segment']
                metadata['regions'].append(region)
            (root / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
            tick = time.monotonic()
            frame = screen.grab(region)
            raw.take()
            with lock:
                taps.clear()
                state['scroll'] = 0
            time.sleep(max(0, 1 / args.fps - (time.monotonic() - tick)))
            delta = raw.take()
            with lock:
                valid = (state['active'] and not state['stop'] and state['segment'] == segment)
                labels = [int(k in held or k in taps) for k in ACTIONS]
                wheel = state['scroll']
            if not valid or game_region() != region:
                continue
            filename = f'{count:08d}.jpg'
            Image.frombytes('RGB', frame.size, frame.rgb).resize(SIZE).save(root / filename, quality=85)
            output.write(json.dumps({'image': filename, 'time': tick, 'segment': segment,
                                     'buttons': labels, 'mouse': delta, 'scroll': wheel}) + '\n')
            output.flush()
            count += 1
    print(f'{count} muestras en {root}')
