"""Constants for Smart Heating integration."""

DOMAIN = "smart_heating"
PLATFORMS = ["sensor", "binary_sensor", "number", "switch"]

# --- Config keys ---
CONF_ZONE_NAME = "zone_name"
CONF_SENSOR_TEMP = "sensor_temp"
CONF_SENSOR_EXT = "sensor_ext"
CONF_CLIMATE_ENTITY = "climate_entity"
CONF_SCHEDULE_ENTITY = "schedule_entity"
CONF_WEATHER_ENTITY = "weather_entity"

# Paramètres
CONF_SAFETY_MARGIN = "safety_margin"
CONF_WARMUP_IGNORE_MIN = "warmup_ignore_min"
CONF_ANTI_SHORT_CYCLE = "anti_short_cycle"
CONF_MIN_OFF_TIME_SEC = "min_off_time_sec"
CONF_MIN_SESSIONS = "min_sessions"

# LLM
CONF_LLM_PROVIDER = "llm_provider"
CONF_LLM_API_KEY = "llm_api_key"
CONF_LLM_MODEL = "llm_model"
CONF_LLM_URL = "llm_url"
CONF_LLM_FREQUENCY = "llm_frequency"
CONF_LLM_HOURS = "llm_hours"

# --- LLM Providers ---
LLM_NONE = "none"
LLM_OPENAI = "openai"
LLM_ANTHROPIC = "anthropic"
LLM_OLLAMA = "ollama"
LLM_HA_CONVERSATION = "ha_conversation"

LLM_PROVIDERS = {
    LLM_NONE: "Aucune IA (algorithme pur)",
    LLM_OPENAI: "OpenAI (GPT-4o-mini, GPT-4o, ...)",
    LLM_ANTHROPIC: "Anthropic (Claude Sonnet, Opus, Haiku, ...)",
    LLM_OLLAMA: "Ollama (local: Llama3, Mistral, ...)",
    LLM_HA_CONVERSATION: "HA Conversation (agent configuré dans HA)",
}

LLM_MODELS = {
    LLM_OPENAI: ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    LLM_ANTHROPIC: [
        "claude-sonnet-4-5-20250514",
        "claude-haiku-4-5-20251001",
    ],
    LLM_OLLAMA: ["llama3", "llama3.1", "mistral", "mixtral", "phi3", "gemma2"],
}

# --- Defaults ---
DEFAULT_SAFETY_MARGIN = 1.15
DEFAULT_WARMUP_IGNORE_MIN = 0
DEFAULT_MIN_OFF_TIME_SEC = 1800
DEFAULT_MIN_SESSIONS = 3
DEFAULT_LLM_FREQUENCY = "2x_daily"
DEFAULT_LLM_HOURS = [9, 16]
DEFAULT_CYCLE_MIN = 15  # minutes - durée cycle TPI

# --- Storage ---
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "smart_heating"
MAX_SESSIONS = 100
MAX_LLM_HISTORY = 7  # jours

# --- Session ---
MIN_SESSION_DURATION_SEC = 300  # 5 min
MIN_SESSION_DELTA_TEMP = 0.3  # °C

# --- States ---
STATE_LEARNING = "learning"
STATE_READY = "ready"
STATE_ANTICIPATING = "anticipating"
STATE_IDLE = "idle"
