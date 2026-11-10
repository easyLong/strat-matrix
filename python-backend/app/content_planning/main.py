"""Application factory shared by standalone and embedded deployment."""
def create_app(config, *, dependencies=None):
    from fastapi import FastAPI
    from .config import PlanningConfig
    from .runtime import PlanningRuntime, RuntimeContextMiddleware
    from .bootstrap import configure_app
    if not isinstance(config, PlanningConfig):
        config = PlanningConfig.from_mapping(config)
    runtime = PlanningRuntime(config, dependencies)
    app = FastAPI(title='多账号智能策划 API', version='0.3.0', lifespan=runtime.lifespan)
    app.state.planning_runtime = runtime
    configure_app(app)
    app.add_middleware(RuntimeContextMiddleware, runtime=runtime)
    return app
