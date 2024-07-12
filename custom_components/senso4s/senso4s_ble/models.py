"""Data model for Senso4s device."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Senso4sDevice:
    """Response data with information about the Senso4s device."""

    manufacturer: str = "Senso4s"
    hw_version: str = ""
    sw_version: str = ""
    model: str | None = None
    name: str = ""
    identifier: str = ""
    address: str = ""
    sensors: dict[str, str | float | None] = dataclasses.field(
        default_factory=lambda: {}
    )

    def friendly_name(self) -> str:
        """Generate a name for the device."""

        return f"{self.manufacturer} {self.model} ({self.identifier})"
