"""Package assets and explicitly installed external resources; independent of cwd."""
from importlib.resources import files
from pathlib import Path
from .context import current_runtime


def standalone_workspace():
    # Only a development tool calls this fallback; importing the package never loads .env.
    for parent in Path(__file__).resolve().parents:
        if parent.name == 'python-backend' and (parent / 'app').is_dir():
            return parent.parent
    raise RuntimeError('Development tools need an explicit planning workspace directory')


def workspace_directory():
    runtime = current_runtime()
    if runtime is not None and runtime.config.workspace_directory is not None:
        return runtime.config.workspace_directory
    if runtime is not None and not runtime.config.standalone:
        raise RuntimeError('This development tool needs an explicit planning workspace directory')
    return standalone_workspace()


def database_directory():
    runtime = current_runtime()
    if runtime is not None and runtime.config.resource_directory is not None:
        return runtime.config.resource_directory
    if runtime is not None and not runtime.config.standalone:
        raise RuntimeError('Set PLANNING_RESOURCE_DIRECTORY for database delivery tools')
    return standalone_workspace() / 'python-backend/database/content_planning'


def fixture_path():
    runtime = current_runtime()
    if runtime is not None:
        if runtime.config.fixture_path is not None:
            return runtime.config.fixture_path
        raise RuntimeError('Set PLANNING_FIXTURE_PATH for the explicitly selected fixture provider')
    return standalone_workspace() / 'run/bank-source-fixture.json'


def package_text(name):
    return files(__package__).joinpath('assets', name).read_text(encoding='utf-8')
