# Deployment

Supported installable units converge on the same config/data paths:

- `/etc/perceptshift/` — configuration
- `/var/lib/perceptshift/` — runtime state
- `/var/lib/perceptshift/api/` — API service-owned state and data
- `/var/log/perceptshift/` — logs

See `deploy/systemd/`, `deploy/containers/`, and `packaging/debian/`.

## Debian / systemd (supported integrated product)

The Debian package installs the ROS lifecycle runtime and the operational API as
systemd services. The API unit runs as `perceptshift-api` through
`/usr/lib/perceptshift/bin/perceptshift-api-service`, which sources the packaged
ROS environment and reads the mutation token from systemd `LoadCredential`
(`perceptshift-api-token` from `/etc/perceptshift/credentials/api-token`).

That credential path is a root-owned plaintext file consumed by systemd
`LoadCredential`, not an encrypted systemd-creds blob. Runtime and API run as
different users; packaged wrappers default Cyclone DDS plus localhost UDPv4 so they
can complete ROS service calls without Fast DDS shared-memory UID isolation.

## Individual container images

Images are independent tools, not an integrated compose stack. There is no supported `docker compose up` product surface.

- `Dockerfile.runtime` — native `perceptshift-runtime` diagnostic/runtime binary.
  Requires an explicit command and a user-supplied bundle. Default `CMD` is
  `--doctor --json` (one-shot). Not a ROS adaptive runtime.
- `Dockerfile.api` — artifact-store API only. ROS is unavailable in this image;
  readiness/capabilities report artifact-store / ROS unavailable. Not ROS-connected.
- `Dockerfile.console` — static console. Same-origin `/api` is not proxied; the
  operator must set the API base URL in the console.

Containers run as non-root and mount bundles read-only when used.
