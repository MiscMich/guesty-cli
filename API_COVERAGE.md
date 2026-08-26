# API coverage

`guesty-cli` provides named commands for common Guesty resources and a `raw` command for advanced use.

## Named command areas

- Authentication and status
- Listings and photos
- Reservations and guests
- Owners and users
- Calendar operations
- Tasks and reviews
- Integrations and views
- Financial, occupancy, search, sync, and export workflows

Run `guesty --help` for the current command list and `guesty schema` for machine-readable command metadata.

## Raw API access

Use Guesty's official API documentation to identify a supported HTTP method and path:

```bash
guesty raw GET /v1/listings --params '{"limit": 5}'
```

The project does not bundle a mirror of Guesty's documentation or OpenAPI material. API availability and permissions vary by Guesty account, plan, scope, and platform changes. A path's presence in external documentation does not guarantee that a specific account can use it.

## Safety and compatibility

- Prefer named commands when available; they provide consistent output and safety checks.
- Preview mutating operations with `--dry-run` where supported.
- Verify changes in Guesty after a successful write.
- Treat response fields and undocumented behavior as unstable.
- Never use production credentials in tests or examples.
