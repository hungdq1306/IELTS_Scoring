"""Configure an existing Clerk development app without requesting its secret key.

This command only writes local configuration; it does not create a Clerk account,
enable OAuth providers, migrate a database, or claim that live sign-in was tested.
"""
import argparse
import base64
import binascii
import io
import re
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from dotenv.parser import parse_stream

ROOT = Path(__file__).resolve().parents[2]


def issuer_from_publishable_key(value):
    value = value.strip()
    if not re.fullmatch(r'pk_test_[A-Za-z0-9_-]{8,500}={0,2}', value):
        raise ValueError('Use the full development Publishable Key beginning pk_test_. Do not paste sk_ secret keys.')
    encoded = value.removeprefix('pk_test_')
    try:
        decoded = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True).decode('ascii')
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise ValueError('This Publishable Key is not a valid Clerk key.') from None
    if not decoded.endswith('$'):
        raise ValueError('The Clerk key is incomplete or has an invalid domain payload.')
    domain = decoded[:-1].lower()
    labels = domain.split('.')
    if (len(labels) < 2 or len(domain) > 253 or domain.endswith('.localhost') or
        all(label.isdecimal() for label in labels) or
        any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)):
        raise ValueError('The key must contain a valid public Clerk Frontend API hostname.')
    return 'https://' + domain


def local_origin(value):
    parts = urlsplit(value)
    if (parts.scheme != 'http' or parts.hostname not in ('localhost', '127.0.0.1', '::1') or
        parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise ValueError('Local setup requires an exact localhost HTTP origin, for example http://localhost:8000.')
    try:
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError()
    except ValueError:
        raise ValueError('Invalid localhost port.') from None
    return value.rstrip('/')


def update_env_text(text, updates):
    """Preserve complete unrelated bindings, including multiline secrets/comments."""
    newline = '\r\n' if '\r\n' in text else '\n'
    chunks, seen = [], set()
    for binding in parse_stream(io.StringIO(text)):
        key = binding.key.upper() if binding.key else None
        if key not in updates:
            chunks.append(binding.original.string)
        elif key not in seen:
            # Keep blank lines preceding this binding; collapse duplicate configured keys.
            leading = re.match(r'^[\r\n]*', binding.original.string).group()
            chunks.append(leading + key + '=' + updates[key] + newline)
            seen.add(key)
    result = ''.join(chunks)
    remaining = [key for key in updates if key not in seen]
    if remaining:
        if result and not result.endswith(('\n', '\r')): result += newline
        result += newline + '# FogWrite Clerk development setup' + newline
        result += ''.join(key + '=' + updates[key] + newline for key in remaining)
    return result


def configure(path, publishable_key, origin, *, replace_existing=False):
    issuer = issuer_from_publishable_key(publishable_key)
    origin = local_origin(origin)
    original = path.read_bytes() if path.exists() else b''
    text = original.decode('utf-8-sig')
    values = dotenv_values(stream=io.StringIO(text))
    existing = values.get('CLERK_PUBLISHABLE_KEY') or values.get('VITE_CLERK_PUBLISHABLE_KEY')
    if existing and existing != publishable_key.strip() and not replace_existing:
        raise ValueError('An application key already exists. Use --replace-existing only if you intend to change this Clerk app.')
    if values.get('APP_ENV') == 'production':
        raise ValueError('This helper configures local development only; do not replace a production .env with development keys.')
    updates = {'APP_ENV': 'development', 'CLERK_PUBLISHABLE_KEY': publishable_key.strip(),
               'CLERK_ISSUER': issuer, 'FRONTEND_ORIGIN': origin,
               'CLERK_JWT_KEY': '', 'CLERK_AUDIENCE': ''}
    if not values.get('DATABASE_URL'):
        updates['DATABASE_URL'] = 'sqlite+aiosqlite:///./results/pilot.sqlite3'
    updated = update_env_text(text, updates)
    prefix = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    path.write_bytes(prefix + updated.encode('utf-8'))
    return issuer, origin


def check(path):
    values = dotenv_values(path)
    issuer = issuer_from_publishable_key(values.get('CLERK_PUBLISHABLE_KEY') or '')
    origin = local_origin(values.get('FRONTEND_ORIGIN') or '')
    if values.get('CLERK_ISSUER') != issuer:
        raise ValueError('CLERK_ISSUER does not match the Publishable Key. Run setup again with the correct key.')
    if values.get('APP_ENV') != 'development':
        raise ValueError('The local Clerk launcher requires APP_ENV=development.')
    if not values.get('DATABASE_URL'):
        raise ValueError('DATABASE_URL is missing. Run setup or configure the local database.')
    return issuer, origin


def main():
    parser = argparse.ArgumentParser(description='Configure Clerk for the local FogWrite MVP.')
    parser.add_argument('--publishable-key')
    parser.add_argument('--origin', default='http://localhost:8000')
    parser.add_argument('--replace-existing', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.check:
            issuer, origin = check(ROOT / '.env')
        else:
            key = args.publishable_key or input('Paste your Clerk DEVELOPMENT Publishable Key (pk_test_...): ').strip()
            issuer, origin = configure(ROOT / '.env', key, args.origin, replace_existing=args.replace_existing)
            (ROOT / 'results').mkdir(exist_ok=True)
        print('Clerk local configuration: ready (configuration only).')
        print('Issuer: ' + issuer)
        print('Frontend origin: ' + origin)
        print('Existing Gemini configuration was preserved. No secret Clerk key is required.')
    except (ValueError, OSError, EOFError) as error:
        raise SystemExit('Setup not completed: ' + str(error)) from None


if __name__ == '__main__':
    main()
