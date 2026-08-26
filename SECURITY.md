# Security policy

## Reporting a vulnerability

Please do not open a public issue for suspected vulnerabilities or exposed credentials. Use GitHub's private vulnerability reporting for this repository:

https://github.com/Villa-Paraiso-Vacation-Rentals/guesty-cli/security/advisories/new

Include the affected version, reproduction steps, impact, and any suggested mitigation. Do not include real Guesty credentials, access tokens, guest data, or other customer information.

Maintainers will acknowledge a report as soon as practical, investigate it, and coordinate remediation and disclosure with the reporter.

## Supported versions

Security fixes are applied to the latest release. Users should upgrade to the newest available version before reporting an issue that may already be fixed.

## Credential exposure

If a real client secret or access token is exposed, revoke or rotate it in Guesty immediately. Removing a secret from the current Git tree does not remove it from Git history or external clones.
