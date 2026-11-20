import base64

import pytest
from dotenv import dotenv_values

from app.setup_clerk import check, configure, issuer_from_publishable_key, local_origin, update_env_text


def key(domain='fogwrite-test.clerk.accounts.dev'):
    return 'pk_test_' + base64.urlsafe_b64encode((domain + '$').encode()).decode().rstrip('=')


def test_public_key_derives_exact_clerk_issuer():
    assert issuer_from_publishable_key(key()) == 'https://fogwrite-test.clerk.accounts.dev'


@pytest.mark.parametrize('value', ['sk_test_do_not_paste', 'pk_live_production_key', 'pk_test_REPLACE_ME', key('user@evil.test'), key('127.0.0.1'), key('evil.test/path'), key('localhost')])
def test_setup_rejects_secrets_placeholders_and_invalid_hosts(value):
    with pytest.raises(ValueError): issuer_from_publishable_key(value)


@pytest.mark.parametrize('value', ['http://localhost:8000/path', 'https://example.com', 'http://localhost:8000?x=1', 'http://user@localhost:8000', 'http://127.0.0.1:99999'])
def test_local_setup_rejects_wrong_origins(value):
    with pytest.raises(ValueError): local_origin(value)


def test_env_preserves_existing_secrets_comments_and_line_endings():
    text = '# Keep this\r\nGEMINI_API_KEY=private-example\r\nEXAMPLE_MULTILINE="first\r\nsecond"\r\nCLERK_ISSUER=old\r\nCLERK_ISSUER=duplicate\r\n'
    changed = update_env_text(text, {'CLERK_ISSUER':'https://fogwrite-test.clerk.accounts.dev','FRONTEND_ORIGIN':'http://localhost:8000'})
    assert '# Keep this\r\nGEMINI_API_KEY=private-example\r\nEXAMPLE_MULTILINE="first\r\nsecond"\r\n' in changed
    assert changed.count('CLERK_ISSUER=') == 1
    assert '\r\n' in changed


def test_setup_is_repeatable_and_keeps_gemini_key(tmp_path):
    target = tmp_path / '.env'
    target.write_text('GEMINI_API_KEY=private-example\nGEMINI_MODEL=gemini-3.5-flash-lite\n')
    configure(target, key(), 'http://localhost:8000')
    configure(target, key(), 'http://localhost:8000')
    values = dotenv_values(target)
    assert values['GEMINI_API_KEY'] == 'private-example'
    assert values['DATABASE_URL'].startswith('sqlite+aiosqlite:')
    assert values['CLERK_PUBLISHABLE_KEY'] == key()
    assert check(target) == ('https://fogwrite-test.clerk.accounts.dev','http://localhost:8000')
    with pytest.raises(ValueError): configure(target,key('another.clerk.accounts.dev'),'http://localhost:8000')


def test_setup_does_not_overwrite_production_or_existing_database(tmp_path):
    target = tmp_path / '.env'
    target.write_text('APP_ENV=production\nGEMINI_API_KEY=private-example\n')
    before = target.read_bytes()
    with pytest.raises(ValueError): configure(target,key(),'http://localhost:8000')
    assert target.read_bytes() == before
    target.write_text('DATABASE_URL=postgresql+asyncpg://example/existing\n')
    configure(target,key(),'http://localhost:8000')
    assert dotenv_values(target)['DATABASE_URL'] == 'postgresql+asyncpg://example/existing'
