# Security Policy

## Supported versions

Veltro is pre-1.0. Only the latest commit on `main` is supported: fixes land
there, and there are no maintained release branches to backport to.

| Version | Supported |
|---------|-----------|
| `main` (v0.1) | :white_check_mark: |
| anything older | :x: |

## What the attack surface actually is

Worth stating plainly, because it is smaller than most projects':

- **The parser and extractors** (`veltro/`) run locally and read files you give
  them. The realistic risk is a malicious `.vel` or source tree fed to
  `python -m veltro`, parser crashes, pathological inputs, path handling on
  `--out`. Schema validation uses `jsonschema`, the runtime is otherwise the
  Python standard library
- **The viewer** ([`docs/`](docs)) is a static page. No backend, no accounts, no
  telemetry, no network calls beyond fetching its own `demo.model.json`. Models
  you drop on it are parsed in your browser and never leave it, the only
  thing it stores is layout coordinates in `localStorage`. The realistic risk is
  a malicious `.model.json` driving the loader or a query into bad behaviour
- No credentials, keys or user data are handled anywhere in this repository

## Reporting a vulnerability

Use GitHub's private reporting: **Security -> Advisories -> Report a
vulnerability** on
[this repository](https://github.com/Nicchi10/Veltro/security/advisories/new).
It stays private until a fix is out.

Please do not open a public issue for a vulnerability.

Useful in a report: what you fed it, what happened, what you expected, and the
smallest input that reproduces it. A `.vel` or `.model.json` that triggers the
behaviour is worth more than a description of it.

**What to expect:** this is a single-maintainer project, so the honest answer is
best-effort, not a contractual window, an acknowledgement within a few days,
and a fix on `main` for anything confirmed. If a report is declined you will be
told why. Credit in the advisory unless you would rather stay anonymous.
