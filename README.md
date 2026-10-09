# DJ App

A full-stack song-request app: listeners discover YouTube playback results and
request mixes from server-managed local or licensed audio assets. The DJ dashboard
accepts/plays requests, and the backend mixes eligible audio in the background.

| Layer     | Tech |
|-----------|------|
| API       | FastAPI + Uvicorn (async) |
| Database  | PostgreSQL 17, SQLAlchemy 2.0 (async), Alembic migrations |
| Auth      | JWT access + refresh tokens, bcrypt password hashing |
| Live feed | WebSockets (`/ws/dj`, JWT-gated) |
| Client    | Flutter (Windows, Web, Android-ready) |
| Media     | ffmpeg mixing (overlay / alternate / crossfade / tempo-sync / pitch-shift / beat-overlay / no-mix) |

---

## Repository layout

```
DJ-App/
├── music_backend/          FastAPI application
│   ├── main.py             app factory, lifespan, CORS, websocket
│   ├── auth.py / user.py   signup, login, refresh, profile
│   ├── song_requests.py    search, request, queue, status, audio streaming
│   ├── process_audio.py    ffmpeg-based audio mixing
│   ├── models.py           SQLAlchemy models
│   └── schemas.py          Pydantic request/response models
├── alembic/                migrations (baseline schema + role seed)
├── scripts/
│   ├── start_postgres.ps1  starts the portable PostgreSQL server
│   └── smoke_test.py       29-check end-to-end test suite
├── dj_app/                 Flutter client
│   ├── lib/src/            api client, session, models, websocket, audio
│   ├── lib/screens/        login, signup, search, my requests, DJ dashboard
│   └── test/               unit, widget and live integration tests
├── .env                    local configuration (git-ignored)
├── alembic.ini
└── requirements.txt
```

---

## Prerequisites

* **Windows 10/11** (commands below are PowerShell)
* **Python 3.12** (project was built on 3.12.10)
* **PostgreSQL 17** – portable install at `%LOCALAPPDATA%\pgsql17\pgsql`
* **ffmpeg** (on the user `PATH`, e.g. `Gyan.FFmpeg` via winget)
* **Flutter 3.47 / Dart 3.13** (only for the client)

---

## 1. Python environment

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> **Why SQLAlchemy 2.0.41?** This machine runs Smart App Control in enforcement
> mode, which blocks the native `_immutabledict_cy.pyd` shipped with
> SQLAlchemy ≥ 2.1. The pin in `requirements.txt` is intentional – keep it.

## 2. Configuration (`.env`)

Create `.env` in the repository root (git-ignored):

```ini
DATABASE_URL=postgresql+asyncpg://djapp:<password>@127.0.0.1:5432/djapp_db
SECRET_KEY=<long random string>
PUBLIC_API_BASE=
CORS_ORIGINS=*
YOUTUBE_API_KEY=<YouTube Data API v3 key>
YOUTUBE_ALLOWED_CHANNEL_IDS=UCxxxxxxxxxxxxxxxxxxxxxx
```

* `PUBLIC_API_BASE` empty ⇒ media URLs are returned relative (`/requests/audio/...`).
* Search uses YouTube Data API v3. YouTube results are playback/discovery
  tracks with a YouTube watch URL and no server audio-download URL. Audio
  processing through the existing authorized YouTube path is limited to the
  comma-separated channel IDs in `YOUTUBE_ALLOWED_CHANNEL_IDS`; add only
  channels whose videos you own or are authorized to process. The API key
  enables search and metadata access; it does not authorize downloading or
  processing audio. Other YouTube results can be played on YouTube but cannot
  be mixed.
* Authenticated users can upload audio through `POST /tracks/assets` (also
  available in Swagger). The uploader must confirm their rights and provide
  the license and attribution. `local` assets are private to the uploader;
  `licensed` and `public_domain` assets are available in the shared catalog.
  Files are stored under a server-generated name in `music_backend/audio_assets`
  (or the configured `AUDIO_ASSET_DIR`), never at a client-supplied path.
  The singular `YOUTUBE_ALLOWED_CHANNEL_ID` is also accepted for existing
  `.env` files; the plural name is preferred when configuring multiple channels.
* `CORS_ORIGINS` is a comma-separated list; `*` is safe because the API uses
  Bearer tokens only (no cookies, `allow_credentials=False`).

## 3. PostgreSQL

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_postgres.ps1
```

Notes:

* The script launches the existing `postgres.exe` directly from the scheduled
  task, using the cluster in `C:\ProgramData\pgsql17\data`. It does not register
  a Windows service or change Windows security policy.
* The readiness probe is a plain TCP check – never use
  `psql -U postgres -h 127.0.0.1`: the superuser has no password and the
  client blocks forever on an interactive prompt.
* Application login uses the non-superuser role `djapp` with scram-sha-256.

## 4. Database migrations

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

Applies three revisions:

1. `e9c1e8a6176c` – baseline: 8 tables, enums, indexes
2. `d66802f3171b` – seeds `role_master` with `user`, `dj`, `admin` (idempotent)
3. `71c2a6f9b43d` – source-aware audio assets and request track metadata

```powershell
.\.venv\Scripts\alembic.exe current      # should print: d66802f3171b (head)
.\.venv\Scripts\alembic.exe downgrade base   # optional round-trip check
.\.venv\Scripts\alembic.exe upgrade head
```

## 5. Run the API

```powershell
cd music_backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8085
```
On startup the app verifies the schema (it never calls `create_all`; Alembic owns
the schema) and prints `✅ Database connected, schema OK`.

Interactive API docs: <http://127.0.0.1:8085/docs>

## 6. Backend test suite

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

Starts its own server on `127.0.0.1:8085`, runs **29 checks** (auth, refresh,
role guards, YouTube search, authorized-channel request lifecycle with background mixing,
token-protected audio streaming, path-traversal defence, WebSocket auth) and
shuts the server down again.

## 7. Flutter client

```powershell
cd dj_app
flutter pub get
flutter run -d windows            # desktop
flutter run -d chrome             # web
```

Builds that were verified on this machine:

```powershell
flutter analyze                   # 0 issues
flutter test                      # 16 tests (live API tests skip when offline)
flutter build windows --debug     # build\windows\x64\runner\Debug\dj_app.exe
flutter build web --release       # build\web
```

The API base URL is a compile-time define (default `http://127.0.0.1:8085`):

```powershell
flutter run -d android --dart-define=API_BASE=http://10.0.2.2:8085   # emulator
flutter build windows --release --dart-define=API_BASE=http://192.168.1.10:8085
```

### Client architecture

* `src/api_client.dart` – JSON + Bearer auth, one automatic refresh-and-retry on 401
* `src/session.dart` – login/signup/refresh/logout, persists the session
* `src/token_store.dart` – `%APPDATA%\.dj_app\session.json` (desktop), `localStorage` (web)
* `src/song_api.dart` – search, queue, status transitions, media URLs
* `src/live_queue.dart` – `/ws/dj` reconnecting socket (token passed as query param)
* `screens/` – login, signup, listener home (search + my requests), DJ dashboard

> **Why pure-Dart packages only?** This Windows account has no administrator
> rights and Developer Mode is off, so symbolic links cannot be created.
> Flutter's native plugin tooling requires symlinks, which means packages with
> native code (`shared_preferences`, `just_audio`, …) cannot build here.
> Storage/playback therefore use `dart:io`, `package:web` and the standard
> `http`/`provider`/`web_socket_channel` packages – the whole app compiles with
> zero plugins. Enable *Settings → System → For developers → Developer Mode*,
> then `flutter pub add shared_preferences` (or an encrypted store) works again.

---

## API surface

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/signup` | `userName`, `phone`, `password`, `role` (`user`/`dj`), optional `email`, `restaurantName` |
| POST | `/auth/login` | `identifier` (email or phone), `password`, `role` |
| POST | `/auth/refresh` | body field is **`refresh_token`** |
| GET  | `/user/profile` | Bearer required |
| GET  | `/requests/searchSong?q=` | YouTube Data API search, writes search history |
| GET  | `/requests/suggestedSongs` | suggestions from past searches |
| POST | `/requests/requestSong` | `tracks: [{trackId, sourceType}]` (1–2), `tipAmount?`, `mixer?`; only authorized YouTube or server-managed assets can mix |
| GET | `/tracks/assets?q=` | Authenticated catalog search for local/licensed/public-domain audio |
| POST | `/tracks/assets` | Authenticated multipart upload with title, source type, license, attribution, and rights confirmation |
| GET | `/tracks/assets/{id}/audio?token=` | Authenticated audio playback for a server-managed asset |
| GET  | `/requests/allSongs?mineOnly=&status=` | queue; `status` honoured for DJ/admin |
| PUT  | `/requests/accept/{id}` / `reject/{id}` / `updateStatus/{id}` | DJ/admin only |
| GET  | `/requests/audio/{filename}` | Bearer **or** `?token=` for media players |
| WS   | `/ws/dj?token=` | `new_song_request` + `status_update` events |

All responses use the envelope `{statusCode, status, data}`; use `statusCode`
for logic and `status` for the human-readable message.

YouTube results use the shared Track fields `trackId`, `sourceType`, `title`,
`artist`, `artwork`, `duration`, `playbackUrl`, `mixEligible`, `license`, and
`attribution`. The Flutter search view provides a **Play on YouTube** action;
playback-only tracks are not selectable for mixing. Local/library uploads can
be searched and selected in Flutter. The first implementation intentionally
does not include an in-app native file picker; upload through the authenticated
API/Swagger interface.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'auth'` | run uvicorn from `music_backend/` (flat imports) or set `PYTHONPATH=music_backend` |
| Backend exits with `0xC0000142` | start PostgreSQL with `scripts\start_postgres.ps1` (outside the Job Object) |
| `psql -U postgres` hangs | superuser has no password; use `-U djapp` with `PGPASSWORD`, or a TCP probe |
| `ffmpeg` not found | refresh `$env:Path` from the registry after installing (`[Environment]::GetEnvironmentVariable("Path","User")`) |
| `UnicodeEncodeError` in logs | fixed in `music_backend/main.py` (stdout reconfigured to UTF-8) |
| `InsufficientSystemResources` / DLL blocked | Smart App Control – keep SQLAlchemy 2.0.41 |
| Flutter plugin build fails | see the pure-Dart note above |
| Windows exe cannot reach the API | build with `--dart-define=API_BASE=http://<host-ip>:8085` |
