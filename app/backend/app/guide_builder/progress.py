"""Progress events while a guide is built, so the knitter's page can show what is happening at every moment.

The builder calls `report(event)` at each stage. The app stores the latest events with the job, and the page polls
them (and refreshes the moment the page becomes visible again), so after the iPad sleeps the page never looks frozen.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable

STAGES = [
    ("read", "Reading the pattern"),
    ("pictures", "Reading pages that are pictures"),
    ("outline", "Finding sizes, yarn and sections"),
    ("sections", "Writing the steps"),
    ("checks", "Checking every number against the pattern"),
    ("repair", "Taking a second look at a few steps"),
    ("done", "Ready to check"),
]
STAGE_TITLES = dict(STAGES)


@dataclass
class Event:
    stage: str                 # one of STAGES
    message: str               # plain English for the knitter, e.g. "Writing the steps: Sleeves (3 of 6)"
    done: int = 0              # units finished within the stage (pages, sections)
    total: int = 0             # units in the stage, 0 when not countable
    detail: dict = field(default_factory=dict)   # e.g. {"section": "Sleeves", "state": "finished"}
    at: float = field(default_factory=time.time)

    @property
    def percent(self) -> int:
        """Overall progress, 0 to 100, for a progress bar. Each stage owns a share; sections take most of it."""
        weights = {"read": 5, "pictures": 15, "outline": 15, "sections": 50, "checks": 10, "repair": 5, "done": 0}
        order = [s for s, _ in STAGES]
        before = sum(weights[s] for s in order[: order.index(self.stage)])
        within = weights[self.stage] * (self.done / self.total) if self.total else 0
        return min(100, int(before + within)) if self.stage != "done" else 100

    def as_dict(self) -> dict:
        d = asdict(self)
        d["percent"] = self.percent
        d["title"] = STAGE_TITLES.get(self.stage, self.stage)
        return d


Reporter = Callable[[Event], None]


def silent(_: Event) -> None:
    pass
