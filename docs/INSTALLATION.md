# 🚀 Smart Heating — Guide d'installation

## Prérequis

- Home Assistant ≥ 2024.1
- HACS installé
- Au moins une entité `climate` (VTherm, Netatmo, etc.)
- Un capteur température intérieure et extérieure
- (Optionnel) `schedule_state` HACS pour le planning
- (Optionnel) Entité `weather` pour les prévisions
- (Optionnel) Clé API OpenAI/Anthropic ou Ollama local

---

## Étape 1 — Copier les fichiers

### Option A : HACS (quand le repo sera public)

```
HACS → Intégrations → ⋮ → Dépôts personnalisés
URL : https://github.com/ton-user/smart-heating
Catégorie : Intégration
→ Installer → Redémarrer HA
```

### Option B : Installation manuelle (maintenant)

En SSH sur ton Proxmox :

```bash
# Accéder au conteneur HA (adapter l'ID)
pct enter 100

# Créer le dossier
mkdir -p /config/custom_components/smart_heating/llm

# Extraire l'archive (depuis le dossier où tu l'as mise)
cd /config/custom_components/
tar xzf /chemin/vers/smart_heating_v0.3.tar.gz \
  --strip-components=1 \
  custom_components/smart_heating/
```

Ou bien copier manuellement le dossier `custom_components/smart_heating/`
dans `/config/custom_components/` de ton Home Assistant.

**Vérification :**
```bash
ls -la /config/custom_components/smart_heating/
```

Tu dois voir :
```
__init__.py
anticipation.py
binary_sensor.py
config_flow.py
const.py
coordinator.py
diagnostics.py
feedback.py
manifest.json
number.py
schedule_parser.py
sensor.py
services.yaml
strings.json
switch.py
thermal_model.py
translations/
llm/
```

---

## Étape 2 — Installer les dépendances Python

Seulement si tu veux utiliser OpenAI ou Anthropic comme provider IA :

```bash
# Dans le conteneur HA
pip install openai anthropic --break-system-packages
```

> Si tu utilises Ollama ou "Aucune IA", pas besoin de dépendances.

---

## Étape 3 — Redémarrer Home Assistant

```
Paramètres → Système → Redémarrer
```

Ou en SSH :
```bash
ha core restart
```

---

## Étape 4 — Ajouter l'intégration

```
Paramètres → Appareils et intégrations → + Ajouter une intégration
→ Chercher "Smart Heating"
```

### Écran 1 : Zone de chauffage

| Champ | Valeur pour ton séjour |
|-------|------------------------|
| **Nom de la zone** | `sejour` |
| **Capteur temp intérieure** | `sensor.tdeg_sejour_netatmo` |
| **Capteur temp extérieure** | `sensor.tdeg_exterieur_temperature` |
| **Entité climate** | `climate.sejour_2` (Netatmo) |

> Plus tard avec VTherm : remplacer par `climate.vtherm_sejour_poele`

### Écran 2 : Planning & Météo

| Champ | Valeur |
|-------|--------|
| **Sensor de planning** | `sensor.schedule_sejour_consigne` |
| **Entité météo** | `weather.forecast_maison` |

### Écran 3 : Paramètres

| Champ | Séjour (poêle) | Chambre parents (radiateur) |
|-------|-----------------|----------------------------|
| **Marge de sécurité** | 125% | 115% |
| **Temps montée puissance** | 12 min | 0 min |
| **Anti-cycle courts** | ✅ Oui | ❌ Non |
| **Temps min arrêt** | 30 min | 15 min |
| **Sessions minimum** | 3 | 3 |

### Écran 4 : Fournisseur IA

Choisis selon ta préférence :

| Choix | Config |
|-------|--------|
| **Aucune IA** | Rien à configurer |
| **OpenAI** | Clé API + modèle `gpt-4o-mini` |
| **Anthropic** | Clé API + modèle `claude-sonnet-4-5-20250514` |
| **Ollama** | URL `http://ton-ip:11434` + modèle `llama3` |
| **HA Conversation** | Sélectionner l'agent configuré |

→ **Valider** → L'intégration est créée !

---

## Étape 5 — Vérifier les entités

Va dans **Outils de développement → États** et cherche `smart_heating` :

Tu dois voir ces entités :

```
sensor.smart_heating_sejour_state            → "learning"
sensor.smart_heating_sejour_sessions         → 0
sensor.smart_heating_sejour_min_per_deg      → (vide)
sensor.smart_heating_sejour_speed            → (vide)
sensor.smart_heating_sejour_anticipation     → (vide)
sensor.smart_heating_sejour_llm_advice       → "Aucun conseil"
sensor.smart_heating_sejour_effective_margin  → 125
sensor.smart_heating_sejour_schedule         → "19.5°C à 17:00" (ou similaire)
sensor.smart_heating_sejour_feedback         → "N/A"

binary_sensor.smart_heating_sejour_anticipating  → off
binary_sensor.smart_heating_sejour_anti_cycle    → off

switch.smart_heating_sejour_enabled          → on
switch.smart_heating_sejour_llm_enabled      → on

number.smart_heating_sejour_margin           → 125
number.smart_heating_sejour_warmup           → 12
```

**État "learning"** = normal ! Le système doit collecter 3 sessions de chauffe minimum.

---

## Étape 6 — Ajouter la 2ème zone (chambre parents)

Refaire l'étape 4 avec :

| Champ | Valeur |
|-------|--------|
| Nom de la zone | `parents` |
| Capteur temp intérieure | `sensor.tdeg_parents_temperature` |
| Capteur temp extérieure | `sensor.tdeg_exterieur_temperature` |
| Entité climate | `climate.vtherm_parents_2` |
| Sensor de planning | `sensor.schedule_parents_consigne_2` |
| Marge de sécurité | 115% |
| Temps montée puissance | 0 min |
| Anti-cycle courts | Non |

---

## Étape 7 — Dashboard (optionnel)

Exemple de carte pour suivre Smart Heating :

```yaml
type: vertical-stack
cards:
  # État
  - type: entities
    title: "🧠 Smart Heating Séjour"
    entities:
      - entity: sensor.smart_heating_sejour_state
        name: État
      - entity: sensor.smart_heating_sejour_sessions
        name: Sessions collectées
      - entity: sensor.smart_heating_sejour_min_per_deg
        name: Minutes par °C
      - entity: sensor.smart_heating_sejour_schedule
        name: Prochain créneau
      - entity: sensor.smart_heating_sejour_anticipation
        name: Anticipation
      - entity: binary_sensor.smart_heating_sejour_anticipating
        name: Anticipation active
      - entity: sensor.smart_heating_sejour_effective_margin
        name: Marge effective
      - entity: sensor.smart_heating_sejour_llm_advice
        name: Conseil IA
      - entity: sensor.smart_heating_sejour_feedback
        name: Performance

  # Contrôles
  - type: entities
    title: "🎛️ Contrôles"
    entities:
      - entity: switch.smart_heating_sejour_enabled
        name: Smart Heating activé
      - entity: switch.smart_heating_sejour_llm_enabled
        name: IA activée
      - entity: number.smart_heating_sejour_margin
        name: Marge de sécurité
      - entity: number.smart_heating_sejour_warmup
        name: Temps montée puissance
```

---

## Ce qui va se passer

### Jours 1-3 : Phase d'apprentissage
- L'état sera `learning`
- Le système **observe** chaque session de chauffe
- Il enregistre : temp départ, temp fin, durée, temp extérieure
- Il calcule la vitesse de montée (°C/min) automatiquement
- **Pas d'anticipation pendant cette phase** — le chauffage fonctionne normalement

### Après 3+ sessions : Phase active
- L'état passe à `ready`
- Le schedule parser détecte la prochaine transition (ex: 17h → comfort 19.5°C)
- Le modèle calcule "il faut 26 min pour monter de 3.5°C"
- L'IA ajuste la marge selon la météo (si activée)
- **L'anticipation démarre automatiquement** X minutes avant la transition
- Le climate entity reçoit la consigne en avance

### Au fil du temps
- Le feedback loop mesure les résultats (en avance ? en retard ?)
- La marge s'auto-calibre : trop en avance → réduit, en retard → augmente
- Le modèle affine ses prédictions avec chaque nouvelle session
- L'IA apprend les patterns saisonniers

---

## Dépannage

### L'état reste "learning"
- Vérifie que `hvac_action` change bien quand le chauffage tourne
- Vérifie le capteur de température (pas "unavailable")
- Les sessions < 5 min ou < 0.3°C sont ignorées

### L'anticipation ne démarre pas
- Vérifie que `sensor.schedule_*_consigne` retourne bien une valeur numérique
- Le planning doit avoir une transition qui **monte** (ex: 16 → 19.5)
- Il faut au minimum 3 sessions enregistrées

### L'IA ne répond pas
- Vérifie ta clé API dans les paramètres de l'intégration
- Regarde les logs : `Paramètres → Système → Journaux` → filtrer `smart_heating`
- Pour Ollama : vérifie que le serveur est accessible depuis HA

### Forcer un appel IA
```
Outils de développement → Services
→ smart_heating.force_llm_call
→ context: morning
```

### Réinitialiser les sessions
```
Outils de développement → Services
→ smart_heating.reset_sessions
```

### Voir le diagnostic complet
```
Paramètres → Intégrations → Smart Heating → ⋮ → Télécharger les diagnostics
```
