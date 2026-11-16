"""Grabación local y aprendizaje por imitación. Python 3.11+."""
import argparse
import ctypes
import json
import threading
import time
from pathlib import Path

KEYS = ['w', 'a', 's', 'd', 'space', 'shift', 'e', 'r', '1', '2', '3']
ACTIONS = KEYS + ['left', 'right']
SIZE = (160, 90)


def focused():
    user = ctypes.windll.user32
    title = ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(user.GetForegroundWindow(), title, 512)
    return 'roblox' in title.value.lower()


def record(args):
    import mss
    from PIL import Image
    from pynput import keyboard, mouse

    root = Path(args.data) / str(time.time_ns())
    root.mkdir(parents=True)
    lock = threading.Lock()
    held, taps = set(), set()
    state = {'active': False, 'stop': False, 'scroll': 0}

    def name(key):
        return getattr(key, 'char', None) or getattr(key, 'name', '')

    def press(key):
        with lock:
            if key == keyboard.Key.f8:
                state['active'] = not state['active']
                held.clear()
                taps.clear()
                print('Grabando' if state['active'] else 'Pausa', flush=True)
            elif key == keyboard.Key.f9:
                state['stop'] = True
            elif state['active'] and focused() and name(key) in KEYS:
                held.add(name(key))
                taps.add(name(key))

    def release(key):
        with lock:
            held.discard(name(key))

    def click(x, y, button, down):
        with lock:
            if not state['active'] or not focused():
                return
            if button.name in ('left', 'right'):
                if down:
                    held.add(button.name)
                    taps.add(button.name)
                else:
                    held.discard(button.name)

    def scroll(x, y, dx, dy):
        with lock:
            if state['active'] and focused():
                state['scroll'] += dy

    print('F8: iniciar/pausar. F9: terminar. Solo graba con Roblox al frente.')
    controller = mouse.Controller()
    previous = None
    started = time.perf_counter()
    count = 0
    with keyboard.Listener(on_press=press, on_release=release), mouse.Listener(on_click=click, on_scroll=scroll), mss.mss() as screen, (root / 'samples.jsonl').open('w', encoding='utf-8') as output:
        if not 1 <= args.monitor < len(screen.monitors):
            raise ValueError('Monitor inválido; usa --monitor 1 para el principal.')
        (root / 'metadata.json').write_text(json.dumps({'fps': args.fps, 'size': SIZE, 'actions': ACTIONS, 'monitor': screen.monitors[args.monitor]}, indent=2), encoding='utf-8')
        while True:
            tick = time.perf_counter()
            with lock:
                if state['stop']:
                    break
                active = state['active'] and focused()
                if not active:
                    held.clear()
                    taps.clear()
                    state['scroll'] = 0
            if not active:
                previous = None
                time.sleep(0.05)
                continue
            frame = screen.grab(screen.monitors[args.monitor])
            position = controller.position
            with lock:
                labels = [int(k in held or k in taps) for k in ACTIONS]
                taps.clear()
                wheel = state['scroll']
                state['scroll'] = 0
            delta = [0, 0] if previous is None else [position[i] - previous[i] for i in range(2)]
            previous = position
            filename = f'{count:08d}.jpg'
            Image.frombytes('RGB', frame.size, frame.rgb).resize(SIZE).save(root / filename, quality=85)
            output.write(json.dumps({'image': filename, 'time': tick - started, 'buttons': labels, 'mouse': delta, 'scroll': wheel}) + '\n')
            output.flush()
            count += 1
            time.sleep(max(0, 1 / args.fps - (time.perf_counter() - tick)))
    print(f'{count} muestras guardadas en {root}')


def model():
    from torch import nn
    return nn.Sequential(nn.Conv2d(3, 16, 5, stride=2), nn.ReLU(), nn.Conv2d(16, 32, 3, stride=2), nn.ReLU(), nn.AdaptiveAvgPool2d((4, 6)), nn.Flatten(), nn.Linear(768, 128), nn.ReLU(), nn.Linear(128, len(ACTIONS) + 2))


def tensor(path):
    import numpy as np
    import torch
    from PIL import Image
    with Image.open(path) as img:
        pixels = np.array(img.convert('RGB').resize(SIZE), dtype=np.float32) / 255
    return torch.from_numpy(pixels).permute(2, 0, 1)


def train(args):
    import random
    import torch
    from torch.utils.data import DataLoader, Dataset

    sessions = sorted(Path(args.data).glob('*/samples.jsonl'))
    if len(sessions) < 2:
        raise ValueError('Graba al menos 2 sesiones: una se reserva para validación.')
    random.Random(42).shuffle(sessions)
    torch.manual_seed(42)

    class Samples(Dataset):
        def __init__(self, files):
            self.rows = [(f.parent, json.loads(line)) for f in files for line in f.read_text(encoding='utf-8').splitlines() if line.strip()]
            if not self.rows:
                raise ValueError('Una partición no contiene muestras. Graba sesiones con F8.')

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            folder, row = self.rows[i]
            return tensor(folder / row['image']), torch.tensor(row['buttons'], dtype=torch.float32), torch.tensor(row['mouse'], dtype=torch.float32).clamp(-100, 100) / 100

    split = max(1, len(sessions) // 5)
    validation = DataLoader(Samples(sessions[:split]), batch_size=32)
    training = DataLoader(Samples(sessions[split:]), batch_size=32, shuffle=True)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net = model().to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=0.001)
    best = float('inf')
    destination = Path(args.model)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(args.epochs):
        net.train()
        for images, buttons, movement in training:
            prediction = net(images.to(device))
            loss = torch.nn.functional.binary_cross_entropy_with_logits(prediction[:, :len(ACTIONS)], buttons.to(device)) + torch.nn.functional.smooth_l1_loss(prediction[:, len(ACTIONS):], movement.to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        net.eval()
        total, count = 0.0, 0
        with torch.no_grad():
            for images, buttons, movement in validation:
                prediction = net(images.to(device))
                loss = torch.nn.functional.binary_cross_entropy_with_logits(prediction[:, :len(ACTIONS)], buttons.to(device)) + torch.nn.functional.smooth_l1_loss(prediction[:, len(ACTIONS):], movement.to(device))
                total += loss.item() * len(images)
                count += len(images)
        score = total / count
        print(f'Época {epoch + 1}: pérdida de validación {score:.4f}', flush=True)
        if score < best:
            best = score
            torch.save({'state': net.cpu().state_dict(), 'actions': ACTIONS, 'size': SIZE}, destination)
            net.to(device)
    print(f'Mejor modelo: {destination}. La pérdida no mide supervivencia.')


def predict(args):
    import torch
    checkpoint = torch.load(args.model, map_location='cpu', weights_only=True)
    if checkpoint['actions'] != ACTIONS:
        raise ValueError('Las acciones del modelo no coinciden.')
    net = model()
    net.load_state_dict(checkpoint['state'])
    net.eval()
    with torch.no_grad():
        result = net(tensor(args.image).unsqueeze(0))[0]
    print(json.dumps({'probabilidades': dict(zip(ACTIONS, result[:len(ACTIONS)].sigmoid().tolist())), 'mouse_estimado': (result[len(ACTIONS):].clamp(-1, 1) * 100).tolist()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    rec = subs.add_parser('record', help='Grabar demostraciones locales')
    rec.add_argument('--data', default='data')
    rec.add_argument('--fps', type=int, default=10, choices=range(1, 31))
    rec.add_argument('--monitor', type=int, default=1)
    fit = subs.add_parser('train', help='Entrenar con sesiones separadas para validación')
    fit.add_argument('--data', default='data')
    fit.add_argument('--model', default='models/policy.pt')
    fit.add_argument('--epochs', type=int, default=10, choices=range(1, 1001))
    pred = subs.add_parser('predict', help='Probar una imagen sin controlar el juego')
    pred.add_argument('image')
    pred.add_argument('--model', default='models/policy.pt')
    args = parser.parse_args()
    {'record': record, 'train': train, 'predict': predict}[args.command](args)


if __name__ == '__main__':
    main()
