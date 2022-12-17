"""gestione delle playlist."""
import sys
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import yaml
from loguru import logger


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
    tipo: Optional[PlaylistElementType]  # se None, non verrà visualizzato questo elemento
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
            return {"name": self.path.name, "durata": str(self.durata)}
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


class SafeLoaderIgnoreUnknown(yaml.SafeLoader): # pylint: disable=too-few-public-methods
    """Loader che non genera errori in caso di tag sconosciuti (ma registra l'errore nel log)."""

    def ignore_unknown(self, node):
        """Ignora i tag sconosciuti senza generare errore."""
        logger.warning(f"tag sconosciuto durante il parsing: {node}")


SafeLoaderIgnoreUnknown.add_constructor(None, SafeLoaderIgnoreUnknown.ignore_unknown)  # type: ignore


class Playlist:
    """Classe che descrive una playlist di elementi."""

    playlist_path: Optional[Path] = None
    data: list[PlaylistElement] = []

    def __init__(self, playlist_path: Optional[str] = None):
        """crea una playlist vuota oppure, se è stato fornito un path, ne verifica il contenuto per popolare la playlist
        stessa."""
        if playlist_path is not None:
            self.playlist_path = Path(playlist_path)
            self.data = self.load()

    @logger.catch
    def save(self):
        """salva la playlist nella cartella indicata in [[playlist_path]]."""
        with open(self.playlist_path / "playlist.yaml", "w", encoding="utf-8") as outfile:
            yaml.dump(map(lambda x: x.serialize(), self.data), outfile, default_flow_style=False)

    def reload(self, playlist_path=None) -> bool:
        """ricarica la playlist, eventualmente cambiando il path, e restituisce un booleano se qualcosa è cambiato."""
        if playlist_path is not None:
            self.playlist_path = Path(playlist_path)
        newdata = self.load()
        changed = self.equals(newdata)
        if changed:
            self.data = newdata
        return changed

    def equals(self, newdata):
        """confronta l'oggetto con un altro."""
        if self.data is None or newdata is None or len(self.data) != len(newdata):
            return False
        for i, elemento in enumerate(self.data):
            if elemento != newdata[i]:
                return False
        return True

    @logger.catch
    def load(self):
        """Carica una playlist dalla cartella indicata in [[playlist_path]]."""

        logger.debug("carico playlist")
        if self.playlist_path is not None and self.playlist_path.is_dir():
            # verifico che esista la cartella indicata in [[playlist_path]]
            data = None
            with open(self.playlist_path / "playlist.yaml", "r", encoding="utf-8") as playlistfile:
                # leggo la playlist dalla cartella indicata in [[playlist_path]]
                try:
                    lista = yaml.load(playlistfile, Loader=SafeLoaderIgnoreUnknown)  # nosec B506
                    data = []
                    for elemento in lista:
                        if isinstance(elemento, dict):
                            durata = elemento["durata"] if "durata" in elemento.keys() else None
                            new_item = PlaylistElement(
                                elemento["name"], relative_to_dir=self.playlist_path, durata=durata
                            )
                        else:
                            new_item = PlaylistElement(elemento, relative_to_dir=self.playlist_path)
                        if new_item.is_valid():
                            data.append(new_item)
                        else:
                            logger.warning(f"non posso aggiungere l'elemento {new_item} perchè non è valido")
                except yaml.YAMLError:
                    logger.exception("playlist non valida")
            if data is None:
                # se non la trovo, leggo tutti i file nella cartella condivisa, in ordine alfabetico, e registro il log
                for elemento in sorted(
                    [path.as_posix() for path in self.playlist_path.glob("*.[jpeg][jpg][png][mp4]")]
                ):
                    new_item = PlaylistElement(elemento, relative_to_dir=self.playlist_path)
                    data.append(new_item)
        else:
            # se non la trovo, esco.
            if self.playlist_path is None:
                logger.error("la cartella che contiene la playlist non esiste, è nulla")
            else:
                path_cercato = (self.playlist_path / "playlist.yaml").resolve()
                logger.error(f"la cartella che contiene la playlist non esiste, ho cercato in: {path_cercato}")
            sys.exit(1001)
        return data


class PlaylistPlayer(Playlist):
    """Playlist che tiene traccia dell'elemento visualizzato."""

    idx: int = -1

    def reload(self, playlist_path=None) -> bool:
        self.idx = -1
        return super().reload(playlist_path)

    def next(self) -> Optional[PlaylistElement]:
        """restituisce il termine successivo nella playlist."""
        if self.data is None or len(self.data) == 0:
            # nessun elemento, termino qui
            return None

        self.idx = self.idx + 1 if self.idx < len(self.data) else 0
        return self.data[self.idx]
