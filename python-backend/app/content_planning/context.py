"""Application-local runtime binding, also explicitly propagated to background work."""
from contextlib import contextmanager
from contextvars import ContextVar

_runtime = ContextVar('content_planning_runtime', default=None)


def current_runtime():
    return _runtime.get()


@contextmanager
def use_runtime(runtime):
    token = _runtime.set(runtime)
    try:
        yield runtime
    finally:
        _runtime.reset(token)
