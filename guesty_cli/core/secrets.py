"""Credential storage with OS keychain support.

Uses the 'keyring' library if available, falls back to file-based storage.
Inspired by gogcli's internal/secrets/store.go
"""
import json
import os
import sys

SERVICE_NAME = "guesty-cli"

_keyring_available = False
try:
    import keyring as _keyring
    _keyring_available = True
except ImportError:
    _keyring = None


def is_keyring_available():
    """Check if keyring backend is available and functional."""
    if not _keyring_available:
        return False
    try:
        # Test if backend works (some Linux systems have broken backends)
        backend = _keyring.get_keyring()
        # ChainerBackend with no backends = not useful
        name = type(backend).__name__
        if 'fail' in name.lower() or 'null' in name.lower():
            return False
        return True
    except Exception:
        return False


def store_secret(key, value):
    """Store a secret in keychain or config file.

    Args:
        key: Secret key (e.g., 'client_secret', 'token')
        value: Secret value

    Returns:
        str: Storage backend used ('keychain' or 'file')
    """
    if is_keyring_available():
        try:
            _keyring.set_password(SERVICE_NAME, key, value)
            return 'keychain'
        except Exception:
            pass

    # Fallback: store in config (existing behavior)
    return 'file'


def get_secret(key, fallback=None):
    """Retrieve a secret from keychain or config file.

    Args:
        key: Secret key
        fallback: Fallback value if not found in keychain

    Returns:
        str: The secret value, or fallback
    """
    if is_keyring_available():
        try:
            value = _keyring.get_password(SERVICE_NAME, key)
            if value:
                return value
        except Exception:
            pass

    return fallback


def delete_secret(key):
    """Delete a secret from keychain.

    Args:
        key: Secret key to delete

    Returns:
        bool: True if deleted
    """
    if is_keyring_available():
        try:
            _keyring.delete_password(SERVICE_NAME, key)
            return True
        except Exception:
            pass
    return False


def migrate_to_keychain(config):
    """Migrate secrets from config file to keychain.

    Args:
        config: Config dict containing secrets

    Returns:
        tuple: (updated config, bool whether migration happened)
    """
    if not is_keyring_available():
        return config, False

    migrated = False

    for key in ('client_secret', 'token'):
        value = config.get(key)
        if value:
            backend = store_secret(key, value)
            if backend == 'keychain':
                config[key] = ''  # Clear from config file
                migrated = True

    return config, migrated


def get_storage_info():
    """Get info about the current storage backend.

    Returns:
        dict with backend name, whether keychain is available, etc.
    """
    info = {
        'keyring_available': _keyring_available,
        'keyring_functional': is_keyring_available(),
        'backend': 'file',
    }

    if is_keyring_available():
        info['backend'] = 'keychain'
        info['keyring_backend'] = type(_keyring.get_keyring()).__name__

    return info
