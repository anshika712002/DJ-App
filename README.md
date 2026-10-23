# Music Mixer

A full-stack, single-role music app: users sign in, search songs, pick one or
two tracks, submit a mix, then track and play the finished mix. The backend
prepares each mix in the background and gates playback on real status.

```text
Login → Search → Select songs → Mix → My Requests → Play completed mix
```

There is no DJ role and no request accept/reject workflow. Every account is a
plain **user**; the backend owns request status end-to-end.

| Layer    | Tech |
|----------|------|
| API      | FastAPI + Uvicorn (async) |
| Database | PostgreSQL 17, SQLAlchemy 2.0 (async), Alembic migrations |
| Auth     | JWT access + refresh tokens, bcrypt password hashing |
| Client   | Flutter (Windows, Web, Android-ready) |
| Media    | ffmpeg mixing (overlay / alternate / crossfade / tempo-sync / pitch-shift / beat-overlay / no-mix) |

---

## Repository layout

```
DJ-App/
├── music_backend/          FastAPI application
│   ├── main.py             app factory, lifespan, CORS
│   ├── auth.py / user.py   signup, login, refresh, profile
│   ├── song_requests.py    search, request, mixing, audio streaming
│   ├── process_audio.py    ffmpeg-based audio mixing
│   ├── models.py           SQLAlchemy models
│   └── schemas.py          Pydantic request/response models
├── alembic/                migrations (baseline schema + role seed)
├── scripts/
│   ├── start_postgres.ps1  starts the portable PostgreSQL server
│   └── smoke_test.py       35-check end-to-end test suite
├── dj_app/                 Flutter client
│   ├── lib/src/            api client, session, models, search, playback
│   ├── lib/screens/        login, signup, user home/search/requests/profile
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
YOUTUBE_ALLOWED_CHANNEL_ID=<comma-separated channel IDs>
```

* `PUBLIC_API_BASE` empty ⇒ media URLs are returned relative (`/requests/audio/...`).
* Search uses YouTube Data API v3. YouTube results are playback/discovery
  tracks with a YouTube watch URL and no server audio-download URL. Audio
  processing through the existing authorized YouTube path is limited to the
  comma-separated channel IDs in `YOUTUBE_ALLOWED_CHANNEL_ID`
  (`YOUTUBE_ALLOWED_CHANNEL_IDS` is also accepted); add only channels whose
  videos you own or are authorized to process. The API key enables search and
  metadata access; it does not authorize downloading or processing audio.
  Other YouTube results can be played on YouTube but cannot be mixed.
* Authenticated users can upload audio through `POST /tracks/assets` (also
  available in Swagger). The uploader must confirm their rights and provide
  the license and attribution. `local` assets are private to the uploader;
  `licensed` and `public_domain` assets are available in the shared catalog.
  Files are stored under a server-generated name in `music_backend/audio_assets`
  (or the configured `AUDIO_ASSET_DIR`), never at a client-supplied path.
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

1. `e9c1e8a6176c` – baseline: tables, enums, indexes
2. `d66802f3171b` – seeds `role_master` with `user`, `dj`, `admin` (idempotent)
3. `71c2a6f9b43d` – source-aware audio assets and request track metadata

> The single-role change is **application-level only**. The schema still seeds
> the `dj`/`admin` role rows and keeps the restaurant columns for backward
> compatibility with existing data; no new migration is required.

### Backend unit tests

```powershell
.\.venv\Scripts\python.exe -m pytest music_backend/tests -q
```

## 5. Run the API

```powershell
cd music_backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8085
```
On startup the app verifies the schema (it never calls `create_all`; Alembic owns
the schema) and prints `✅ Database connected, schema OK`.

Interactive API docs: <http://127.0.0.1:8085/docs>

## 6. End-to-end smoke test

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

Starts its own server on `127.0.0.1:8085`, runs **35 checks** (single-role auth,
removed DJ surface, YouTube search, background mix lifecycle `pending →
completed`, owner-scoped audio with 403/401, path-traversal defence) and shuts
the server down again.

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
flutter test                      # 24 tests (live API tests skip when offline)
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
* `src/song_api.dart` – search, request, owner-scoped request list, media URLs
* `src/my_requests_controller.dart` – polls the user's own requests (no realtime socket)
* `src/search_view_model.dart` – debounced, stale-safe search
* `screens/user/` – user home, search/mix builder and My Requests

> **Why pure-Dart packages only?** This Windows account has no administrator
> rights and Developer Mode is off, so symbolic links cannot be created.
> Flutter's native plugin tooling requires symlinks, which means packages with
> native code (`shared_preferences`, `just_audio`, …) cannot build here.
> Storage/playback therefore use `dart:io`, `package:web` and the standard
> `http`/`provider` packages – the whole app compiles with zero plugins. Enable
> *Settings → System → For developers → Developer Mode*, then
> `flutter pub add shared_preferences` (or an encrypted store) works again.

---

## API surface

| Method | Path | Notes |
|--------|------|-------|
| POST | `/auth/signup` | `userName`, `phone`, `password`, optional `email`; any `role` is ignored (always `user`) |
| POST | `/auth/login` | `identifier` (email or phone), `password`; `role` optional and matched if provided |
| POST | `/auth/refresh` | body field is **`refresh_token`** |
| GET  | `/user/profile` | Bearer required |
| GET  | `/requests/searchSong?q=` | YouTube Data API search, writes search history |
| GET  | `/requests/suggestedSongs` | suggestions from past searches |
| POST | `/requests/requestSong` | `tracks: [{trackId, sourceType}]` (1–2), `mixer?`; returns `requestId` + `status: pending` |
| GET  | `/requests/allSongs` | the caller's own requests (newest first); no role/queue params |
| GET  | `/requests/audio/byRequestId/{id}` | owner-only mixed audio (403 for others, 401 without token) |
| GET  | `/requests/audio/{filename}` | owner-only mixed audio by filename |
| GET  | `/tracks/assets?q=` | Authenticated catalog search for local/licensed/public-domain audio |
| POST | `/tracks/assets` | Authenticated multipart upload with title, source type, license, attribution, and rights confirmation |
| GET  | `/tracks/assets/{id}/audio?token=` | Authenticated audio playback for a server-managed asset |

All responses use the envelope `{statusCode, status, data}`; use `statusCode`
for logic and `status` for the human-readable message.

Request lifecycle: `pending` → (`completed` | `failed`). Playback in the Flutter
client is enabled only when the status is `completed`/`ready` and an audio URL
exists; failed mixes expose a **Retry** action that re-submits the same tracks.
Legacy `accepted`/`playing`/`played` rows remain readable for old data.

YouTube results use the shared Track fields `trackId`, `sourceType`, `title`,
`artist`, `artwork`, `duration`, `playbackUrl`, `mixEligible`, `license`, and
`attribution`. The Flutter search view provides a **Play on YouTube** action;
playback-only tracks are not selectable for mixing. Local/library uploads can
be searched and selected in Flutter through the authenticated API/Swagger.

## Render staging (Docker)

The repository includes a root `Dockerfile` that installs FFmpeg and starts
Uvicorn from `music_backend/` so the backend's flat imports resolve. It binds
to Render's `PORT` (defaulting to `10000` for local container runs). Use the
repository root as the service root and Docker as the runtime. `.dockerignore`
excludes local environment files, tests, caches, and media from the image build
context; it does not remove those files from Git.
The Docker build verifies that the `yt-dlp` Python package, `ffmpeg`, and
`ffprobe` are available. If an authorized YouTube download fails, check the
Render service logs for the underlying downloader error; the API response
intentionally stays generic.
If yt-dlp reports “Sign in to confirm you're not a bot,” this is a YouTube
server-side download block, not a missing FFmpeg dependency. Use an authorized
audio upload instead; installing more system packages will not resolve it.

Configure these variables in the Render service environment, never in source:
`DATABASE_URL`, `SECRET_KEY`, `YOUTUBE_API_KEY`, and, for authorized YouTube
audio processing, `YOUTUBE_ALLOWED_CHANNEL_ID` or
`YOUTUBE_ALLOWED_CHANNEL_IDS`. `CORS_ORIGINS` can restrict browser clients.
The optional `YOUTUBE_DOWNLOADS_DIR`, `MIXED_AUDIO_DIR`, and `AUDIO_ASSET_DIR`
can point to configured storage; the existing local defaults are unchanged.

The service exposes `/health/live` for process liveness and `/health/ready` for
a database readiness check. Run migrations once, deliberately, from the
repository root with `alembic upgrade head` after verifying the target
`DATABASE_URL`; migrations are not run automatically at service startup.

Render's free service filesystem is ephemeral. Uploaded audio and completed
mixes may disappear after sleep, restart, or redeploy, so free staging verifies
only the workflow while files remain available on the running instance. A free
Render Postgres database expires 30 days after creation and is deleted after a
14-day upgrade grace period. Keep a separate export if the staging data matters.
The first request after a free web service sleeps can take about a minute to
wake it.

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
| `requestSong` is slow on first call | the authorized YouTube download runs inline before the request is queued; subsequent plays use the cached file |
