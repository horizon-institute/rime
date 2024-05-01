"""
Serve GraphQL on a socket.
"""

import asyncio
import concurrent.futures
import os
import resource
import urllib.parse
import sys
import signal
import traceback

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.websockets import WebSocket
from ariadne.asgi import GraphQL as AriadneGraphQL
from ariadne.asgi.handlers import GraphQLTransportWSHandler

# Assume RIME is in the directory above this one.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rime import Rime
from rime.graphql import schema, QueryContext
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

def create_app():
    # Increase number of open files, particularly relevant on macOS.
    resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))

    # Read config
    frontend_host, frontend_port = os.environ.get('RIME_FRONTEND', 'localhost:3000').split(':')
    for filename in (os.environ.get('RIME_CONFIG', 'rime_settings.local.yaml'), 'rime_settings.yaml'):
        if os.path.exists(filename):
            print("RIME is using the configuration file", filename)
            rime_config = Config.from_file(filename)
            break
    else:
        print("Configuration file not found. Create rime_settings.local.yaml or set RIME_CONFIG.")
        sys.exit(1)

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

    # Add CORS middleware to allow the frontend to communicate with the backend on a different port.
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

    return app
