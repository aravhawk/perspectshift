# Quality certification

Certification gates combine:

- schema/integrity validity;
- measured quality metric versus configured floor (offline-attested);
- latency envelope versus deadline policy with margin;
- memory/RSS attestations;
- provider compatibility.

Failing candidates are rejected with machine-readable reason codes. Passing candidates may enter the profile bundle. Runtime still applies deadline-aware eligibility and may fail closed.
