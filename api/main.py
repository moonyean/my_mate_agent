from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import init_services, shutdown_services
from api.routers import chat, memory, persona, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_services()
    yield
    shutdown_services()


app = FastAPI(
    title="My Mate Agent API",
    description="로컬 AI 에이전트 — Ollama + Gemma 기반",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(persona.router)
app.include_router(memory.router)
app.include_router(settings.router)


@app.get("/health")
def health():
    return {"status": "ok"}
