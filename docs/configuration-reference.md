# Configuration reference

Schemas under `config/schemas/` are the contract source of truth.

## Runtime config

Template: `config/templates/runtime.template.yaml`  
Schema: `config/schemas/runtime-config-v1.schema.json`

Notable fields:

- `bundle_path` — absolute path to a user-supplied profile bundle
- `policy.deadline_ms` — soft deadline used for eligibility and switching
- `security.*` — symlink/world-writable/model-root constraints
- `telemetry.power_provider` — may be `disabled` / unavailable with reason codes

## Forge config

Template: `config/templates/forge.template.yaml`  
Schema: `config/schemas/forge-config-v1.schema.json`

Environment expansion supports only `${NAME}` for allowlisted names. Unresolved variables are errors. No command substitution.
