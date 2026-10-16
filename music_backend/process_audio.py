import os
import math
import time
import shutil
import subprocess
from pydub import AudioSegment
from gtts import gTTS
from datetime import datetime
from pydub.effects import normalize

# -----------------------------
# CONSTANTS
# -----------------------------
# FINAL USER-REQUESTED FOLDER PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Downloaded YouTube source tracks (only from configured authorized channels)
YOUTUBE_DOWNLOADS_FOLDER = os.getenv(
    "YOUTUBE_DOWNLOADS_DIR", os.path.join(BASE_DIR, "youtube_downloads")
)

# Mixed audio output, also exposed as static /audio
MIXED_AUDIO_FOLDER = os.getenv(
    "MIXED_AUDIO_DIR", os.path.join(BASE_DIR, "uploads", "mixed_audio")
)

os.makedirs(YOUTUBE_DOWNLOADS_FOLDER, exist_ok=True)
os.makedirs(MIXED_AUDIO_FOLDER, exist_ok=True)

os.environ["PYDUB_FFMPEG_LOGLEVEL"] = "quiet"

SEG_MS = 10000
BG_ATTENUATE_DB = -12
TODAY = datetime.now().strftime("%Y-%m-%d")


# ------------------------------------------------------------
#  🔊 AUDIO PROCESSING FUNCTIONS (UNCHANGED)
# ------------------------------------------------------------
def _run_ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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
    _run_ffmpeg(
        "-i", audio_path,
        "-af", f"asetrate=44100*{ratio},aresample=44100",
        output_path,
    )
    return output_path


def change_tempo(audio_path, output_path, speed=1.2):
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Tempo speed must be between 0.5 and 2.0")
    _run_ffmpeg("-i", audio_path, "-af", f"atempo={speed}", output_path)
    return output_path


def mix_audio(audio1_path, audio2_path, output_path, bg_db: int = BG_ATTENUATE_DB):
    track1 = AudioSegment.from_file(audio1_path)
    track2 = AudioSegment.from_file(audio2_path)
    min_len = min(len(track1), len(track2))
    mixed = track1[:min_len].overlay(track2[:min_len].apply_gain(bg_db))
    mixed.export(output_path, format="mp3", bitrate="192k")
    return output_path


def copy_audio_as_mp3(audio_path, output_path):
    if os.path.splitext(audio_path)[1].lower() == ".mp3":
        shutil.copy(audio_path, output_path)
    else:
        AudioSegment.from_file(audio_path).export(
            output_path, format="mp3", bitrate="192k"
        )
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

    main = normalize(main)
    bg = normalize(bg).apply_gain(bg_db)

    loops = math.ceil(len(main) / len(bg))
    bg_full = (bg * loops)[:len(main)]

    combined = main.overlay(bg_full)
    combined.export(out_path, format="mp3", bitrate="192k")
    return out_path


def strip_vocals(audio_path: str, output_path: str) -> str:
    """Rough center-channel vocal cancellation (karaoke filter)."""
    _run_ffmpeg(
        "-i", audio_path,
        "-af", "pan=stereo|c0=c0-c1|c1=c1-c0",
        output_path,
    )
    return output_path


def beat_background(
    main_path: str,
    beat_path: str,
    out_path: str,
    bg_db: int = BG_ATTENUATE_DB,
) -> str:
    """Keep `main_path` up front and loop an attenuated, vocal-stripped beat behind it."""
    beat_only = os.path.splitext(out_path)[0] + "_beat_only.mp3"
    try:
        strip_vocals(beat_path, beat_only)
        return overlay_tracks(main_path, beat_only, out_path, bg_db)
    finally:
        if os.path.isfile(beat_only):
            os.remove(beat_only)


def overlay_beat(main_path: str, beat_path: str, out_path: str, bg_db: int = BG_ATTENUATE_DB):
    return overlay_tracks(main_path, beat_path, out_path, bg_db)
