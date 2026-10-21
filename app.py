"""Run FORGE's FastAPI backend and serve its HTML, CSS, and JavaScript frontend."""

import os

import uvicorn

from server.main import app


DEFAULT_PORT = int(os.getenv("FORGE_PORT", "8001"))


if __name__ == "__main__":
    uvicorn.run("server.main:app", host="127.0.0.1", port=DEFAULT_PORT, reload=True)
