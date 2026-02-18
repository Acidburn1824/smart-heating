# 🧠 Smart Heating

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://www.home-assistant.io/)

**Anticipation intelligente du chauffage pour Home Assistant**

Smart Heating apprend l'inertie thermique de votre logement et anticipe le démarrage du chauffage pour atteindre la température souhaitée au bon moment.

Compatible avec **Versatile Thermostat**, **Netatmo**, ou toute entité `climate` Home Assistant.

## ✨ Fonctionnalités

- 📊 **Apprentissage automatique** de l'inertie thermique (minutes/°C) par zone
- ⏰ **Anticipation** du démarrage pour être à température à l'heure programmée
- 🤖 **IA optionnelle** pour ajuster la marge selon la météo
- 🔥 **Protection anti-cycles courts** pour poêles à granulés
- 📈 **Sensors** complets pour dashboard et automations
- 🎛️ **Ajustement en temps réel** de la marge et des paramètres

## 🤖 Fournisseurs IA supportés

| Provider | Type | Coût estimé |
|----------|------|-------------|
| **Aucun** | Algorithme pur | Gratuit |
| **Ollama** | IA locale (Llama3, Mistral...) | Gratuit |
| **OpenAI** | GPT-4o-mini, GPT-4o... | ~0.01€/jour |
| **Anthropic** | Claude Sonnet, Haiku... | ~0.01€/jour |
| **HA Conversation** | Agent configuré dans HA | Variable |

L'IA est **optionnelle** — l'algorithme fonctionne très bien sans. L'IA affine les marges selon les prévisions météo.

## 📦 Installation

### HACS (recommandé)

1. Ouvrir HACS → Intégrations → Menu ⋮ → Dépôts personnalisés
2. URL : `https://github.com/Acidburn1824/smart-heating`
3. Catégorie : Intégration
4. Télécharger et redémarrer HA

### Manuel

Copier `custom_components/smart_heating/` dans votre dossier `config/custom_components/`

## ⚙️ Configuration

Paramètres → Intégrations → Ajouter → **Smart Heating**

Le flux de configuration en 4 étapes :

1. **Zone** : nom, capteurs température, entité climate
2. **Planning** : sensor de schedule, entité météo
3. **Paramètres** : marge, warmup, anti-cycle, sessions minimum
4. **IA** : choix du provider (optionnel)

## 📊 Entités créées

Par zone, Smart Heating crée :

| Entité | Description |
|--------|-------------|
| `sensor.smart_heating_*_state` | État (learning/ready/anticipating) |
| `sensor.smart_heating_*_sessions` | Nombre de sessions |
| `sensor.smart_heating_*_min_per_deg` | Minutes par degré |
| `sensor.smart_heating_*_speed` | Vitesse de montée °C/min |
| `sensor.smart_heating_*_anticipation` | Minutes d'anticipation |
| `sensor.smart_heating_*_llm_advice` | Conseil IA |
| `sensor.smart_heating_*_effective_margin` | Marge effective (base + IA) |
| `binary_sensor.smart_heating_*_anticipating` | Anticipation en cours |
| `binary_sensor.smart_heating_*_anti_cycle` | Anti-cycle actif |
| `switch.smart_heating_*_enabled` | Activer/Désactiver |
| `switch.smart_heating_*_llm_enabled` | IA activée |
| `number.smart_heating_*_margin` | Marge ajustable |
| `number.smart_heating_*_warmup` | Temps montée en puissance |

## 🔧 Services

| Service | Description |
|---------|-------------|
| `smart_heating.force_llm_call` | Forcer un appel IA |
| `smart_heating.reset_sessions` | Réinitialiser les sessions |
| `smart_heating.recalculate` | Forcer un recalcul |

## 🏠 Cas d'usage

### Poêle à granulés
- `warmup_ignore_min: 12` (le poêle met ~12 min à monter en puissance)
- `anti_short_cycle: true` + `min_off_time_sec: 30` (protection 30 min)
- `safety_margin: 125%` (marge plus grande car inertie plus forte)

### Radiateur électrique
- `warmup_ignore_min: 0` (démarrage instantané)
- `anti_short_cycle: false`
- `safety_margin: 115%`

### Chauffage central (chaudière)
- `warmup_ignore_min: 5`
- `safety_margin: 120%`

## 📝 Licence

MIT
