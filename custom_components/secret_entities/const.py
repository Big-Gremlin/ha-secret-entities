"""Constants for the Secret Entities integration."""
from __future__ import annotations

DOMAIN = "secret_entities"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.secrets"

# Storage / item keys
CONF_SECRETS = "secrets"
CONF_ID = "id"
CONF_NAME = "name"
CONF_ICON = "icon"
CONF_TOKEN = "token"  # ciphertext (public)
CONF_KEY = "key"  # encryption key (internal, never exposed)

# Config-flow input keys
CONF_SECRET = "secret"  # the plaintext the user types in (never persisted)

# Services
SERVICE_DECRYPT = "decrypt"

# Service / call attributes
ATTR_SECRET_ID = "secret_id"
ATTR_ENTITY_ID = "entity_id"
ATTR_NAME = "name"
ATTR_VALUE = "value"

# Signals
SIGNAL_SECRETS_CHANGED = f"{DOMAIN}_secrets_changed"

SAVE_DELAY_SECONDS = 2
