
from dataclasses import dataclass, field

@dataclass()
class Path:
    cids: list
    pix_per_mm:  float
    power:  int
    feed:   int
    cross:  int
    points: list
    scale:  float


