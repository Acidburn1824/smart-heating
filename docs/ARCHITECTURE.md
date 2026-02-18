# 🧠 Smart Heating - Architecture

## Vision

Custom component HACS pour Home Assistant qui ajoute une anticipation intelligente
du chauffage basée sur l'apprentissage de l'inertie thermique et l'IA.

Compatible avec Versatile Thermostat, les entités climate natives, ou tout thermostat HA.

## Structure du projet

```
custom_components/smart_heating/
├── __init__.py              # Setup intégration + platforms
├── manifest.json            # Metadata HACS
├── config_flow.py           # Configuration UI (flux étape par étape)
├── const.py                 # Constantes
├── strings.json             # Traductions EN
├── translations/
│   └── fr.json              # Traductions FR
│
├── coordinator.py           # DataUpdateCoordinator - cerveau principal
├── thermal_model.py         # Modèle d'inertie thermique (apprentissage)
├── anticipation.py          # Moteur d'anticipation (quand démarrer)
├── schedule_parser.py       # Lecture des schedules / presets
│
├── llm/                     # Providers LLM modulaires
│   ├── __init__.py          # Factory + base class
│   ├── base.py              # Classe abstraite LLMProvider
│   ├── openai_provider.py   # OpenAI (GPT-4o-mini, GPT-4o, etc.)
│   ├── anthropic_provider.py # Claude (claude-sonnet, opus, haiku)
│   ├── ollama_provider.py   # Ollama (local: llama3, mistral, etc.)
│   ├── ha_conversation.py   # Via l'intégration HA Conversation (Google, OpenAI, etc.)
│   └── none_provider.py     # Mode sans IA (algorithme pur)
│
├── sensor.py                # Sensors exposés dans HA
├── climate.py               # (optionnel) climate wrapper avec anticipation
├── number.py                # Input numbers (marge, anti-cycle, etc.)
├── switch.py                # Switches (activer/désactiver anticipation)
├── binary_sensor.py         # Binary sensors (anticipation active, anti-cycle)
├── diagnostics.py           # Diagnostics pour debug
└── services.yaml            # Actions/services custom
```

## Flux de données

```
                          ┌──────────────┐
                          │   Schedule    │ (sensor, scheduler, preset change)
                          └──────┬───────┘
                                 │
                                 ▼
┌──────────────┐    ┌───────────────────────┐    ┌──────────────┐
│  Temp Room   │───▶│    SmartHeating        │◀───│  Temp Ext    │
│  (sensor)    │    │    Coordinator         │    │  (sensor)    │
└──────────────┘    │                       │    └──────────────┘
                    │  ┌─────────────────┐  │
                    │  │ Thermal Model   │  │    ┌──────────────┐
                    │  │ (inertie)       │  │◀───│  Weather     │
                    │  └─────────────────┘  │    │  (forecast)  │
                    │                       │    └──────────────┘
                    │  ┌─────────────────┐  │
                    │  │ Anticipation    │  │    ┌──────────────┐
                    │  │ Engine          │  │───▶│  Climate      │
                    │  └─────────────────┘  │    │  (VTherm/     │
                    │                       │    │   Netatmo/    │
                    │  ┌─────────────────┐  │    │   any)        │
                    │  │ LLM Provider    │  │    └──────────────┘
                    │  │ (optionnel)     │  │
                    │  └─────────────────┘  │
                    └───────────────────────┘
```

## Providers LLM

### Interface commune (base.py)

```python
class LLMProvider(ABC):
    @abstractmethod
    async def async_get_adjustment(
        self,
        zone_name: str,
        thermal_data: dict,      # inertie, sessions, vitesses
        weather_forecast: dict,   # prévisions météo
        current_state: dict,      # temp int, ext, consigne
        context: str,             # "morning" | "evening"
    ) -> LLMResponse:
        """Retourne un ajustement de marge + conseil texte."""
```

### LLMResponse

```python
@dataclass
class LLMResponse:
    margin_adjustment: float   # ex: 0.05 = +5% de marge
    confidence: float          # 0.0 - 1.0
    reasoning: str             # explication courte
    raw_response: str          # réponse brute pour debug
```

### Providers disponibles

| Provider | Config | Coût | Latence | Qualité |
|----------|--------|------|---------|---------|
| **None** | Rien | 0€ | 0ms | Algo pur, pas d'IA |
| **Ollama** | URL serveur | 0€ | 1-5s | Bon avec llama3/mistral |
| **OpenAI** | Clé API | ~0.01€/j | 1-3s | Excellent |
| **Anthropic** | Clé API | ~0.01€/j | 1-3s | Excellent |
| **HA Conversation** | Intégration HA | Dépend | Variable | Dépend du backend |

## Config Flow UI

### Étape 1 : Zone
- Nom de la zone
- Capteur température intérieure
- Capteur température extérieure
- Entité climate (VTherm ou autre)

### Étape 2 : Schedule
- Source de consigne (sensor schedule / presets VTherm / manual)
- Entité weather (optionnel)

### Étape 3 : Paramètres
- Marge de sécurité (default 15%)
- Warmup ignore minutes (poêle: 12, radiateur: 0)
- Anti short cycle (oui/non + durée)
- Minimum sessions avant anticipation (default 3)

### Étape 4 : IA (optionnel)
- Provider : None / OpenAI / Anthropic / Ollama / HA Conversation
- Selon le provider:
  - OpenAI: clé API + modèle (gpt-4o-mini, gpt-4o)
  - Anthropic: clé API + modèle (claude-sonnet-4-5-20250514, etc.)
  - Ollama: URL + modèle (llama3, mistral, etc.)
  - HA Conversation: sélection de l'agent configuré
- Fréquence appels (1x/jour, 2x/jour)
- Heure(s) d'appel

## Sensors créés par zone

| Sensor | Description |
|--------|-------------|
| `sensor.smart_heating_{zone}_state` | État (learning/ready/anticipating/idle) |
| `sensor.smart_heating_{zone}_sessions` | Nombre de sessions collectées |
| `sensor.smart_heating_{zone}_min_per_deg` | Minutes par degré |
| `sensor.smart_heating_{zone}_speed` | Vitesse montée °C/min |
| `sensor.smart_heating_{zone}_optimal_start` | Heure de démarrage optimale |
| `sensor.smart_heating_{zone}_anticipation` | Minutes d'anticipation calculées |
| `sensor.smart_heating_{zone}_llm_advice` | Dernier conseil IA |
| `binary_sensor.smart_heating_{zone}_anticipating` | Anticipation en cours |
| `binary_sensor.smart_heating_{zone}_anti_cycle` | Anti-cycle actif |
| `number.smart_heating_{zone}_margin` | Marge de sécurité ajustable |
| `switch.smart_heating_{zone}_enabled` | Activer/désactiver |

## Stockage des données

Fichier JSON par zone dans `/config/.storage/smart_heating_{zone}.json`
- Sessions de chauffe (max 100, FIFO)
- Modèle d'inertie calculé
- Historique LLM (7 derniers jours)
- Paramètres calibrés
