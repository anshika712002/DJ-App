from fastapi.websockets import WebSocket, WebSocketDisconnect

connected_clients = []


async def handle_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)


async def broadcast_message(message: dict):
    # Iterate a copy: a dead client is removed inside the loop
    for client in list(connected_clients):
        try:
            await client.send_json(message)
        except Exception:
            print("⚠️ WebSocket connection lost. Removing client.")
            if client in connected_clients:
                connected_clients.remove(client)


async def broadcast_song_request(song_request):
    status = song_request.status
    message = {
        "action": "new_song_request",
        "data": {
            "songRequestId": song_request.id,
            "songName": song_request.songName,
            "artist": song_request.videoArtist1,
            "mixedAudioPath": song_request.mixedAudioPath,
            "status": status.value if hasattr(status, "value") else str(status),
        }
    }
    await broadcast_message(message)
