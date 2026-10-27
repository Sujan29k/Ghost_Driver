"""Save the Mac connection details on the GPU computer without printing tokens."""
from getpass import getpass
from pathlib import Path
import os


def main():
    from dotenv import dotenv_values, set_key
    from bridge import parse_args
    path = Path(__file__).with_name('.env')
    template = path.with_name('.env.example')
    existing = dotenv_values(path) if path.exists() else {}
    print('Keep the Mac backend and tunnel running. Use the current HTTPS tunnel base URL.')
    url = input('Backend URL (Enter keeps the saved URL): ').strip() or existing.get('BACKEND_URL', '')
    token = getpass('Sender token (hidden; Enter keeps the saved token): ').strip() or existing.get('SENDER_TOKEN', '')
    # Validate before creating or modifying any local settings.
    parse_args([], {**dotenv_values(template), **existing, 'BACKEND_URL': url, 'SENDER_TOKEN': token})
    if not path.exists():
        # Open with private permissions from the beginning on POSIX systems.
        with open(path, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
            output.write(template.read_text())
    set_key(str(path), 'BACKEND_URL', url)
    set_key(str(path), 'SENDER_TOKEN', token)
    print('Saved carla-service/.env. Existing AI and traffic settings preserved.')
    print('Start CARLA, then run: python carla-service/bridge.py')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('Configuration cancelled; connection settings were not changed.')
