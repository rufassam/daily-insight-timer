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

def upload_video_to_github(video_path):
    print("☁️ Uploading to GitHub Releases...")

    repo = "rufassam/daily-insight-timer"
    token = os.environ["GITHUB_TOKEN"]

    tag = f"reel-{TODAY}"
    release_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # Create release if not exists
    r = requests.get(release_url, headers=headers)
    if r.status_code == 404:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/releases",
            headers=headers,
            json={"tag_name": tag, "name": tag},
        )
    release = r.json()

    upload_url = release["upload_url"].split("{")[0]
    filename = os.path.basename(video_path)

    with open(video_path, "rb") as f:
        requests.post(
            f"{upload_url}?name={filename}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
            },
            data=f,
        )

    public_url = f"https://github.com/{repo}/releases/download/{tag}/{filename}"
    print("✅ Public video URL:", public_url)
    return public_url

def upload_to_instagram(video_url, caption):
    print("📤 Uploading to Instagram...")

    r = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=60,
    )

    if r.status_code != 200:
        print(r.text)
        r.raise_for_status()

    creation_id = r.json()["id"]

    r = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=30,
    )

    r.raise_for_status()
    print("✅ Reel published successfully!")


# =========================
# MAIN
# =========================

def main():
    video = create_reel()
    caption = generate_caption()

    public_video_url = upload_video_to_github(video)
    upload_to_instagram(public_video_url, caption)
