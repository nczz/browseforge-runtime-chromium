# Security Policy

This repository is intended to be open source, but runtime development can easily produce sensitive operational artifacts. Do not commit secrets, cookies, browser profiles, account data, proxy credentials, or unsanitized detector captures.

## Sensitive material that must not be committed

- BrowseForge API tokens
- proxy host credentials or paid proxy account metadata
- cookies, localStorage, sessionStorage, browser user-data directories
- raw screenshots or detector dumps that identify a real account, IP owner, or operator
- private signing keys, CI tokens, cloud credentials, release credentials

## Detector evidence policy

Detector results may be committed only after sanitization. A committed report should preserve technical facts while removing operational identity:

- keep runtime version, detector name, detector URL, test date, host OS, container flag, surface, result, and mitigation notes
- redact full IP addresses unless intentionally public test infrastructure is used
- redact account names, profile names, proxy credentials, and raw tokens
- prefer normalized JSON summaries under `detectors/` over raw HTML dumps

## Responsible use

This project exists to support repeatable browser automation, QA, research, and controlled anti-fingerprinting experiments. Do not use it to bypass access controls, commit fraud, steal data, or violate platform terms.

## Reporting

Open a private security advisory or contact the repository maintainers if you find a vulnerability, secret exposure, or detector evidence leak.
