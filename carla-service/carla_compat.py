"""Explicit CARLA release policy shared by startup and the setup checker."""
RESEARCH_VERSIONS = ('0.9.15', '0.9.16')


def validate_versions(client_version, server_version, research=True):
    if client_version != server_version:
        raise RuntimeError(f'CARLA version mismatch: client {client_version}, server {server_version}. '
                           'Install the Python client matching the running simulator.')
    if research and server_version not in RESEARCH_VERSIONS:
        raise RuntimeError('Research controls require matching CARLA 0.9.15 or 0.9.16 client/server releases.')
