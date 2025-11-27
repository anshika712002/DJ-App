# import asyncio
import uvicorn
from fastapi import FastAPI, Depends,WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi import Query, Header
from fastapi.staticfiles import StaticFiles
import os
# from sqlalchemy.ext.asyncio import AsyncSession
# from database import get_db
from auth import auth_router
from database import  async_engine, Base
from user import user_router
from song_requests import song_request_router 
from websocket_manager import connected_clients
from sqlalchemy import text 
from database import AsyncSessionLocal

print("✅ FastAPI server is starting...") 

app = FastAPI()
app.mount("/audio",StaticFiles(directory=os.path.join("uploads", "mixed_audio")), name="audio")

@app.on_event("startup")
async def on_startup():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created!")

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        print("✅ DB connection warmed up at startup")
    except Exception as e:
        print("❌ Failed to warm up DB:", str(e))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",   
        "http://4.247.144.6",        
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/dj")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text() 
    except Exception:
        pass
    finally:
        connected_clients.remove(websocket)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(user_router, prefix="/user", tags=["User Management"])
app.include_router(song_request_router, prefix="/requests", tags=["Song Requests"])

@app.get("/")
def home():
    return {"message": "Welcome to Music App Backend!"}

# @app.get("/auth/protected")
# async def protected_route(
#     query: str =  Query(None),
#     token: str = Depends(oauth2_scheme),
#     authorization: str = Header(None)
# ):
#     return {
#         "message": "You have access!", 
#         "query": query,
#         "token": token,
#         "authorization_header":authorization
#     }

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Music App Backend",
        version="1.0.0",
        description="Backend APIs",
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
    }

    for path in openapi_schema["paths"].values():
        for method in path:
            path[method]["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    print("✅ Running Uvicorn...") 
    uvicorn.run(app, host="0.0.0.0", port=8085, reload=True)
