# Final Report — DJ App (Phases 1–19)

Date: 2026-10-08 · Machine: Windows 11 (non-admin), Python 3.12.10, PostgreSQL 17.11 (portable), Flutter 3.47.6 / Dart 3.13.5

## Status board

| Phase | Deliverable | Status |
|------:|-------------|--------|
| 1 | Read-only architecture analysis | ✅ |
| 2 | Python 3.12 + virtualenv + pinned `requirements.txt` | ✅ |
| 3 | PostgreSQL 17 installed/started, `djapp` role + `djapp_db`, `.env` | ✅ |
| 4 | `database.py` / `models.py` rewritten (8 tables, 12 indexes) | ✅ |
| 5 | Alembic init + baseline migration + role seed (round-trip verified) | ✅ |
| 6 | FastAPI fixes (folders, async search, WS manager, lifespan, CORS, UTF-8) | ✅ |
| 7 | Backend E2E smoke suite — **29/29 passed, 0 skipped** | ✅ |
| 8 | Flutter SDK installed, `flutter doctor` | ✅ |
| 9 | `flutter create` (android, windows, web) | ✅ |
| 10 | Flutter config/models/api-client/session/token-store | ✅ |
| 11 | Screens: login, signup, listener home (search + my requests), DJ dashboard | ✅ |
| 12 | WebSocket live queue + audio playback layers | ✅ |
| 13 | `flutter analyze` → **0 issues** | ✅ |
| 14 | `flutter test` → **16/16 passed** (unit + widget + live integration) | ✅ |
| 15 | `flutter build windows --debug` ✔ and `flutter build web --release` ✔, exe boot-tested against live API | ✅ |
| 16 | Security review — 2 findings fixed, 5 documented | ✅ |
| 17 | Cleanup (temp files, broken venv, git hygiene, `.gitignore`) | ✅ |
| 18 | `README.md` with exact commands | ✅ |
| 19 | This report | ✅ |

---

## Key environment decisions (and why)

1. **SQLAlchemy pinned to 2.0.41** — Smart App Control (enforcement mode) blocks the
   unsigned `_immutabledict_cy.pyd` in SQLAlchemy ≥ 2.1. The app crashes on import
   otherwise.
2. **PostgreSQL started through WMI** (`Win32_Process.Create`) — backends die with
   `0xC0000142` when launched inside the terminal's restricted Job Object.
   `scripts/start_postgres.ps1` does this.
3. **The script's readiness probe is a plain TCP check** — the previous `psql -U postgres`
   probe hung forever (superuser has no password → interactive prompt). Fixed during
   Phase 17 testing.
4. **Schema is owned by Alembic** — startup only *verifies* tables and prints
   `alembic upgrade head` as a hint; `create_all` was removed.
5. **Flutter uses pure-Dart packages only** — Developer Mode is off and the account is
   non-admin, so symlinks are impossible; native plugins cannot compile. Storage and
   playback use `dart:io` / `package:web`. Enabling Developer Mode later unlocks
   `shared_preferences`, `just_audio`, Android builds, etc.
6. **UTF-8 stdout reconfigure at import time in `main.py`** — Windows consoles default
   to cp1252 and the app logs emoji (`UnicodeEncodeError` crashes otherwise).

---

## Exact commands

### Backend

```powershell
# environment
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# database
powershell -ExecutionPolicy Bypass -File scripts\start_postgres.ps1
.\.venv\Scripts\alembic.exe upgrade head          # 2 revisions → head d66802f3171b
.\.venv\Scripts\alembic.exe current               # d66802f3171b (head)

# run API (from music_backend/, flat imports)
cd music_backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8085

# end-to-end test suite (starts/stops its own server)
cd ..
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

### Flutter

```powershell
cd dj_app
flutter pub get
flutter analyze                 # No issues found!
flutter test                    # All tests passed! (16)
flutter build windows --debug   # build\windows\x64\runner\Debug\dj_app.exe
flutter build web --release     # build\web
flutter run -d windows          # dev run; API base via --dart-define=API_BASE=...
```

---

## Verification results

| Check | Result |
|-------|--------|
| Alembic `upgrade → downgrade base → upgrade` round trip | 8 tables, 27 indexes, enum + 3 seeded roles, `alembic_version` correct |
| `alembic current` | `d66802f3171b (head)` |
| API startup | `✅ Database connected, schema OK (managed by Alembic)`, 15 routes, docs at `/docs` |
| Smoke suite | **29 passed / 0 failed / 0 skipped** — auth (signup, duplicate, login, bad password, profile, refresh, protected, invalid token), live Audius search + suggestions, request lifecycle with background mixing → `mixedAudioUrl`, audio 200 with token / 401 without, queue + role guard 403, accept / updateStatus playing / played / reject / unknown-id 404, traversal `..%5C..%5C.env` → 404, **unauthenticated `/ws/dj` rejected**, authenticated accepted |
| `flutter analyze` | **No issues found!** |
| `flutter test` | **16/16 passed** — model parsing, envelope, role parsing, widget tests (splash, login, role toggle), plus live integration (real signup → failed login → login → empty queue → Audius search through the Dart client; skips itself when the API is offline) |
| `flutter build windows --debug` | built in 11–13 s |
| `flutter build web --release` | built in ~40 s (fonts tree-shaken) |
| Executable boot test | launched `dj_app.exe` against the live API → stayed alive 10 s, 329 MB RSS, no crash |
| Security re-check after fixes | `GET /audio/` → **404** (static mount removed), anon WS → **rejected** |

---

## Security review (Phase 16)

**Fixed**

1. **Unauthenticated static media mount** — `app.mount("/audio", StaticFiles(...))` served
   every mixed file anonymously, bypassing the token check on
   `/requests/audio/{filename}`. Mount removed; media is reachable only with a Bearer
   token or `?token=`.
2. **Unauthenticated `/ws/dj`** — the socket broadcast requester names, tips and song
   titles. It now requires `?token=<access JWT>` (validated with `decode_access_token`);
   the Flutter `LiveQueue` sends the current token on every (re)connect. Covered by two
   new smoke checks.

**Documented / accepted**

* `SECRET_KEY` falls back to `"mysecret"` with a loud warning — make it fatal before a
  production deploy.
* Access JWTs live 12 h, refresh 90 days with `jti`/`iat`.
* Session persistence is plaintext: `%APPDATA%\.dj_app\session.json` (Windows) /
  `localStorage` (web). Encrypted storage needs a native plugin → possible after
  Developer Mode is enabled.
* CORS is `*` with `allow_credentials=False` (Bearer-only auth, explicit headers).
* `uvicorn ... --host 0.0.0.0` in `main.py`'s `__main__` block — run through
  `127.0.0.1` (as all commands here do) unless LAN access is wanted.
* DB is non-superuser `djapp`, scram-sha-256, bound to `127.0.0.1`; PostgreSQL data dir
  is local to the user profile.
* Path traversal, missing-file and missing-token cases all return 404/401.

---

## Cleanup performed (Phase 17)

* Deleted: `_phase5_check.py`, `server.log`, `boot_check.log`, stray 0-byte `outputs`
  and `uploads` placeholder files.
* Removed the broken **`env/`** virtualenv **from disk and from the git index**
  (690 of the 708 tracked files were venv junk in the single existing commit).
* Untracked `music_backend/cookies.txt` (yt-dlp cookie jar — visitor tokens only, but a
  cookie jar does not belong in git).
* Rewrote `.gitignore`: environments, `.env*`, logs, runtime media
  (`audius_downloads/`, `uploads/`), cookie jar, build/test caches.

`git status` now shows only the real work: modified backend files, new `alembic/`,
`scripts/`, `dj_app/`, `README.md` — nothing has been committed (say the word and I'll
stage and commit).

---

## Known limitations / optional next steps

1. **No Android build yet** — Flutter reports *no Android SDK*, and Developer Mode is
   off. Enabling Developer Mode → install Android SDK → `flutter build apk`.
2. **Plugin-based features are off-limits** right now (encrypted storage, audio
   plugins) — same Developer Mode constraint; the current pure-Dart replacements work.
3. **Audius track availability is external** — some tracks return `403`, which the API
   now surfaces as a structured **400** (`These tracks are not available …`) instead of a
   500. The smoke test retries automatically until it finds streamable pair.
4. **Mixing is ffmpeg-only** (installed via winget); refresh `$env:Path` in any shell
   opened before the install.
5. Uncommitted work — ready to commit on request.
