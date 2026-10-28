"""Build the GPU-computer handoff without credentials, datasets or environments."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
source = root / 'carla-service'
output = root / 'artifacts/ghostdriver-sender.zip'
output.parent.mkdir(exist_ok=True)
files = list(source.glob('*.py')) + list(source.glob('requirements*.txt'))
files += [source / '.env.example', source / 'README.md', source / 'ghostdriver/integration.py']
files += list((root / 'docs').glob('*.md'))
files += list((root / 'docs/examples').glob('evaluation-example.*'))
files += list((source / 'scenario-configs').glob('*.json'))
files += [p for p in (source / 'vendor/raft').rglob('*') if p.is_file() and p.suffix in ('.py', '.md')]
files += [source / 'vendor/raft/LICENSE', source / 'ghostdriver/models/raft-small.pth',
          source / 'ghostdriver/yolov8n_coco128-5/weights/best.pt']
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        archive.write(path, path.relative_to(root))
print(f'Created {output.relative_to(root)} ({output.stat().st_size / 1024 / 1024:.1f} MB)')
print('Contains the live sender, both checkpoints, dependencies and setup guides. No connection credentials.')
