# Systemd units for PerceptShift

## Units

- `perceptshift-runtime.service` — deadline-aware ROS lifecycle runtime (user `perceptshift`).
- `perceptshift-api.service` — local operational API (user `perceptshift-api`) via
  `/usr/lib/perceptshift/bin/perceptshift-api-service`.

The runtime unit does not load the API mutation token. The native runtime does
not consume that credential.

## API service environment

The API unit sets:

- `HOME=/var/lib/perceptshift/api`
- `XDG_STATE_HOME=/var/lib/perceptshift/api/state`
- `XDG_DATA_HOME=/var/lib/perceptshift/api/data`

Those directories are owned by `perceptshift-api`. Parent `/var/lib/perceptshift`
is `0750` `root:perceptshift` so both service users can traverse without an
unsafe systemd path transition, and the parent is not group-writable.

Both services share `XDG_RUNTIME_DIR=/run/perceptshift/dds` (`0770`
`perceptshift:perceptshift`) so Fast DDS sockets are reachable across UIDs.
Wrappers default `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`, localhost ROS discovery,
and `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` so the API user and runtime user
can complete ROS service calls.

The wrapper sources `/opt/ros/jazzy/setup.bash` and
`/usr/share/perceptshift/ros/setup.bash` unless `PERCEPTSHIFT_API_ENABLE_ROS` is
explicitly false.

## Credentials

Runtime and API run as different Unix users. Both wrappers default
`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` and localhost ROS discovery so they can
communicate without Fast DDS shared-memory segments that are not usable
across UIDs. Operators may override those variables in the unit environment
files.

`LoadCredential=perceptshift-api-token:/etc/perceptshift/credentials/api-token`
loads a **root-owned plaintext** token file. systemd exposes it as
`$CREDENTIALS_DIRECTORY/perceptshift-api-token`. The API reads, in order:

1. `PERCEPTSHIFT_API_MUTATION_TOKEN`
2. `PERCEPTSHIFT_API_MUTATION_TOKEN_FILE`
3. `$CREDENTIALS_DIRECTORY/perceptshift-api-token`

This is not `LoadCredentialEncrypted`; do not place a systemd-creds encrypted
blob at that path unless you change the unit directive to match.

## Hardening

Units apply `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`,
`ProtectHome`, restricted address families (including `AF_NETLINK` for DDS),
and bounded `LimitNOFILE`. API `ReadWritePaths` are limited to the API-owned
state/log directories and `/dev/shm` for DDS.

`MemoryDenyWriteExecute` is intentionally not enabled by default because ONNX
Runtime may require executable mappings. Enable only after validating ORT on
the target host.

## Configuration

- Runtime config: `/etc/perceptshift/runtime.yaml`
- API env: `/etc/perceptshift/api.env` (mode 0640, owner root:perceptshift)
- Credentials: `/etc/perceptshift/credentials/api-token` (mode 0600, owner root)

Do not place secrets in unit files or world-readable environment files.

## Notes

PerceptShift publishes a control-hold request when no eligible profile is
available. Units do not publish actuator velocity commands.
