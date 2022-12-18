"""Verifiche relative all'accesso/lettura di una playlist."""
from pathlib import Path

from playlists.playlist import Playlist


def test_loader_1():
    """Verifica con directory esistente."""
    plist = Playlist('../shared/playlist_test')
    plist.load()

def test_loader_2():
    """Verifica con directory insesistente."""
    playlist_path = Path('../shared/playlist')
    if playlist_path.is_dir():
        for filetodelete in playlist_path.glob("*"):
            if filetodelete.is_file():
                filetodelete.unlink()
        playlist_path.rmdir()
    plist = Playlist('../shared/playlist')
    plist.load()
