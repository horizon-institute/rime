"""
Serve GraphQL on a socket with FastAPI.

Designed to be run from a frontend such as Uvicorn; use create_app as a factory.
"""

import asyncio
import concurrent.futures
import mimetypes
import os
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None
import urllib.parse
import sys
import signal
import traceback
import zipfile

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.websockets import WebSocket
from ariadne.asgi import GraphQL as AriadneGraphQL
from ariadne.asgi.handlers import GraphQLTransportWSHandler

from rime import Rime
from rime.graphql import load_schema, QueryContext
from rime.config import Config


def rime_background_task_entrypoint(config, cmd, args):
    """
    This is started in a separate process. It performs a single task and then exits.

    'config' is the Rime configuration.
    """
    aio_loop = asyncio.new_event_loop()

    # Reset signal behaviour; see https://github.com/encode/uvicorn/issues/548#issuecomment-1157082729
    signal.set_wakeup_fd(-1) # don't send the signal into shared socket
    signal.signal(signal.SIGTERM, signal.SIG_DFL) # reset signal handlers to default
    signal.signal(signal.SIGINT, signal.SIG_DFL) # reset signal handlers to default

    asyncio.set_event_loop(aio_loop)

    async def bg_enqueue_bg_call(rime, fn, *args, on_complete_fn=None):
        # Background RIME also needs a 'run in background' task, but we just run in fg here.
        exc = None

        try:
            result = aio_loop.run_until_complete(fn(rime, *args))
        except Exception as e:
            traceback.print_exc()
            result = None
            exc = e

        if on_complete_fn is not None:
            await on_complete_fn(rime, result, exc)

    async def run_cmd_in_background_rime():
        bg_rime = Rime.create(config, bg_enqueue_bg_call)
        return await cmd(bg_rime, *args)

    result = aio_loop.run_until_complete(run_cmd_in_background_rime())
    aio_loop.close()

    return result


class ZippedStaticFiles:
    def __init__(self, zip_pathname):
        self.zf = zipfile.ZipFile(zip_pathname, 'r')

    def __call__(self, path):
        if path == '':
            path = 'index.html'

        mime_type = mimetypes.guess_type(path)[0]
        return StreamingResponse(self.zf.open(path), media_type=mime_type)


def create_app(config_pathname=None, frontend_zip_pathname=None, frontend_hostport=None, schema_pathname=None):
    if frontend_hostport and frontend_zip_pathname:
        # frontend_zip_pathname is for production deploys; frontend_hostport is for dev.
        raise ValueError("Please supply either frontend_zip_pathname or frontend_hostport, not both.")
    elif not (frontend_hostport or frontend_zip_pathname):
        # Allow env vars to override iff we didn't specify either argument.
        frontend_hostport = os.environ.get('RIME_FRONTEND')
        frontend_zip_pathname = os.environ.get('RIME_FRONTEND_ZIP')

    if resource:
        # Increase number of open files, particularly relevant on macOS.
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))

    # Read config
    if not config_pathname:
        for filename in (os.environ.get('RIME_CONFIG', 'rime_settings.local.yaml'), 'rime_settings.yaml'):
            if os.path.exists(filename):
                print("RIME is using the configuration file", filename)
                config_pathname = filename
                break
        else:
            print("Configuration file not found. Create rime_settings.local.yaml or set RIME_CONFIG.")
            sys.exit(1)

    rime_config = Config.from_file(config_pathname)

    bg_task_executor = concurrent.futures.ProcessPoolExecutor()

    async def enqueue_background_task(rime, cmd, *args, on_complete_fn=None):
        assert isinstance(rime, Rime)

        # Start a new process to run the background task.
        future = bg_task_executor.submit(rime_background_task_entrypoint, rime_config, cmd, args)

        afuture = asyncio.wrap_future(future)

        # Wait for the async task to complete and translate exceptions into parameters for the callback.
        try:
            result = await afuture
            exc = None
        except Exception as e:
            traceback.print_exc()
            result = None
            exc = e

        if on_complete_fn is not None:
            await on_complete_fn(rime, result, exc)

    rime = Rime.create(rime_config, enqueue_background_task)
    app = FastAPI()

    if frontend_hostport:
        # Add CORS middleware to allow the frontend to communicate with the backend on a different port.
        frontend_host, frontend_port = frontend_hostport.split(':')
        cors_origins = [
            f"http://{frontend_host}:{frontend_port}",
        ]

        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.on_event("startup")
    async def startup():
        await rime.start_background_tasks_async()

    @app.on_event("shutdown")
    async def shutdown():
        bg_task_executor.shutdown()
        await rime.stop_background_tasks_async()

    @app.get("/media/{media_id:path}")
    async def handle_media(media_id: str):
        media_id = urllib.parse.unquote(media_id)
        media_data =  rime.get_media(media_id)

        response = StreamingResponse(media_data.handle, media_type=media_data.mime_type)
        response.headers['Content-Length'] = str(media_data.length)
        return response

    def get_context_value(request, data):
        return QueryContext(rime)

    schema = load_schema(Path(schema_pathname) if schema_pathname else None)

    graphql_app = AriadneGraphQL(
        schema,
        websocket_handler=GraphQLTransportWSHandler(),
        context_value=get_context_value
    )

    # For checking that the server is up:
    @app.get("/ping")
    async def ping():
        return JSONResponse({"ping": "pong"})

    # Use a separate endpoint, rather than app.mount, because Starlette doesn't support root mounts not ending in /.
    # See https://github.com/encode/starlette/issues/869 .
    @app.post("/graphql")
    async def handle_graphql_post(request: Request):
        # Queries and mutations.
        return await graphql_app.handle_request(request)

    @app.websocket("/graphql-ws")
    async def handle_graphql_ws(websocket: WebSocket):
        return await graphql_app.handle_websocket(websocket)

    if frontend_zip_pathname:
        app.get("/rime/{path:path}")(ZippedStaticFiles(frontend_zip_pathname))

        @app.get("/")
        async def redirect_to_frontend():
            return RedirectResponse(url="/rime")

    return app
