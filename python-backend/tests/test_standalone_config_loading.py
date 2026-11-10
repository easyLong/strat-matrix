"""The project bootstrap is intentionally not part of the embedded-module ZIP."""
import os


def test_standalone_config_loading_does_not_modify_environment_and_has_explicit_precedence(tmp_path):
    from app.standalone_config import load_config
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/.env').write_text('MYSQL_HOST=old\nMYSQL_USER=test\nMYSQL_PASSWORD=test\nMYSQL_DATABASE=test\n')
    (tmp_path/'.env').write_text('MYSQL_HOST=file\nARK_API_KEY=never-import\n')
    before=dict(os.environ)
    config=load_config(workspace=tmp_path,environ={'MYSQL_HOST':'explicit'})
    assert config.database.host=='explicit' and config.database.database=='test'
    assert config.fixture_path==tmp_path/'run/bank-source-fixture.json'
    assert dict(os.environ)==before and not config.settings
