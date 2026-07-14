# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in the Interactly Workflow SDK, please report it privately to
your Interactly point of contact (or the Interactly support/security team) rather than opening a public
issue. Include a description of the issue, steps to reproduce, and the affected version
(see [`CHANGELOG.md`](CHANGELOG.md)). We will acknowledge the report and work with you on a fix and
coordinated disclosure.

Please do **not** include real credentials, member data, or other sensitive information in a report.

## Handling credentials

This SDK talks to the Interactly Workflow API using a bearer token and team/user identifiers. Treat
these as secrets:

- **Never hardcode** `INTERACTLY_API_KEY` (or other `INTERACTLY_*` values) in source, notebooks, or
  examples. Provide them via environment variables or a local `.env` file.
- **Do not commit** your `.env` file or any file containing an API key to version control.
- **Rotate** any key that may have been exposed, and scope keys to the minimum team/permissions needed.
- The client reads credentials from the environment by default; see
  [`docs/authentication.md`](docs/authentication.md).

## Supported versions

Security fixes are applied to the latest released version. See [`CHANGELOG.md`](CHANGELOG.md) for
release history and [`docs/versioning.md`](docs/versioning.md) for the versioning policy.
