from app.pilot_config import PilotSettings


def test_neon_pulled_env_overrides_base_file_without_losing_gemini(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('GEMINI_API_KEY=fixture-not-a-real-key\nGEMINI_MAX_RPM=5\n')
    (tmp_path / '.env.local').write_text('DATABASE_URL=postgresql+asyncpg://fixture/pooled\nDATABASE_URL_UNPOOLED=postgresql+asyncpg://fixture/direct\nGEMINI_MAX_RPM=7\n')
    settings = PilotSettings()
    assert settings.database_url.get_secret_value().endswith('/pooled')
    assert settings.migration_database_url.get_secret_value().endswith('/direct')
    assert settings.gemini_api_key.get_secret_value() == 'fixture-not-a-real-key'
    assert settings.gemini_max_rpm == 7


def test_explicit_migration_url_has_precedence_over_neon_alias():
    settings = PilotSettings(_env_file=None, migration_database_url='postgresql+asyncpg://fixture/explicit',
                             database_url_unpooled='postgresql+asyncpg://fixture/direct')
    assert settings.migration_database_url.get_secret_value().endswith('/explicit')


def test_empty_migration_url_uses_the_pulled_direct_connection():
    settings = PilotSettings(_env_file=None, migration_database_url='',
                             database_url_unpooled='postgresql+asyncpg://fixture/direct')
    assert settings.migration_database_url.get_secret_value().endswith('/direct')
