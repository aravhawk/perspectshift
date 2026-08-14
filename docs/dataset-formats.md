# Dataset formats

Supported manifests (templates under `config/templates/`):

- Classification JSON
- COCO detection JSON
- ROS bag dataset descriptors (MCAP/SQLite via Jazzy APIs)

Datasets are always user-supplied. Tests may generate tiny deterministic fixtures at runtime in temporary directories; those fixtures are not product data and are not performance evidence.
