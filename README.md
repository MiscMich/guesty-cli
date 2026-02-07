# guesty-cli

> 🏖️ **The missing CLI for Guesty PMS**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](pyproject.toml)

A powerful, zero-dependency command-line interface for [Guesty](https://www.guesty.com/) — the leading vacation rental management platform. Query, manage, and automate your property operations directly from the terminal.

---

## ✨ Features

- 🔐 **Secure OAuth2 authentication** with automatic token caching
- 📊 **Real-time dashboard** — `guesty status` shows your entire operation at a glance
- 🏠 **Full property management** — CRUD operations for listings, owners, and more
- 📅 **Reservation management** with powerful filtering and search
- 👥 **Guest profiles** — view history, preferences, and communication
- 📆 **Calendar operations** — view availability, block dates, adjust pricing
- 💰 **Financial analytics** — revenue reports by listing, month, or booking source
- 🔍 **Full-text search** across all your data
- 💾 **Local SQLite cache** for offline access and lightning-fast queries
- 🔄 **Incremental & full sync** — keep your local cache up to date
- 📤 **Export to CSV/JSON** for reporting and backups
- 🎣 **Webhook management** with built-in local listener for development
- 🎨 **Beautiful terminal output** with colors and formatted tables
- 0️⃣ **Zero external dependencies** — uses only Python standard library

---

## 🚀 Quick Start

```bash
# Install from PyPI
pip install guesty-cli

# Initialize configuration (interactive setup)
guesty init

# View your dashboard
guesty status
```

---

## 📖 Usage Examples

### Authentication

```bash
# Interactive setup — enter your Guesty API credentials
guesty init

# Check authentication status
guesty auth status
```

### Dashboard Overview

```bash
$ guesty status

╭─────────────────────────────────────────────────────────────╮
│  🏖️  Guesty CLI Dashboard                                    │
├─────────────────────────────────────────────────────────────┤
│  Account: Villa Paraiso Vacation Rentals                     │
│  Last Sync: 2026-02-07 14:32 UTC                            │
╰─────────────────────────────────────────────────────────────╯

📊 Quick Stats
   Properties:     22 listings
   Reservations:   2,348 total
   This Month:     47 check-ins, 52 check-outs
   Revenue MTD:    $127,450

📅 Upcoming (Next 7 Days)
   Today:          3 check-ins, 2 check-outs
   Tomorrow:       5 check-ins, 4 check-outs
   This Week:      18 arrivals, 21 departures

🔔 Alerts
   • 2 pending tasks requiring attention
   • 1 new review awaiting response
```

### Property Management

```bash
# List all properties
guesty listings

# Get detailed info for a specific property
guesty listings get --id 5f8a2b1c3d4e5f6a7b8c9d0e

# Filter by status
guesty listings --status active

# Search by name
guesty listings --search "ocean"

# Output as JSON for scripting
guesty listings --json | jq '.[] | {id, nickname, address}'
```

Sample output:
```
ID                        | Nickname          | Type       | Status  | City
──────────────────────────────────────────────────────────────────────────────
5f8a2b1c3d4e5f6a7b8c9d0e | Ocean View Villa  | Entire home | active  | Marathon
5f8a2b1c3d4e5f6a7b8c9d0f | Beachfront Bungalow | Entire home | active  | Miami
5f8a2b1c3d4e5f6a7b8c9d10 | Sunset Cottage    | Entire home | inactive | Key West
```

### Reservations

```bash
# List recent reservations
guesty reservations

# Filter by status
guesty reservations --status confirmed
guesty reservations --status check_in --date today
guesty reservations --status check_out --date tomorrow

# Date range queries
guesty reservations --from 2026-02-01 --to 2026-02-28
guesty reservations --check-in today
guesty reservations --check-out "next-week"

# Search by guest name
guesty reservations --guest "Smith"

# View reservation details
guesty reservations get --id RES-123456

# Cancel a reservation
guesty reservations cancel --id RES-123456 --reason "Guest request"

# Export reservations to CSV
guesty reservations --from 2026-01-01 --to 2026-01-31 --csv > january.csv
```

### Guest Management

```bash
# Search guests
guesty guests --search "john smith"

# View guest history
guesty guests get --id 5f8a2b1c3d4e5f6a7b8c9d0e

# List guests with upcoming stays
guesty guests --upcoming

# Export guest list
guesty guests --json > guests.json
```

### Calendar Operations

```bash
# View calendar for a property
guesty calendar --listing-id 5f8a2b1c3d4e5f6a7b8c9d0e --from today --to "+30d"

# Block dates
guesty calendar block --listing-id 5f8a2b1c3d4e5f6a7b8c9d0e \
  --from 2026-03-01 --to 2026-03-05 \
  --reason "Maintenance"

# Unblock dates
guesty calendar unblock --listing-id 5f8a2b1c3d4e5f6a7b8c9d0e \
  --from 2026-03-01 --to 2026-03-05

# Update pricing
guesty calendar price --listing-id 5f8a2b1c3d4e5f6a7b8c9d0e \
  --from 2026-07-01 --to 2026-07-07 \
  --amount 450
```

### Financial Reports

```bash
# Revenue summary
guesty financials summary --month 2026-01

# Revenue by property
guesty financials by-listing --year 2026

# Revenue by booking source
guesty financials by-source --quarter Q1-2026

# Export financial data
guesty financials export --from 2026-01-01 --to 2026-12-31 --csv > 2026-revenue.csv
```

Sample output:
```
Revenue Report: January 2026
══════════════════════════════════════════════════════════════

Total Revenue:        $127,450
Host Payout:          $108,332
Guest Fees:           $12,745
Taxes Collected:      $6,373

By Property:
──────────────────────────────────────────────────────────────
Property                  | Revenue    | Nights | Avg/Night
──────────────────────────────────────────────────────────────
Ocean View Villa          | $34,200    | 31     | $1,103
Beachfront Bungalow       | $28,500    | 28     | $1,018
Sunset Cottage            | $18,900    | 21     | $900
...                       | ...        | ...    | ...
```

### Search

```bash
# Full-text search across all data
guesty search "smith"
guesty search "ocean view" --type listings
guesty search "confirmed" --type reservations

# Advanced search with filters
guesty search --query "maintenance" --type tasks --status open
```

### Data Synchronization

```bash
# Quick incremental sync (default)
guesty sync

# Full historical sync
guesty sync --full

# Sync specific entities
guesty sync --listings
guesty sync --reservations --from 2025-01-01

# Check sync status
guesty sync status
```

### Data Export

```bash
# Export everything to JSON
guesty export --format json --output backup-2026-02-07.json

# Export to CSV (multiple files)
guesty export --format csv --output-dir ./exports/

# Export specific entities
guesty export --reservations --from 2026-01-01 --to 2026-01-31 --csv > jan.csv
guesty export --guests --json > guests.json
```

### Webhook Management

```bash
# List webhooks
guesty webhooks

# Create webhook
guesty webhooks create \
  --url https://api.example.com/webhooks/guesty \
  --events reservation.new,reservation.updated

# Update webhook
guesty webhooks update --id 5f8a2b1c3d4e5f6a7b8c9d0e --events reservation.new

# Delete webhook
guesty webhooks delete --id 5f8a2b1c3d4e5f6a7b8c9d0e

# Local webhook listener for development
guesty webhooks listen --port 8080
```

---

## ⚙️ Configuration

Configuration is stored in `~/.guesty-cli/config.json`:

```json
{
  "client_id": "your-guesty-client-id",
  "client_secret": "your-guesty-client-secret",
  "api_base": "https://open-api.guesty.com",
  "database_path": "~/.guesty-cli/guesty.db",
  "default_format": "table",
  "colors": true,
  "cache_ttl": 3600
}
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GUESTY_CLIENT_ID` | OAuth2 Client ID |
| `GUESTY_CLIENT_SECRET` | OAuth2 Client Secret |
| `GUESTY_API_BASE` | API base URL (default: `https://open-api.guesty.com`) |
| `NO_COLOR` | Disable colored output |

---

## 🔌 API Coverage

| Endpoint | List | Get | Create | Update | Delete | Special |
|----------|:--:|:--:|:--:|:--:|:--:|:--------|
| **Listings** | ✅ | ✅ | ✅ | ✅ | ✅ | Calendar ops |
| **Reservations** | ✅ | ✅ | ✅ | ✅ | ✅ | Approve/Decline/Cancel |
| **Guests** | ✅ | ✅ | ❌ | ❌ | ❌ | Profile history |
| **Owners** | ✅ | ✅ | ✅ | ✅ | ✅ | Documents |
| **Tasks** | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Reviews** | ✅ | ✅ | ❌ | ❌ | ❌ | — |
| **Calendar** | ✅ | — | — | ✅ | — | Block/Unblock/Price |
| **Webhooks** | ✅ | ✅ | ✅ | ✅ | ✅ | Local listener |
| **Users** | ✅ | ✅ | ❌ | ❌ | ❌ | — |
| **Integrations** | ✅ | ✅ | ❌ | ❌ | ❌ | — |
| **Financials** | ✅ | — | — | — | — | Reports & analytics |
| **Expenses** | ✅ | ✅ | ✅ | ✅ | ❌ | Attachments |
| **Views/Reports** | ✅ | — | — | — | — | Custom reports |

**Legend:** ✅ Supported | 🚧 In Progress | ❌ Not Available | — N/A

---

## 🛠️ Development

```bash
# Clone the repository
git clone https://github.com/villaparaiso/guesty-cli.git
cd guesty-cli

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode
pip install -e .

# Run tests
python -m pytest tests/
```

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Guidelines

- Follow [PEP 8](https://pep8.org/) style guidelines
- Write tests for new functionality
- Update documentation for API changes
- Keep dependencies at zero (stdlib only)

### Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/villaparaiso/guesty-cli/issues) with:

- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built with ❤️ by [Villa Paraiso Vacation Rentals](https://paraisovacationrentals.com)
- Inspired by the excellent CLI tools from [Stripe](https://stripe.com/docs/stripe-cli), [Vercel](https://vercel.com/cli), and [Fly.io](https://fly.io/docs/flyctl/)
- Thanks to the Guesty team for the Open API

---

## 📞 Support

- 📧 Email: [tech@paraisovacationrentals.com](mailto:tech@paraisovacationrentals.com)
- 🐛 Issues: [GitHub Issues](https://github.com/villaparaiso/guesty-cli/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/villaparaiso/guesty-cli/discussions)

---

<p align="center">
  <sub>Built for property managers who love the terminal.</sub>
</p>
