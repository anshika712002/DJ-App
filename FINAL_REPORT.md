# Final Report — Music Mixer (single-role refactor)

Date: 2026-10-12 · Machine: Windows 11 (non-admin), Python 3.12.10, PostgreSQL 17.11 (portable), Flutter 3.47.7 / Dart 3.13.5

## Objective

Convert the previous DJ/Listener app into a simplified **single-role** music
mixing app (login → search → select → mix → My Requests → play completed mix)
and remove DJ-role functionality (accept/reject, live DJ queue, WebSocket) and
restaurant concepts from the real architecture — backend routes/models/auth,
database behaviour and the Flutter client — not just the UI. Existing user data
is preserved; all changes are backward-compatible and require **no migration**.

---

## Status board

| Area | Deliverable | Status |
|-----:|-------------|--------|
| Backend | Models/schemas drop restaurant; single `user` role enforced at signup | ✅ |
| Backend | Auth ignores/normalises `role`; login works without a role | ✅ |
| Backend | Removed DJ endpoints (`accept`/`reject`/`updateStatus`) and `/ws/dj` + `websocket_manager.py` | ✅ |
| Backend | Owner-scoped `/requests/allSongs` and media endpoints (403/401) | ✅ |
| Backend | Background mix lifecycle `pending → completed \| failed` | ✅ |
| Backend tests | `pytest music_backend/tests` → **19 passed** | ✅ |
| Backend E2E | `scripts/smoke_test.py` → **35 passed / 0 failed / 0 skipped** | ✅ |
| Flutter | Removed DJ screens/controller/socket; renamed listener → user | ✅ |
| Flutter | Mix tray, My Requests (polling), play gating, Retry on failure | ✅ |
| Flutter | `flutter analyze` → **0 issues** | ✅ |
| Flutter tests | `flutter test` → **24 passed** (live tests skip offline) | ✅ |
| Docs | `README.md` + this report updated | ✅ |

---

## What changed

### Backend

* `models.py` — removed `Restaurant`; `RoleMaster` no longer references a
  restaurant; `User` and `SongRequest` dropped restaurant columns.
* `schemas.py` — `role` optional on `UserCreate`/`UserLogin`; removed restaurant
  fields and the DJ-only `StatusEnum` / `StatusUpdateSchema` / `SongRequestResponse`.
* `auth.py` — signup forces the `user` role (duplicate checks scoped to it);
  login filters by role only when supplied, otherwise matches any role.
* `song_requests.py` — removed WebSocket notifications; `requestSong` queues the
  background mix and returns `{requestId, message, status: 'pending',
  mixedAudioUrl, tracks}`; `_process_mixing_async` sets `COMPLETED`/`FAILED`;
  `allSongs` is scoped to the caller; both audio endpoints enforce ownership
  (403 for other users, 401 without a token); removed DJ endpoints.
* `user.py` — profile drops restaurant, adds `phone`.
* `main.py` — removed `/ws/dj` and its imports.
* `websocket_manager.py` — deleted.

### Flutter

* Deleted `screens/dj/`, `src/dj_queue_controller.dart`, `src/live_queue.dart`;
  renamed `screens/listener/` → `screens/user/` (`UserShell`, `UserHomeScreen`).
* `src/models.dart` / `src/session.dart` — removed `UserRole`, `parseRole`,
  `role`, `restaurantName`, `isDj`; `signUp`/`login` no longer take a role.
* `src/song_api.dart` — `all()` (owner-scoped) replaces `all({mineOnly,status})`;
  removed `accept`/`reject`/`updateStatus`.
* `screens/user/`, `profile`, `login`, `signup` — removed role selectors and the
  restaurant field; updated copy/branding to "Music Mixer".
* `widgets/request_card.dart` / `theme/app_theme.dart` — lifecycle timeline
  Submitted → Mixing → Ready; playback only for completed/ready; Retry action.
* `pubspec.yaml` — removed `web_socket_channel` (pure-Dart deps only: `http`,
  `provider`, `web`).

### Database

* No new migration. `requeststatus` already supports `completed`/`failed`. The
  `role_master` rows and restaurant columns remain in the schema for
  backward compatibility with existing data.

---

## Verification results

| Check | Result |
|-------|--------|
| `pytest music_backend/tests -q` | **19 passed** |
| `scripts/smoke_test.py` | **35 passed / 0 failed / 0 skipped** — single-role auth, duplicate rejected, profile without restaurant, removed DJ surface (404), YouTube search contract, `pending → completed` with `mixedAudioUrl`, owner 200 / other-user 403 / no-token 401, owner-scoped `allSongs`, traversal → 404 |
| `flutter analyze` | **No issues found!** |
| `flutter test` | **24/24 passed** — models, envelope, widget (splash + login), search view-model, and live integration (skips when API is offline) |

---

## Key environment decisions (unchanged)

1. **SQLAlchemy pinned to 2.0.41** — Smart App Control blocks the native
   `_immutabledict_cy.pyd` in SQLAlchemy ≥ 2.1.
2. **PostgreSQL started via WMI** (`scripts/start_postgres.ps1`) — avoids the
   terminal Job Object crash (`0xC0000142`); readiness probe is a plain TCP check.
3. **Schema owned by Alembic** — startup only verifies tables.
4. **Flutter uses pure-Dart packages only** — Developer Mode is off and the
   account is non-admin, so native plugins cannot compile. Playback is delegated
   externally (Play on YouTube / play mix URL); the app never fakes playback.
5. **UTF-8 stdout reconfigure in `main.py`** — Windows consoles default to cp1252.

---

## Exact commands

### Backend

```powershell
# environment
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# database
powershell -ExecutionPolicy Bypass -File scripts\start_postgres.ps1
.\.venv\Scripts\alembic.exe upgrade head

# unit tests
.\.venv\Scripts\python.exe -m pytest music_backend/tests -q

# run API (from music_backend/, flat imports)
cd music_backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8085

# end-to-end suite (starts/stops its own server)
cd ..
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

### Flutter

```powershell
cd dj_app
flutter pub get
flutter analyze                 # No issues found!
flutter test                    # All tests passed! (24)
flutter run -d windows          # API base via --dart-define=API_BASE=...
```

---

## Known limitations / notes

1. **`requestSong` blocks on the first authorized-YouTube download** — the
   download runs inline before the request is queued (pre-existing behavior;
   covered by unit tests). Cached files make subsequent requests fast. The
   background step then mixes and flips the status to terminal.
2. **No realtime channel** — My Requests polls the owner-scoped endpoint, which
   is sufficient for the single-role flow.
3. **No Android build** — no Android SDK and Developer Mode is off.
4. **Plugin-based features remain off-limits** (encrypted storage, audio plugins).
5. Uncommitted work — ready to commit on request.
