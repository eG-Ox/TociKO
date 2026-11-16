"""Política temporal, datos de demostración y checkpoints versionados."""
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import Dataset

KEYS = ['w', 'a', 's', 'd', 'space', 'shift', 'e', 'r', '1', '2', '3']
ACTIONS = KEYS + ['left', 'right']
SIZE = (160, 90)
HISTORY = 4
FORMAT = 2


def image_tensor(image):
    pixels = np.array(image.convert('RGB').resize(SIZE), dtype=np.float32) / 255
    return torch.from_numpy(pixels).permute(2, 0, 1)


def network():
    return nn.Sequential(
        nn.Conv2d(3 * HISTORY, 24, 5, stride=2), nn.ReLU(),
        nn.Conv2d(24, 48, 3, stride=2), nn.ReLU(),
        nn.AdaptiveAvgPool2d((4, 6)), nn.Flatten(),
        nn.Linear(1152, 192), nn.ReLU(), nn.Linear(192, len(ACTIONS) + 2))


def load_policy(path):
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    if (checkpoint.get('format') != FORMAT or checkpoint.get('actions') != ACTIONS
            or checkpoint.get('history') != HISTORY or tuple(checkpoint.get('size', ())) != SIZE):
        raise ValueError('Modelo incompatible. Graba sesiones v2 y vuelve a entrenar.')
    net = network()
    net.load_state_dict(checkpoint['state'])
    return net.eval(), checkpoint


def session_files(root):
    files = []
    for path in sorted(Path(root).glob('*/samples.jsonl')):
        metadata = path.parent / 'metadata.json'
        if metadata.exists() and json.loads(metadata.read_text(encoding='utf-8')).get('format') == FORMAT:
            if path.stat().st_size:
                files.append(path)
    return files


class Demonstrations(Dataset):
    def __init__(self, files):
        self.rows, self.clips = [], []
        for path in files:
            history = []
            previous = None
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if len(row['buttons']) != len(ACTIONS) or len(row['mouse']) != 2:
                    raise ValueError(f'Acciones inválidas en {path}')
                if previous is None or row['segment'] != previous['segment']:
                    history = []
                index = len(self.rows)
                self.rows.append((path.parent, row))
                history.append(index)
                history = history[-HISTORY:]
                self.clips.append([history[0]] * (HISTORY - len(history)) + history[:])
                previous = row
        if not self.rows:
            raise ValueError('No hay demostraciones v2 en esta partición.')

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        frames = []
        for i in self.clips[index]:
            folder, row = self.rows[i]
            with Image.open(folder / row['image']) as image:
                frames.append(image_tensor(image))
        row = self.rows[index][1]
        return (torch.cat(frames), torch.tensor(row['buttons'], dtype=torch.float32),
                torch.tensor(row['mouse'], dtype=torch.float32).clamp(-100, 100) / 100)


def train(args):
    import random
    from torch.utils.data import DataLoader
    sessions = session_files(args.data)
    if len(sessions) < 2:
        raise ValueError('Necesitas al menos 2 sesiones v2 no vacías; graba con F8 y termina con F9.')
    rates = {json.loads((path.parent / 'metadata.json').read_text(encoding='utf-8'))['fps'] for path in sessions}
    if len(rates) != 1 or not 1 <= next(iter(rates)) <= 30:
        raise ValueError('Usa sesiones grabadas a la misma frecuencia de 1 a 30 FPS.')
    fps = next(iter(rates))
    random.Random(42).shuffle(sessions)
    torch.manual_seed(42)
    split = max(1, len(sessions) // 5)
    training = Demonstrations(sessions[split:])
    validation = Demonstrations(sessions[:split])
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net = network().to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=0.001)
    # Compensa acciones poco frecuentes, sin pesos ilimitados para acciones ausentes.
    labels = torch.tensor([row['buttons'] for _, row in training.rows], dtype=torch.float32)
    positives = labels.sum(0)
    weights = ((len(labels) - positives) / positives.clamp(min=1)).clamp(1, 10).to(device)
    train_loader = DataLoader(training, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(validation, batch_size=args.batch_size)
    destination = Path(args.model)
    destination.parent.mkdir(parents=True, exist_ok=True)
    best = float('inf')
    print(f'{len(training)} entrenamiento, {len(validation)} validación; {device}', flush=True)
    for epoch in range(args.epochs):
        net.train()
        for images, buttons, movement in train_loader:
            prediction = net(images.to(device))
            loss = (nn.functional.binary_cross_entropy_with_logits(
                prediction[:, :len(ACTIONS)], buttons.to(device), pos_weight=weights)
                + nn.functional.smooth_l1_loss(prediction[:, len(ACTIONS):], movement.to(device)))
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 5)
            optimizer.step()
        net.eval()
        total, count, tp, fp, fn = 0.0, 0, 0, 0, 0
        with torch.inference_mode():
            for images, buttons, movement in val_loader:
                buttons, movement = buttons.to(device), movement.to(device)
                prediction = net(images.to(device))
                loss = (nn.functional.binary_cross_entropy_with_logits(
                    prediction[:, :len(ACTIONS)], buttons, pos_weight=weights)
                    + nn.functional.smooth_l1_loss(prediction[:, len(ACTIONS):], movement))
                chosen = prediction[:, :len(ACTIONS)].sigmoid() >= 0.5
                target = buttons.bool()
                tp += (chosen & target).sum().item()
                fp += (chosen & ~target).sum().item()
                fn += (~chosen & target).sum().item()
                total += loss.item() * len(images)
                count += len(images)
        score = total / count
        f1 = 2 * tp / max(1, 2 * tp + fp + fn)
        print(f'Época {epoch + 1}: pérdida={score:.4f}; F1 acciones={f1:.3f}', flush=True)
        if score < best:
            best = score
            torch.save({'format': FORMAT, 'state': {k: v.detach().cpu().clone() for k, v in net.state_dict().items()},
                        'actions': ACTIONS, 'size': SIZE, 'history': HISTORY, 'fps': fps,
                        'validation_loss': score, 'validation_f1': f1,
                        'training_sessions': [str(p.parent) for p in sessions[split:]],
                        'validation_sessions': [str(p.parent) for p in sessions[:split]]}, destination)
    print(f'Modelo guardado: {destination}. F1 no equivale a supervivencia.')


def predict(args):
    net, _ = load_policy(args.model)
    with Image.open(args.image) as image:
        frame = image_tensor(image)
    with torch.inference_mode():
        result = net(torch.cat([frame] * HISTORY).unsqueeze(0))[0]
    print(json.dumps({'probabilidades': dict(zip(ACTIONS, result[:len(ACTIONS)].sigmoid().tolist())),
                      'mouse_estimado': (result[len(ACTIONS):].clamp(-1, 1) * 100).tolist()}, indent=2))
