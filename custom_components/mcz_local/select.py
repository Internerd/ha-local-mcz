"""Fan selects for the MCZ Maestro (local) integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator
from .entity import MczEntity
from .protocol import (
    FAN_AUTO,
    FAN_OFF,
    INFO_FAN_DUCT_1,
    INFO_FAN_DUCT_2,
    INFO_FAN_FRONT,
    PARAM_FAN_DUCT_1,
    PARAM_FAN_DUCT_2,
    PARAM_FAN_FRONT,
    PARAMS_FAN_DUCT_1_PRESENT,
    PARAMS_FAN_DUCT_2_PRESENT,
    PARAMS_FAN_FRONT_PRESENT,
)

PARALLEL_UPDATES = 1

FAN_OPTIONS: dict[str, int] = {
    "off": FAN_OFF,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "auto": FAN_AUTO,
}
FAN_VALUES = {value: option for option, value in FAN_OPTIONS.items()}


@dataclass(frozen=True, kw_only=True)
class MczFanDescription(SelectEntityDescription):
    """Describes one of the up to three room fans."""

    param_id: int
    info_index: int
    presence_index: int


FANS: tuple[MczFanDescription, ...] = (
    MczFanDescription(
        key="fan_front",
        translation_key="fan_front",
        param_id=PARAM_FAN_FRONT,
        info_index=INFO_FAN_FRONT,
        presence_index=PARAMS_FAN_FRONT_PRESENT,
    ),
    MczFanDescription(
        key="fan_duct_1",
        translation_key="fan_duct_1",
        param_id=PARAM_FAN_DUCT_1,
        info_index=INFO_FAN_DUCT_1,
        presence_index=PARAMS_FAN_DUCT_1_PRESENT,
    ),
    MczFanDescription(
        key="fan_duct_2",
        translation_key="fan_duct_2",
        param_id=PARAM_FAN_DUCT_2,
        info_index=INFO_FAN_DUCT_2,
        presence_index=PARAMS_FAN_DUCT_2_PRESENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up fan selects for the fans the stove reports as installed."""
    coordinator = entry.runtime_data
    params = coordinator.data.parameters
    async_add_entities(
        MczFanSelect(coordinator, description)
        for description in FANS
        if params.fan_present(description.presence_index)
    )


class MczFanSelect(MczEntity, SelectEntity):
    """Fan speed: off, 1..5 or auto."""

    entity_description: MczFanDescription
    _attr_options = list(FAN_OPTIONS)

    def __init__(
        self, coordinator: MczCoordinator, description: MczFanDescription
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        """Return the current fan speed."""
        return FAN_VALUES.get(
            self.coordinator.data.info.get(self.entity_description.info_index)
        )

    async def async_select_option(self, option: str) -> None:
        """Set the fan speed."""
        await self.coordinator.async_write(
            self.entity_description.param_id, FAN_OPTIONS[option]
        )
