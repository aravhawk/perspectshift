# Operational console

The web console under `web/` is presentation-only. It talks to the local API.

Security defaults:

- strict CSP in production static serving;
- no token persistence by default;
- no `dangerouslySetInnerHTML` for report HTML;
- secrets redacted from error displays.

Build with pnpm from `web/` or the root workspace.

The static console image does not proxy `/api`. Configure the API base URL in
the console settings. Same-origin API access only works when an operator
fronts the console with their own reverse proxy.
