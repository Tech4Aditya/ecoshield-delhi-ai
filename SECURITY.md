# Security Policy

## Supported Versions

This project is currently in active development. Security fixes are applied to the `main` branch only.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < main  | :x:                 |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Instead, report it privately via one of the following:
   - Use GitHub's [private vulnerability reporting](../../security/advisories/new) feature (Security tab → Report a vulnerability).
   - Email the maintainer directly (see profile contact info).
3. Include as much detail as possible:
   - A description of the vulnerability and its potential impact
   - Steps to reproduce or a proof-of-concept
   - Affected files, endpoints, or components
   - Suggested fix or mitigation, if known

## Response Process

- You will receive an acknowledgment within **48–72 hours**.
- The maintainer will investigate and validate the report.
- A fix or mitigation plan will be developed and, where applicable, a coordinated disclosure timeline agreed upon.
- Credit will be given to the reporter in release notes unless anonymity is requested.

## Scope

This policy covers:

- The simulation engine and dispatch/coordination logic (`smog_control/`)
- The HTML/JS visualizer (`visualize.py` and generated output)
- Any API endpoints, data ingestion scripts, or configuration files in this repository

Out of scope:

- Vulnerabilities in third-party dependencies (report these upstream)
- Issues requiring physical access to a deployment environment
- Social engineering attacks

## General Security Practices in This Project

- No secrets, API keys, or credentials should ever be committed to the repository.
- Generated HTML output (`simulation.html`) is self-contained and does not make external network requests; any change introducing external calls or remote data fetches should be flagged for review.
- Dependencies should be kept up to date and reviewed for known CVEs before merging.

Thank you for helping keep this project and its users safe.
