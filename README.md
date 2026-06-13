# Secret Entities

A Home Assistant custom integration for storing **encrypted secrets** (passwords,
tokens, API keys) and decrypting them on demand via a service.

Per secret you get one entity. Its state is the **encrypted value** — open the
entity and that is all you ever see. The real value is only returned by the
`secret_entities.decrypt` service.

## Installation

### HACS (recommended)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Big-Gremlin&repository=ha-secret-entities&category=integration)

1. HACS → Integrations → ⋮ → *Custom repositories*
2. Add the repository URL, category *Integration*
3. Install *Secret Entities* and restart Home Assistant

### Manual

Copy `custom_components/secret_entities/` into the `config/custom_components/` folder of your Home Assistant instance and restart HA.

## Setup

*Settings* → *Devices & Services* → *Add integration* → **Secret Entities**. Manage secrets via the integration's *Configure* (options) screen.

## How it works

- You add a secret in the integration's **options** (name + value).
- The value is encrypted **immediately** with a freshly generated, per-secret
  key (Fernet / AES-128-CBC + HMAC). Each encryption uses a random IV, so the
  same value produces a different ciphertext every time — the value is *randomly*
  encrypted.
- Only the **ciphertext** and the **key** are persisted in
  `.storage/secret_entities.secrets_<entry_id>`. **The plaintext is never stored.**
- The key is kept internal: it is **never** exposed through entity state,
  attributes, the options UI, or any service response. Only the *decrypted value*
  leaves the integration, and only through the `decrypt` service.

## Entity

Each secret becomes one `sensor` entity whose state is the encrypted token, e.g.

```
sensor.router_password  →  gAAAAABm...K2t9Q==
```

> Sensor states are capped at 255 characters by Home Assistant. Tokens for
> normal passwords/keys stay well under that; very long values are shown
> truncated in the state (decryption still uses the full stored token).

## Service: `secret_entities.decrypt`

Returns the decrypted value. Pass either the `secret_id` (shown in the options
list) or the `entity_id` of the sensor — exactly one of the two is required.

```yaml
action: secret_entities.decrypt
data:
  secret_id: a1b2c3d4   # or: entity_id: sensor.router_password
response_variable: result
# result.value     -> the decrypted value
# result.name      -> the secret's name
# result.secret_id -> the internal id
```

Example in an automation / script:

```yaml
- action: secret_entities.decrypt
  data:
    entity_id: sensor.router_password
  response_variable: secret
- action: notify.admin
  data:
    message: "The password is {{ secret.value }}"
```

## Security model — read this

This integration **obfuscates** secrets from the Home Assistant UI, the state
machine, and dashboards. It is **not** a hardware vault:

- The encryption key is stored next to the ciphertext in `.storage`. Anyone with
  **read access to the config directory** can decrypt the secrets.
- Anyone who can **call services** (e.g. through the UI, API, or an automation)
  can call `decrypt` and read the plaintext.

In other words: it stops the value from being *visible at a glance* (in entity
state, history, logbook, shared dashboards), but it does not protect against an
attacker who already has filesystem or full API access. Treat `.storage` with
the same care as `secrets.yaml`.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This project uses the MIT License, for more details see the [license document](LICENSE).

---

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/biggremlin)
