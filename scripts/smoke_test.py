"""End-to-end smoke test for the Music App backend (FastAPI + PostgreSQL).

Starts the API server, exercises every endpoint group against the real
database, then shuts the server down. Run from the repo root:

    .venv\\Scripts\\python.exe scripts\\smoke_test.py
"""
import os
import io
import math
import struct
import subprocess
import sys
import time
import uuid
import wave

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "http://127.0.0.1:8085"
LOG_PATH = os.path.join(ROOT, "server.log")

PASS, FAIL, SKIP = [], [], []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{(' - ' + str(detail)) if detail else ''}")


def skip(name, detail=""):
    SKIP.append(name)
    print(f"  [SKIP] {name}{(' - ' + str(detail)) if detail else ''}")


def sample_wav():
    output = io.BytesIO()
    sample_rate = 16000
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        frames = (
            struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
            for i in range(sample_rate)
        )
        audio.writeframes(b"".join(frames))
    return output.getvalue()


def wait_for_server(client, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if client.get("/").status_code == 200:
                return True
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    return False


def main():
    stamp = uuid.uuid4().hex[:8]
    user_a, mail_a, phone_a = f"user_{stamp}", f"user_{stamp}@example.com", f"9000{stamp[:7]}"
    user_b, mail_b, phone_b = f"other_{stamp}", f"other_{stamp}@example.com", f"9100{stamp[:7]}"
    password = "TestPassw0rd!"

    env = dict(os.environ)
    # This shell may predate the winget PATH entry; locate ffmpeg explicitly.
    import glob
    ffmpeg_dirs = [
        os.path.dirname(p)
        for p in glob.glob(
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\**\ffmpeg.exe"),
            recursive=True,
        )
    ]
    if ffmpeg_dirs:
        env["PATH"] = os.pathsep.join(ffmpeg_dirs + [env.get("PATH", "")])

    log = open(LOG_PATH, "w", encoding="utf-8", errors="replace")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", "8085", "--log-level", "info"],
        cwd=os.path.join(ROOT, "music_backend"),
        stdout=log, stderr=subprocess.STDOUT, env=env,
    )

    try:
        with httpx.Client(base_url=BASE_URL, timeout=30) as client:
            if not wait_for_server(client):
                check("server starts", False, "did not respond within 60s")
                return

            print("\n-- auth (single role) --")
            r = client.get("/")
            check("GET / welcome", r.status_code == 200 and "message" in r.json(), r.status_code)

            # role is intentionally omitted: every account is a plain user now.
            r = client.post("/auth/signup", json={
                "userName": user_a, "email": mail_a, "password": password,
                "phone": phone_a,
            })
            body = r.json()
            check("signup without role", body.get("status") == "success",
                  f"{r.status_code} {r.text[:200]}")
            check("signup assigns user role",
                  body.get("data", {}).get("role") == "user",
                  body.get("data", {}).get("role"))

            r = client.post("/auth/signup", json={
                "userName": user_b, "email": mail_b, "password": password,
                "phone": phone_b,
            })
            check("second signup", r.json().get("status") == "success",
                  f"{r.status_code} {r.text[:200]}")

            r = client.post("/auth/signup", json={
                "userName": user_a, "email": mail_a, "password": password,
                "phone": phone_a, "role": "dj",
            })
            check("signup duplicate rejected (role ignored)", r.json().get("statusCode") == 400,
                  f"{r.status_code} {r.text[:200]}")

            r = client.post("/auth/login", json={"identifier": mail_a, "password": password})
            login = r.json().get("data", {})
            token_a = login.get("accessToken")
            refresh_token = login.get("refreshToken")
            check("login without role", bool(token_a), f"{r.status_code} {r.text[:200]}")
            check("login returns user role", login.get("role") == "user", login.get("role"))

            r = client.post("/auth/login", json={"identifier": mail_b, "password": password})
            token_b = r.json().get("data", {}).get("accessToken")
            check("second login", bool(token_b), f"{r.status_code} {r.text[:200]}")

            r = client.post("/auth/login", json={"identifier": mail_a, "password": "wrong"})
            check("bad password rejected", r.json().get("statusCode") == 401, r.text[:200])

            r = client.get("/user/profile", headers={"Authorization": f"Bearer {token_a}"})
            profile = r.json().get("data", {}) if r.status_code == 200 else {}
            check("GET /user/profile", r.status_code == 200, r.text[:200])
            check("profile has no restaurant field", "restaurantName" not in profile)

            r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
            new_tokens = r.json().get("data", {})
            check("POST /auth/refresh", bool(new_tokens.get("accessToken")), f"{r.status_code} {r.text[:200]}")
            token_a = new_tokens.get("accessToken") or token_a

            r = client.get("/auth/protected", headers={"Authorization": f"Bearer {token_a}"})
            check("GET /auth/protected", r.status_code == 200, r.status_code)
            r = client.get("/auth/protected", headers={"Authorization": "Bearer bogus.token.here"})
            check("invalid token rejected", r.status_code == 401, r.status_code)

            print("\n-- removed DJ surface --")
            r = client.get("/ws/dj?token=x")
            check("/ws/dj route removed", r.status_code in (403, 404), r.status_code)
            r = client.put("/requests/accept/1", headers={"Authorization": f"Bearer {token_a}"})
            check("PUT /requests/accept removed", r.status_code in (404, 405), r.status_code)
            r = client.put("/requests/reject/1", headers={"Authorization": f"Bearer {token_a}"})
            check("PUT /requests/reject removed", r.status_code in (404, 405), r.status_code)
            r = client.put("/requests/updateStatus/1", headers={"Authorization": f"Bearer {token_a}"},
                           json={"status": "playing"})
            check("PUT /requests/updateStatus removed", r.status_code in (404, 405), r.status_code)

            print("\n-- search / suggestions (YouTube Data API) --")
            r = client.get("/requests/searchSong", params={"q": "love"},
                           headers={"Authorization": f"Bearer {token_a}"})
            search_ok = r.status_code == 200
            tracks = r.json().get("results", []) if search_ok else []
            check("GET /requests/searchSong", search_ok and len(tracks) > 0,
                  f"{r.status_code}, {len(tracks)} tracks")
            contract_ok = all(
                track.get("sourceType") == "youtube"
                and track.get("playbackUrl", "").startswith(
                    "https://www.youtube.com/watch?v="
                )
                and not any("download" in key.lower() for key in track)
                for track in tracks
            )
            check("YouTube results are playback-only tracks", contract_ok)

            r = client.get("/requests/suggestedSongs", headers={"Authorization": f"Bearer {token_a}"})
            check("GET /requests/suggestedSongs", r.status_code == 200, r.status_code)

            r = client.get("/requests/searchHistory", headers={"Authorization": f"Bearer {token_a}"})
            history = r.json().get("queries", []) if r.status_code == 200 else []
            check("GET /requests/searchHistory", r.status_code == 200 and "love" in history,
                  f"{r.status_code} {history}")

            print("\n-- song request lifecycle (pending -> completed) --")
            request_id = None
            authorized_tracks = [
                track for track in tracks if track.get("mixEligible")
            ]
            request_error = ""
            if authorized_tracks:
                r = client.post("/requests/requestSong", headers={"Authorization": f"Bearer {token_a}"},
                                json={
                                    "tracks": [
                                        {
                                            "trackId": authorized_tracks[0]["trackId"],
                                            "sourceType": "youtube",
                                        }
                                    ],
                                    "mixer": "without-mixing",
                                },
                                timeout=300)
                if r.status_code == 200:
                    request_id = r.json().get("requestId")
                    check("requestSong returns pending",
                          r.json().get("status") == "pending", r.json().get("status"))
                else:
                    request_error = f"{r.status_code} {r.text[:150]}"
            if not authorized_tracks:
                skip("POST /requests/requestSong",
                     "no configured authorized channel matched search")
            else:
                check("POST /requests/requestSong", bool(request_id),
                      request_error or f"requestId={request_id}")

            # wait for the background mix to finish
            mixed_url = None
            final_status = None
            if request_id:
                deadline = time.time() + 120
                while time.time() < deadline:
                    r = client.get("/requests/allSongs",
                                   headers={"Authorization": f"Bearer {token_a}"})
                    items = r.json().get("data", [])
                    mine = [i for i in items if i["songRequestId"] == request_id]
                    if mine:
                        final_status = mine[0].get("songStatus")
                        if final_status in ("completed", "failed"):
                            mixed_url = mine[0].get("mixedAudioUrl")
                            break
                    time.sleep(2)
                check("background mixing reaches terminal status",
                      final_status in ("completed", "failed"), final_status)
                check("completed mix exposes mixedAudioUrl",
                      final_status == "failed" or bool(mixed_url),
                      "timeout after 120s" if final_status is None else mixed_url)

            if mixed_url:
                audio_url = mixed_url if mixed_url.startswith("http") else BASE_URL + mixed_url
                r = client.get(audio_url, headers={"Authorization": f"Bearer {token_a}"})
                check("owner can GET mixed audio", r.status_code == 200
                      and r.headers.get("content-type", "").startswith("audio"),
                      f"{r.status_code} {r.headers.get('content-type')}")
                r = client.get(audio_url, headers={"Authorization": f"Bearer {token_b}"})
                check("other user cannot GET mixed audio", r.status_code == 403, r.status_code)
                r = client.get(audio_url)
                check("mixed audio requires token", r.status_code == 401, r.status_code)
            elif request_id:
                skip("audio ownership checks", "mix did not complete")

            r = client.get("/requests/allSongs", headers={"Authorization": f"Bearer {token_a}"})
            items = r.json().get("data", []) if r.status_code == 200 else []
            check("GET /requests/allSongs", r.status_code == 200, f"{len(items)} rows")
            fields_ok = all("restaurantName" not in i for i in items)
            check("allSongs omits restaurant field", fields_ok)

            r = client.get("/requests/allSongs", headers={"Authorization": f"Bearer {token_b}"})
            other_items = r.json().get("data", []) if r.status_code == 200 else []
            check("allSongs is scoped to the owner",
                  all(i["songRequestId"] != request_id for i in other_items),
                  f"{len(other_items)} rows for user B")

            print("\n-- security: audio path traversal --")
            r = client.get("/requests/audio/..%5C..%5C.env",
                           headers={"Authorization": f"Bearer {token_a}"})
            check("traversal blocked", r.status_code == 404, r.status_code)
            r = client.get("/requests/audio/nope.mp3", headers={"Authorization": f"Bearer {token_a}"})
            check("missing file -> 404", r.status_code == 404, r.status_code)
            r = client.get("/requests/audio/nope.mp3")
            check("audio without token -> 401", r.status_code == 401, r.status_code)

    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()

    print(f"\n=== RESULT: {len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped ===")
    if FAIL:
        print("Failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
