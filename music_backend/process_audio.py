import os
import math
import time
import ffmpeg
import httpx
import shutil
from pydub import AudioSegment
from gtts import gTTS
from datetime import datetime
from pydub.effects import normalize
import asyncio

# -----------------------------
# CONSTANTS
# -----------------------------
AUDIUS_API_BASE = "https://discoveryprovider.audius.co/v1"
APP_NAME = "djapp"

# FINAL USER-REQUESTED FOLDER PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ORIGINAL DOWNLOADED AUDIO FOLDER (ABSOLUTE PATH)
AUDIUS_DOWNLOADS_FOLDER = r"C:\Users\Dell\Desktop\Audius API\music_backend\audius_downloads"
os.makedirs(AUDIUS_DOWNLOADS_FOLDER, exist_ok=True)

os.environ["PYDUB_FFMPEG_LOGLEVEL"] = "quiet"

SEG_MS = 10000
BG_ATTENUATE_DB = -8
TODAY = datetime.now().strftime("%Y-%m-%d")


# ------------------------------------------------------------
#  🔊 AUDIO PROCESSING FUNCTIONS (UNCHANGED)
# ------------------------------------------------------------
def generate_singing_vocals(lyrics: str, output_path: str) -> str:
    tts = gTTS(lyrics, lang="en")
    tts.save(output_path)
    return output_path


def crossfade_tracks(track1_path, track2_path, output_path, fade_duration=3000):
    track1 = AudioSegment.from_file(track1_path)
    track2 = AudioSegment.from_file(track2_path)
    fade_duration = min(fade_duration, len(track1), len(track2))
    mixed = track1.append(track2, crossfade=fade_duration)
    mixed.export(output_path, format="mp3", bitrate="192k")
    return output_path


def change_pitch(audio_path, output_path, semitones=2):
    ratio = 2 ** (semitones / 12.0)
    ffmpeg.input(audio_path).output(
        output_path,
        af=f"asetrate=44100*{ratio},aresample=44100"
    ).overwrite_output().run(quiet=True)
    return output_path


def change_tempo(audio_path, output_path, speed=1.2):
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Tempo speed must be between 0.5 and 2.0")
    ffmpeg.input(audio_path).output(
        output_path,
        af=f"atempo={speed}"
    ).overwrite_output().run(quiet=True)
    return output_path


def mix_audio(audio1_path, audio2_path, output_path):
    track1 = AudioSegment.from_file(audio1_path)
    track2 = AudioSegment.from_file(audio2_path)
    min_len = min(len(track1), len(track2))
    mixed = track1[:min_len].overlay(track2[:min_len])
    mixed.export(output_path, format="mp3", bitrate="192k")
    return output_path


def mashup_tracks(a_path: str, b_path: str, out_path: str, seg_ms: int = SEG_MS):
    a = AudioSegment.from_file(a_path)
    b = AudioSegment.from_file(b_path)

    chunks = list(zip(_chunks(a, seg_ms), _chunks(b, seg_ms)))
    tail = a[len(chunks) * seg_ms:] if len(a) > len(b) else b[len(chunks) * seg_ms:]

    combined = AudioSegment.empty()
    for a_seg, b_seg in chunks:
        combined += a_seg + b_seg

    combined += tail
    combined.export(out_path, format="mp3", bitrate="192k")
    return out_path


def _chunks(track: AudioSegment, seg_ms: int):
    for i in range(0, len(track), seg_ms):
        yield track[i:i + seg_ms]


def overlay_tracks(main_path: str, bg_path: str, out_path: str, bg_db: int = BG_ATTENUATE_DB):
    main = AudioSegment.from_file(main_path)
    bg = AudioSegment.from_file(bg_path)

    main = normalize(main) - 6
    bg = normalize(bg) - 6

    loops = math.ceil(len(main) / len(bg))
    bg_full = (bg * loops)[:len(main)]

    combined = main.overlay(bg_full)
    combined.export(out_path, format="mp3", bitrate="192k")
    return out_path


def overlay_beat(main_path: str, beat_path: str, out_path: str, bg_db: int = BG_ATTENUATE_DB):
    return overlay_tracks(main_path, beat_path, out_path, bg_db)


# ------------------------------------------------------------
# 🔍 Audius Search
# ------------------------------------------------------------
def search_audius_tracks(query: str, limit: int = 5):
    url = f"{AUDIUS_API_BASE}/tracks/search"
    params = {"query": query, "limit": limit}

    try:
        response = httpx.get(url, params=params)
        response.raise_for_status()

        data = response.json().get("data", [])

        return [
            {
                "trackId": t["id"],
                "title": t["title"],
                "artist": t["user"]["name"],
                "artwork": t.get("artwork", {}).get("150x150", ""),
                "stream_url": f"{AUDIUS_API_BASE}/tracks/{t['id']}/stream"
            }
            for t in data
        ]
    except Exception as e:
        print(f"❌ Audius search failed: {e}")
        return []

# ------------------------------------------------------------
#  🔍 Get Audius Track Details (title, artist, artwork)
# ------------------------------------------------------------
async def get_audius_track_details(track_id: str):
    url = f"{AUDIUS_API_BASE}/tracks/{track_id}"
    params = {"app_name": APP_NAME}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()

            data = r.json().get("data", {})
            if not data:
                return {
                    "trackId": track_id,
                    "title": None,
                    "artistName": None,
                    "thumbnail": None,
                }

            return {
                "trackId": data["id"],
                "title": data.get("title"),
                "artistName": data["user"].get("name"),
                "thumbnail": data.get("artwork", {}).get("150x150"),
            }

    except Exception as e:
        print(f"❌ Failed to fetch track details for {track_id}: {e}")
        return {
            "trackId": track_id,
            "title": None,
            "artistName": None,
            "thumbnail": None,
        }

# ------------------------------------------------------------
#  ⬇️ FIXED AUDIO DOWNLOAD FUNCTION
#  - Now accepts folder from song_requests.py
#  - Saves to correct absolute path
#  - Retries, handles redirects
# ------------------------------------------------------------
async def download_audius_audio(track_id: str, download_folder: str = AUDIUS_DOWNLOADS_FOLDER) -> str:
    """
    Downloads an Audius track using the official streaming endpoint.
    Handles redirects and failures. Saves to user-defined folder.
    """

    output_path = os.path.join(download_folder, f"{track_id}.mp3")

    # Reuse previously downloaded file
    if os.path.exists(output_path):
        return output_path

    stream_url = f"{AUDIUS_API_BASE}/tracks/{track_id}/stream"
    params = {"app_name": APP_NAME}

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        for attempt in range(3):
            try:
                # 1) Get redirect URL
                r = await client.get(stream_url, params=params)

                if r.status_code not in (200, 302):
                    print(f"⚠️ Attempt {attempt+1}: invalid redirect response {r.status_code}")
                    await asyncio.sleep(1)
                    continue

                final_url = str(r.url)

                # 2) Fetch actual MP3 file
                mp3 = await client.get(final_url)

                if mp3.status_code != 200:
                    print(f"⚠️ Attempt {attempt+1}: MP3 fetch failed {mp3.status_code}")
                    await asyncio.sleep(1)
                    continue

                # 3) Save file
                with open(output_path, "wb") as f:
                    f.write(mp3.content)

                print(f"✅ Downloaded Audius track: {track_id}")
                return output_path

            except Exception as e:
                print(f"⚠️ Attempt {attempt+1} error: {e}")
                await asyncio.sleep(1)

    raise Exception(f"❌ Failed to download Audius track: {track_id}")
