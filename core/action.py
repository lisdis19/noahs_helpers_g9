from dataclasses import dataclass

from core.animal import Animal


@dataclass(frozen=True)
class Release:
    animal: Animal


@dataclass(frozen=True)
class Obtain:
    animal: Animal


@dataclass(frozen=True)
class Move:
    x: float
    y: float


Action = Release | Obtain | Move
