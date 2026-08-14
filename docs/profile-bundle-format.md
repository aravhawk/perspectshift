# Profile bundle format

A profile bundle packages certified execution profiles with:

- per-file SHA-256 digests;
- canonical manifest serialization and manifest digest;
- optional Ed25519 signature over the signing input;
- attested quality metrics and latency envelopes from measured runs;
- provider and resource attestations.

Verification must succeed before model load. Bundles must not contain executable content that is interpreted as code beyond the declared model/runtime artifacts.

Schema: `config/schemas/profile-bundle-v1.schema.json`.
