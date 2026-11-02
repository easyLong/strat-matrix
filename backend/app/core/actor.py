"""Trusted bank actor context, populated only after gateway credential validation."""
from contextlib import contextmanager
from contextvars import ContextVar

_actor = ContextVar('planning_actor', default=None)


def current_actor():
    return _actor.get() or '运营人员'


@contextmanager
def use_actor(actor):
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)
