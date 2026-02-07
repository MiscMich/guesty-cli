"""Configuration management for guesty-cli.

Config stored at ~/.guesty-cli/config.json
"""

import json
import os
from pathlib import Path


DEFAULT_CONFIG = {
    "client_id": "",
    "client_secret": "",
    "account_name": "",
    "api_base_url": "https://open-api.guesty.com",
    "db_path": "",
    "default_format": "table",
    "token": "",
    "token_expires_at": "",
    "tokens_generated_24h": [],  # Track token generation timestamps
}


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    return Path.home() / ".guesty-cli"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.json"


def get_default_db_path() -> Path:
    """Get the default database path."""
    return get_config_dir() / "guesty.db"


def ensure_config_dir() -> None:
    """Create the configuration directory if it doesn't exist."""
    config_dir = get_config_dir()
    if not config_dir.exists():
        config_dir.mkdir(parents=True, mode=0o700)


def load_config() -> dict:
    """Load configuration from file.
    
    Returns:
        dict: Configuration dictionary. Creates default config if none exists.
    """
    config_path = get_config_path()
    
    if not config_path.exists():
        # Create default config on first run
        ensure_config_dir()
        config = DEFAULT_CONFIG.copy()
        save_config(config)
        return config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Merge with defaults to handle new fields
        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        return merged
        
    except (json.JSONDecodeError, IOError) as e:
        # If config is corrupt, return defaults
        config = DEFAULT_CONFIG.copy()
        save_config(config)
        return config


def save_config(config: dict) -> None:
    """Save configuration to file.
    
    Args:
        config: Configuration dictionary to save.
    """
    ensure_config_dir()
    config_path = get_config_path()
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    
    # Set restrictive permissions on config file (contains secrets)
    os.chmod(config_path, 0o600)


def get_db_path(config: dict = None) -> Path:
    """Get the database path from config or default.
    
    Args:
        config: Optional config dict. If not provided, loads from file.
        
    Returns:
        Path: Path to the SQLite database.
    """
    if config is None:
        config = load_config()
    
    db_path = config.get("db_path", "")
    if db_path:
        return Path(db_path).expanduser()
    
    return get_default_db_path()


def update_token_cache(token: str, expires_at: str) -> None:
    """Update the cached token in config.
    
    Args:
        token: The access token.
        expires_at: ISO 8601 timestamp when token expires.
    """
    config = load_config()
    config["token"] = token
    config["token_expires_at"] = expires_at
    
    # Track token generation
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    timestamps = config.get("tokens_generated_24h", [])
    timestamps.append(now)
    config["tokens_generated_24h"] = timestamps
    
    save_config(config)


def clear_token_cache() -> None:
    """Clear the cached token from config."""
    config = load_config()
    config["token"] = ""
    config["token_expires_at"] = ""
    save_config(config)


def get_cached_token() -> tuple[str, str]:
    """Get the cached token and its expiry.
    
    Returns:
        tuple: (token, expires_at) or ("", "") if no cached token.
    """
    config = load_config()
    return config.get("token", ""), config.get("token_expires_at", "")


def count_tokens_last_24h() -> int:
    """Count tokens generated in the last 24 hours.
    
    Returns:
        int: Number of tokens generated in last 24h.
    """
    from datetime import datetime, timezone, timedelta
    
    config = load_config()
    timestamps = config.get("tokens_generated_24h", [])
    
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    
    # Filter to last 24h
    valid_timestamps = []
    for ts in timestamps:
        try:
            ts_dt = datetime.fromisoformat(ts)
            if ts_dt > cutoff:
                valid_timestamps.append(ts)
        except (ValueError, TypeError):
            continue
    
    # Update config with cleaned list
    config["tokens_generated_24h"] = valid_timestamps
    save_config(config)
    
    return len(valid_timestamps)