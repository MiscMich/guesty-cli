# guesty-cli

An independent command-line client for Guesty PMS. Query and synchronize operational data, use structured output in scripts, and preview supported write operations before applying them.

> This project is not affiliated with or endorsed by Guesty. Consult Guesty's official API documentation and terms for supported endpoints and usage.

## Features

- Python standard-library runtime (optional OS keychain support via `keyring`)
- Local SQLite cache with FTS5 search
- JSON, TSV, CSV, and human-readable output
- OAuth token caching and rate-limit handling
- Dry-run support and confirmations for mutating commands
- Stable exit codes and non-interactive operation
- Raw requests to API paths documented by Guesty

## Install

```bash
git clone https://github.com/Villa-Paraiso-Vacation-Rentals/guesty-cli.git
cd guesty-cli
python -m pip install .
```

Python 3.8 or newer is required.

## Configure

Create Guesty Open API credentials in the Guesty dashboard, then run:

```bash
guesty init
```

For non-interactive setup:

```bash
export GUESTY_CLIENT_ID="your-client-id"
export GUESTY_CLIENT_SECRET="your-client-secret"
guesty --no-input init --skip-sync
```

Do not commit credentials, exported authentication files, access tokens, or the local configuration directory.

## Examples

The identifiers below are placeholders, not real account data.

```bash
# Synchronize and query local data
guesty sync
guesty reservations --today
guesty listing get LISTING_ID --json
guesty reservation get RESERVATION_CODE --json
guesty search "maintenance"

# Structured output
guesty --json listings list
guesty --plain reservations list

# Preview a write before applying it
guesty calendar block LISTING_ID 2026-09-01 --to 2026-09-03 --reason "Maintenance" --dry-run

# Call a path from Guesty's official API documentation
guesty raw GET /v1/listings --params '{"limit": 5}'
```

Run `guesty --help` and `guesty <command> --help` for the complete command surface.

## Authentication export safety

`guesty auth-export` omits `client_secret` by default, including in non-interactive mode. The secret is included only when `--include-secrets` is supplied explicitly:

```bash
guesty auth-export --out account.json
guesty auth-export --include-secrets --out account-with-secret.json
```

Files written by the command use restrictive permissions. Treat any export containing a secret as sensitive.

## Automation

```bash
# Avoid prompts
export GUESTY_NO_INPUT=1

# Obtain and reuse one cached access token
TOKEN=$(guesty auth-token)
guesty --access-token "$TOKEN" --json listings list

# Discover machine-readable behavior
guesty schema
guesty exit-codes
guesty agent capabilities
```

`GUESTY_NO_INPUT` disables prompts; it does not opt into secret disclosure or bypass write safeguards.

## Local data

By default, configuration and the SQLite cache live under `~/.guesty-cli/`. The exact schema may evolve between releases. Export through the CLI rather than depending on private database details.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup, tests, and package checks. Security reports should follow [SECURITY.md](SECURITY.md).

## API coverage

Named commands wrap common workflows. `guesty raw` can call a method and path from Guesty's official API documentation without bundling a copy of third-party API documentation. See [API_COVERAGE.md](API_COVERAGE.md) for scope and limitations.

## License

MIT — see [LICENSE](LICENSE).
