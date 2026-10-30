
from fastapi import FastAPI

from routers import users,projects,connections,profiling

app = FastAPI(
    title="DataMBA Data Profiling API",
    description="API for managing users, projects, connections, and data profiling.",
    version="1.0.0",
)

app.include_router(users.router)
app.include_router(projects.router)
app.include_router(connections.router)
app.include_router(profiling.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to DataMBA Data Profiling API",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
    }
