"""Content-planning module. Importing this package creates no runtime resources."""


def __getattr__(name):
    if name == 'create_app':
        from .main import create_app
        return create_app
    if name == 'install_content_planning':
        from .integration import install_content_planning
        return install_content_planning
    raise AttributeError(name)
