"""Config flow for Smart Heating integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.const import CONF_NAME

from .const import (
    DOMAIN,
    CONF_ZONE_NAME,
    CONF_SENSOR_TEMP,
    CONF_SENSOR_EXT,
    CONF_CLIMATE_ENTITY,
    CONF_SCHEDULE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_SAFETY_MARGIN,
    CONF_WARMUP_IGNORE_MIN,
    CONF_ANTI_SHORT_CYCLE,
    CONF_MIN_OFF_TIME_SEC,
    CONF_MIN_SESSIONS,
    CONF_LLM_PROVIDER,
    CONF_LLM_API_KEY,
    CONF_LLM_MODEL,
    CONF_LLM_URL,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_WARMUP_IGNORE_MIN,
    DEFAULT_MIN_OFF_TIME_SEC,
    DEFAULT_MIN_SESSIONS,
    LLM_NONE,
    LLM_OPENAI,
    LLM_ANTHROPIC,
    LLM_OLLAMA,
    LLM_HA_CONVERSATION,
    LLM_PROVIDERS,
    LLM_MODELS,
)

_LOGGER = logging.getLogger(__name__)


class SmartHeatingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Heating."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: Zone configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check zone name is unique
            await self.async_set_unique_id(f"smart_heating_{user_input[CONF_ZONE_NAME]}")
            self._abort_if_unique_id_configured()

            self._data.update(user_input)
            return await self.async_step_schedule()

        schema = vol.Schema(
            {
                vol.Required(CONF_ZONE_NAME): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Required(CONF_SENSOR_TEMP): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Required(CONF_SENSOR_EXT): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Required(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "title": "Zone de chauffage",
            },
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: Schedule & weather."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_params()

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCHEDULE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
            }
        )

        return self.async_show_form(
            step_id="schedule",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 3: Parameters."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_llm()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SAFETY_MARGIN,
                    default=int(DEFAULT_SAFETY_MARGIN * 100),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=100, max=150, step=5, unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_WARMUP_IGNORE_MIN,
                    default=DEFAULT_WARMUP_IGNORE_MIN,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_ANTI_SHORT_CYCLE,
                    default=False,
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MIN_OFF_TIME_SEC,
                    default=DEFAULT_MIN_OFF_TIME_SEC // 60,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10, max=120, step=5, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MIN_SESSIONS,
                    default=DEFAULT_MIN_SESSIONS,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=20, step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="params",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_llm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 4: LLM provider selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            provider = user_input.get(CONF_LLM_PROVIDER, LLM_NONE)
            self._data.update(user_input)

            if provider in (LLM_OPENAI, LLM_ANTHROPIC):
                return await self.async_step_llm_cloud()
            elif provider == LLM_OLLAMA:
                return await self.async_step_llm_ollama()
            elif provider == LLM_HA_CONVERSATION:
                return await self.async_step_llm_ha()
            else:
                return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LLM_PROVIDER,
                    default=LLM_NONE,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=k, label=v)
                            for k, v in LLM_PROVIDERS.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="llm",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_llm_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 4b: Cloud LLM config (OpenAI / Anthropic)."""
        errors: dict[str, str] = {}
        provider = self._data.get(CONF_LLM_PROVIDER, LLM_OPENAI)

        if user_input is not None:
            if not user_input.get(CONF_LLM_API_KEY):
                errors[CONF_LLM_API_KEY] = "api_key_required"
            else:
                self._data.update(user_input)
                return self._create_entry()

        models = LLM_MODELS.get(provider, ["gpt-4o-mini"])
        default_model = models[0] if models else "gpt-4o-mini"

        schema = vol.Schema(
            {
                vol.Required(CONF_LLM_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    )
                ),
                vol.Required(
                    CONF_LLM_MODEL,
                    default=default_model,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=models,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )

        provider_name = "OpenAI" if provider == LLM_OPENAI else "Anthropic"
        return self.async_show_form(
            step_id="llm_cloud",
            data_schema=schema,
            errors=errors,
            description_placeholders={"provider": provider_name},
        )

    async def async_step_llm_ollama(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 4b: Ollama config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        models = LLM_MODELS.get(LLM_OLLAMA, ["llama3"])

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LLM_URL,
                    default="http://localhost:11434",
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Required(
                    CONF_LLM_MODEL,
                    default="llama3",
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=models,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        custom_value=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="llm_ollama",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_llm_ha(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 4b: HA Conversation config."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        schema = vol.Schema(
            {
                vol.Optional("agent_id"): selector.ConversationAgentSelector(),
            }
        )

        return self.async_show_form(
            step_id="llm_ha",
            data_schema=schema,
            errors=errors,
        )

    def _create_entry(self) -> config_entries.ConfigFlowResult:
        """Create the config entry."""
        zone_name = self._data.get(CONF_ZONE_NAME, "zone")
        return self.async_create_entry(
            title=f"Smart Heating - {zone_name}",
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SmartHeatingOptionsFlow:
        """Get the options flow."""
        return SmartHeatingOptionsFlow(config_entry)


class SmartHeatingOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Heating."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SAFETY_MARGIN,
                    default=current.get(CONF_SAFETY_MARGIN, int(DEFAULT_SAFETY_MARGIN * 100)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=100, max=150, step=5, unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_WARMUP_IGNORE_MIN,
                    default=current.get(CONF_WARMUP_IGNORE_MIN, DEFAULT_WARMUP_IGNORE_MIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=30, step=1, unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MIN_SESSIONS,
                    default=current.get(CONF_MIN_SESSIONS, DEFAULT_MIN_SESSIONS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=20, step=1,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
