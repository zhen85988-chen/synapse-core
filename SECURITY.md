# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Synapse Core, please **do not** open a public issue.

Instead, email the maintainer directly at **zhen85988@outlook.com** with:

- A clear description of the vulnerability
- Steps to reproduce
- Affected versions

You will receive a response within 72 hours. The issue will be investigated and, if confirmed, patched within 90 days.

## Scope

Synapse Core is a local-first application. Security issues are most likely to involve:

- **SQL injection** via unsanitized input to the database layer
- **Path traversal** in backup/snapshot file handling
- **MCP tool abuse** leading to unintended data exposure
- **Rate limiter bypass** causing denial-of-service via token exhaustion

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (main branch) | ✅ |
| older versions | ❌ |

## Disclosure Policy

After a fix is released, the vulnerability will be disclosed publicly with full credit to the reporter.

## Local-Only Architecture Note

Synapse Core stores all data in a local SQLite database. No data is transmitted to any remote server. The primary attack surface is local — if an attacker already has filesystem access to your machine, they own your data. This tool assumes a trusted local environment and does not implement encryption at rest.

If you need encryption at rest for your memory database, consider enabling Windows BitLocker or macOS FileVault on the directory `~/.synapse-core/`.
