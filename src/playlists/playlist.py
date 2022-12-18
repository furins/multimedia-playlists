"""gestione delle playlist."""
import importlib.util
import os
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Union

import yaml
from loguru import logger


class MissingPlaylistFolder(Exception):
    """Eccezione sollevata quando non è possibile accedere al file della playlist"""

class WrongPlaylistFolderPath(Exception):
    """Eccezione sollevata quando non è possibile creare il file della playlist nella posizione indicata"""

class PlaylistElementType(Enum):
    """Possibili tipi di file/url gestibili dal sistema."""

    IMMAGINE = 1
    VIDEO = 2
    STREAM = 3


class PlaylistElement:
    """
    Elemento di una playlist. La playlist può includere.

    - immagini statiche png e jpg (con durata, default forever)
    - stream
    - video mp4

    """

    path: Union[str, Path]  # path al file/URL
    # se None, non verrà visualizzato questo elemento
    tipo: Optional[PlaylistElementType]
    durata: Optional[float]  # in secondi, se pari a None ha durata infinita

    def __init__(self, path: str, relative_to_dir: Optional[Path] = None, durata: Optional[float] = None):
        """inizializza l'oggetto."""
        self.tipo = self.classifica(path)
        if self.tipo is not PlaylistElementType.STREAM:
            if relative_to_dir is not None:
                self.path = (relative_to_dir / path).resolve()
            else:
                self.path = Path(path).resolve()
        else:
            self.path = path
        self.durata = durata

    def is_valid(self) -> bool:
        """verifica se l'oggetto esiste realmente (non controlla gli stream, in realtà)"""
        if self.tipo is None:
            return False
        if self.tipo == PlaylistElementType.STREAM:
            return True
        return Path(self.source()).is_file()

    def source(self) -> str:
        """restituisce il path dell'oggetto."""
        if isinstance(self.path, Path):
            return self.path.as_posix()
        return self.path

    def serialize(self) -> Union[str, dict[str, str]]:
        """restituisce un oggetto serializzabile."""
        if self.durata is not None:
            return {"name": str(self.path.name), "durata": str(self.durata)}
        return self.path.name

    @staticmethod
    def classifica(path: str):
        """
        classifica il path ricevuto e restituisce un PlaylistElementType specifico.

        Args:
            path (str): il path da analizzare

        Returns:
            _type_: il PlaylistElementType identificato, o None se non riconosciuto

        """
        if path.startswith("http"):
            return PlaylistElementType.STREAM
        if path.endswith("png") or path.endswith("jpg") or path.endswith("jpeg"):
            return PlaylistElementType.IMMAGINE
        if path.endswith("mp4"):
            return PlaylistElementType.VIDEO
        return None

    def __cmp__(self, other):
        if not isinstance(other, PlaylistElement):
            # don't attempt to compare against unrelated types
            return NotImplemented
        if isinstance(self.path, Path):
            if isinstance(other, Path):
                path_uguali = self.path.as_posix() == other.path.as_posix()
            else:
                path_uguali = self.path.as_posix() == other.path
        else:
            if isinstance(other, Path):
                path_uguali = self.path == other.path.as_posix()
            else:
                path_uguali = self.path == other.path
        return path_uguali and self.durata == other.durata


class SafeLoaderIgnoreUnknown(yaml.SafeLoader):  # pylint: disable=too-few-public-methods
    """Loader che non genera errori in caso di tag sconosciuti (ma registra l'errore nel log)."""

    def ignore_unknown(self, node):
        """Ignora i tag sconosciuti senza generare errore."""
        logger.warning(f"tag sconosciuto durante il parsing: {node}")


SafeLoaderIgnoreUnknown.add_constructor(None, SafeLoaderIgnoreUnknown.ignore_unknown)  # type: ignore


class Playlist():
    """Classe che descrive una playlist di elementi."""

    playlist_path: Optional[Path] = None
    data: list[PlaylistElement] = []

    def __init__(self, playlist_path: Optional[str] = None, on_error: Callable = None):
        """crea una playlist vuota oppure, se è stato fornito un path, ne verifica il contenuto per popolare la playlist
        stessa."""
        self.on_error = on_error if on_error is not None else self.default_on_error
        if playlist_path is not None:
            self.playlist_path = Path(playlist_path)
            self.load()

    @logger.catch
    def save(self):
        """salva la playlist nella cartella indicata in [[playlist_path]]."""
        with open(self.playlist_path / "playlist.yaml", "w", encoding="utf-8") as outfile:
            yaml.dump(list(map(lambda x: x.serialize(), self.data)),
                      outfile, default_flow_style=False)

    def reload(self, playlist_path=None):
        """Ricarica la playlist quando viene cambiato il path."""
        if playlist_path is not None:
            self.playlist_path = Path(playlist_path)
        self.load()

    def on_change(self):
        """Method to be called when the content of the folder change."""
        self.load()

    def load(self):
        """Ensures that a playlist exists, and loads it.

        Raises `MissingPlaylistFolder` if `self.playlist_path` is None
        Raises `WrongPlaylistFolderPath` if `self.playlist_path` is unreachable
        """
        logger.debug(f"playlist load: {self.playlist_path}")

        if self.playlist_path is None:
            logger.error("la cartella che contiene la playlist non esiste, è nulla")
            raise MissingPlaylistFolder

        if not self.playlist_path.is_dir():
            # abbiamo un path, ma non esiste la cartella corrispondente
            path_cercato = (self.playlist_path).resolve()
            try:
                self.playlist_path.mkdir(parents=True, exist_ok=True)
                logger.warning(f"la cartella che contiene la playlist non esisteva, l'ho creata in: {path_cercato}")
                # in ogni caso la playlist sarà vuota a questo punto, quindi carico un contenuto di default

                src = Path(importlib.util.find_spec("playlists").origin).parents[0] / 'default_playlist'
                logger.debug(f"cerco contenuti di default in: {src}")
                shutil.copy2(os.path.join(src, 'playlist.yaml'), self.playlist_path)
                shutil.copy2(os.path.join(src, 'empty_playlist.png'), self.playlist_path)

            except FileNotFoundError as err:
                logger.error(f"Esco in quanto è impossible creare la cartella in questa posizione: {path_cercato}")
                raise WrongPlaylistFolderPath from err
        self.populate_playlist()

    def populate_playlist(self) :
        """Populate a playlist from the contents of `self.playlist_path`."""
        playlistfile = (self.playlist_path or Path('.')) / "playlist.yaml"
        if playlistfile.is_file() :
            self.load_playlist(playlistfile)
        else:
            data = []
            filelist = sorted([path.as_posix() for path in self.playlist_path.glob(
                            "*.[jpeg][jpg][png][mp4]")])
            for elemento in filelist:
                new_item = PlaylistElement(
                    elemento, relative_to_dir=self.playlist_path)
                data.append(new_item)
            self.data = data
            self.save()


    def load_playlist(self, playlistfilename:Path):
        """Loads a playlist from a file into `self.data`."""
        with open(playlistfilename, "r", encoding="utf-8") as playlistfile:
            # leggo la playlist dalla cartella indicata in [[playlist_path]]
            data = []
            try:
                lista = yaml.load(
                    playlistfile, Loader=SafeLoaderIgnoreUnknown)  # nosec B506
                for elemento in lista:
                    if isinstance(elemento, dict):
                        durata = elemento["durata"] if "durata" in elemento.keys(
                        ) else None
                        new_item = PlaylistElement(
                            elemento["name"], relative_to_dir=self.playlist_path, durata=durata
                        )
                    else:
                        new_item = PlaylistElement(
                            elemento, relative_to_dir=self.playlist_path)
                    if new_item.is_valid():
                        logger.debug(f"carico l'elemento {new_item.path}")
                        data.append(new_item)
                    else:
                        logger.warning(
                            f"non posso aggiungere l'elemento {new_item} perchè non è valido")
            except yaml.YAMLError:
                logger.exception("playlist non valida")
            self.data = data


    def default_on_error(self, errorcode: int = 1):
        """Method called when a fatal error occours."""
        sys.exit(errorcode)


class PlaylistPlayer(Playlist):
    """Playlist che tiene traccia dell'elemento visualizzato."""

    idx: int = -1

    def reload(self, playlist_path=None) -> bool:
        """ricarica la playlist"""
        self.idx = -1
        return super().reload(playlist_path)

    def next(self) -> Optional[PlaylistElement]:
        """restituisce il termine successivo nella playlist."""
        if self.data is None or len(self.data) == 0:
            # nessun elemento, termino qui
            return None

        self.idx = self.idx + 1 if self.idx < len(self.data) else 0
        return self.data[self.idx]
