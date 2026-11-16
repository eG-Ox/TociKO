import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from PIL import Image
import torch

from policy import ACTIONS, FORMAT, HISTORY, Demonstrations, load_policy, session_files, train


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        torch.set_num_threads(1)

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, name, segments):
        folder = self.root / name
        folder.mkdir()
        (folder / 'metadata.json').write_text(json.dumps({'format': FORMAT, 'fps': 10}), encoding='utf-8')
        rows = []
        for i, segment in enumerate(segments):
            filename = f'{i}.jpg'
            Image.new('RGB', (160, 90), color=(i * 30, 30, 60)).save(folder / filename)
            rows.append({'image': filename, 'segment': segment, 'buttons': [1] + [0] * (len(ACTIONS) - 1), 'mouse': [10, -10]})
        path = folder / 'samples.jsonl'
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
        return path

    def test_history_does_not_cross_pause_or_session(self):
        a = self.session('a', [1, 1, 2, 2])
        b = self.session('b', [1, 1])
        data = Demonstrations([a, b])
        self.assertEqual(data.clips[1], [0, 0, 0, 1])
        self.assertEqual(data.clips[2], [2, 2, 2, 2])
        self.assertEqual(data.clips[4], [4, 4, 4, 4])
        frames, buttons, movement = data[1]
        self.assertEqual(tuple(frames.shape), (3 * HISTORY, 90, 160))
        self.assertEqual(len(buttons), len(ACTIONS))
        torch.testing.assert_close(movement, torch.tensor([0.1, -0.1]))

    def test_train_save_load_infer_and_session_split(self):
        self.session('a', [1, 1, 1, 1])
        self.session('b', [1, 1, 1, 1])
        path = self.root / 'models' / 'policy.pt'
        args = SimpleNamespace(data=str(self.root), model=str(path), epochs=1, batch_size=2)
        with contextlib.redirect_stdout(io.StringIO()):
            train(args)
        net, metadata = load_policy(path)
        self.assertFalse(set(metadata['training_sessions']) & set(metadata['validation_sessions']))
        frames, _, _ = Demonstrations(session_files(self.root))[0]
        with torch.inference_mode():
            output = net(frames.unsqueeze(0))
        self.assertEqual(tuple(output.shape), (1, len(ACTIONS) + 2))
        self.assertTrue(torch.isfinite(output).all())

    def test_old_model_rejected(self):
        path = self.root / 'old.pt'
        torch.save({'actions': ACTIONS}, path)
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            load_policy(path)

    def test_mixed_fps_rejected(self):
        self.session('a', [1])
        b = self.session('b', [1])
        (b.parent / 'metadata.json').write_text(json.dumps({'format': FORMAT, 'fps': 20}))
        args = SimpleNamespace(data=str(self.root), model='unused', epochs=1, batch_size=2)
        with self.assertRaisesRegex(ValueError, 'frecuencia'):
            train(args)


if __name__ == '__main__':
    unittest.main()
