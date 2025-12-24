import os
import random
import subprocess
import datetime
import requests
from openai import OpenAI

# =========================
# CONFIG
# =========================

IMAGES_DIR = "images"
AUDIO_DIR = "audio"
OUTPUT_DIR = "output"

TODAY = datetime.date.today().isoformat()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

# =========================
# HELPERS
# =========================

def get_random_file(root, extensions):
    files = []
    for r, _, fns in os.walk(root):
        for f in fns:
            if f.lower().endswith(extensions):
                files.append(os.path.join(r, f))
    if not files:
        raise RuntimeError(f"No files in {root}")
    return random.choice(files)

# =========================
# CREATE REEL
# =========================

def create_reel():
    print("🎬 Creating reel...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    image = get_random_file(IMAGES_DIR, (".jpg", ".png", ".jpeg"))
    audio = get_random_file(AUDIO_DIR, (".mp3", ".wav", ".m4a"))

    output = f"{OUTPUT_DIR}/reel_{TODAY}.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", image,
        "-i", audio,
        "-vf", "scale=1080:1920,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output,
    ]

    subprocess.run(cmd, check=True)
    print("✅ Reel created:", output)
    return output

# =========================
# AI CAPTION
# =========================

def generate_caption():
    print("🧠 Generating AI caption...")
    client = OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You create calm Instagram captions for meditation reels."},
            {"role": "user", "content": "Write a peaceful, short Instagram Reel caption with 2–3 hashtags."}
        ],
        max_tokens=80,
        temperature=0.7,
    )

    caption = response.choices[0].message.content.strip()
    print("✅ Caption:", caption)
    return caption

# =========================
# UPLOAD TO INSTAGRAM
# =========================

def upload_to_instagram(video_path, caption):
    print("📤 Uploading to Instagram...")

    # Step 1: Create media container
    with open(video_path, "rb") as f:
        r = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
            data={
                "media_type": "REELS",
                "caption": caption,
                "access_token": IG_ACCESS_TOKEN,
            },
            files={"video_file": f},
            timeout=60,
        )

    r.raise_for_status()
    creation_id = r.json()["id"]

    # Step 2: Publish
    r = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=30,
    )

    r.raise_for_status()
    print("✅ Reel published on Instagram!")

# =========================
# MAIN
# =========================

def main():
    video = create_reel()
    caption = generate_caption()
    upload_to_instagram(video, caption)

if __name__ == "__main__":
    main()
