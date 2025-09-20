from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import plays as plays_api

APP_VERSION = "0.1.0"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"http://localhost(:\\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plays_api.router)


@app.get("/health")
async def read_health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/version")
async def read_version() -> str:
    return APP_VERSION
