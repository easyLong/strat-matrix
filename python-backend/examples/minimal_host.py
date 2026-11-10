"""Run from python-backend: python -m uvicorn examples.minimal_host:app --port 8000.

Disabled by default. The host owns how configuration is obtained; this example
explicitly uses its process environment. Production may pass an Apollo snapshot
or a typed PlanningConfig instead. No module code loads this environment itself.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.content_planning import install_content_planning


@asynccontextmanager
async def host_lifespan(application):
    yield {'host_resource': 'available'}


app = FastAPI(title='Minimal host', lifespan=host_lifespan)


@app.get('/health')
def health(request: Request):
    return {'host': 'ok', 'resource': request.state.host_resource}


planning = install_content_planning(app, config_provider=lambda: dict(os.environ))
