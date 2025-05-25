"""Reusable slot definitions for the appointment scheduler.

Each slot knows
    • its public name
    • which earlier slots it depends on
    • how to fetch its option list, given the conversation context
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeAlias


# Type alias for context dictionary
Context: TypeAlias = dict[str, str | None]


@dataclass(frozen=True, slots=True)
class Slot:
    name: str
    dependencies: Sequence[str]
    options_fn: Callable[[Context], list[str]]

    def options(self, ctx: Context) -> list[str]:
        return self.options_fn(ctx)


# --------------------------------------------------------------------------- #
#  Default slot chain used by GraphManager
# --------------------------------------------------------------------------- #
def build_default_slots(api) -> list[Slot]:
    """Return the canonical hospital → specialty → doctor → timeslot chain."""

    def hospital_options(_: Context) -> list[str]:
        return api.get_hospitals()

    def specialty_options(ctx: Context) -> list[str]:
        if hosp := ctx.get("hospital"):
            return api.get_specialties(hosp)
        return []

    def doctor_options(ctx: Context) -> list[str]:
        hosp, spec = ctx.get("hospital"), ctx.get("specialty")
        if hosp and spec:
            return api.get_doctors(hosp, spec)
        return []

    def timeslot_options(ctx: Context) -> list[str]:
        hosp, spec, doc = (
            ctx.get("hospital"),
            ctx.get("specialty"),
            ctx.get("doctor"),
        )
        if hosp and spec and doc:
            return api.get_appointment_slots(hosp, spec, doc)
        return []

    return [
        Slot("hospital", [], hospital_options),
        Slot("specialty", ["hospital"], specialty_options),
        Slot("doctor", ["hospital", "specialty"], doctor_options),
        Slot("timeslot", ["hospital", "specialty", "doctor"], timeslot_options),
    ]
