from fastapi.websockets import WebSocket, WebSocketDisconnect
connected_clients = [] 

async def handle_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        connected_clients.remove(websocket)

async def broadcast_message(message: dict):
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            print("⚠️ WebSocket connection lost. Removing client.")
            connected_clients.remove(client)

async def broadcast_song_request(song_request):
    message = {
        "action": "new_song_request",
        "data": {
            "song_name": song_request.song_name,
            "artist": song_request.artist,
            "mixed_audio": song_request.mixed_audio_path,
            "custom_lyrics": song_request.custom_lyrics,
            "status": song_request.status.value
        }
    }
    await broadcast_message(message)
