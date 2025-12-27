#!/usr/bin/env python3

import os
import json
import random
import subprocess
import datetime
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import boto3
from boto3.s3.transfer import TransferConfig


# =========================
# SAFE ENV LOADER
# =========================
def env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"❌ Missing environment variable: {name}")
    return value.strip()


# =========================
# CONFIG
# =========================

EMAIL_SENDER   = env("EMAIL_SENDER")
EMAIL_PASSWORD = env("EMAIL_PASSWORD")
EMAIL_RECEIVER = env("EMAIL_RECEIVER")

R2_ACCOUNT_ID  = env("R2_ACCOUNT_ID")
R2_ACCESS_KEY  = env("R2_ACCESS_KEY")
R2_SECRET_KEY  = env("R2_SECRET_KEY")

R2_BUCKET   = "ig-reels"
R2_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

IMAGES_DIR = "images/sleep"
AUDIO_DIR  = "audio/sleep"
OUTPUT_DIR = "output"

TODAY = datetime.date.today().isoformat()

LOW_STOCK_THRESHOLD = 3
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".history.json"
)

RESET_PROGRESS = os.getenv("RESET_PROGRESS", "").lower() == "true"


# =========================
# HISTORY
# =========================

def load_history():
    try:
        if not os.path.exists(HISTORY_FILE):
            return {"index": 0, "shuffle_seed": None}
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"index": 0, "shuffle_seed": None}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def reset_progress():
    print("🔄 Resetting progress…")
    with open(HISTORY_FILE, "w") as f:
        json.dump({"index": 0, "shuffle_seed": None}, f, indent=2)
    print("✅ Progress reset to Day 1")


# =========================
# CAPTION THEMES + TAGS
# =========================

CAPTION_THEMES = ["sleep", "healing", "focus"]

HASHTAGS = {
    "sleep": """
#sleepmusic #deeprest #calmnight #relaxingmusic #insomniarelief
""",
    "healing": """
#healingjourney #innerpeace #calmingvibes #mentalwellness #selfhealing
""",
    "focus": """
#focusmusic #studyvibes #concentration #productivityflow #mindfulworking
"""
}


def pick_theme():
    return random.choice(CAPTION_THEMES)


def get_hashtags(theme):
    return HASHTAGS.get(theme, "").strip()


# =========================
# AI CAPTION
# =========================
def generate_ai_caption(day):
    print("🧠 Generating AI caption...")

    theme = pick_theme()
    tag_block = get_hashtags(theme)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=env("OPENAI_API_KEY"))

        prompt = f"""
Write an Instagram caption for meditation music.

STYLE RULES:
• Theme: {theme}
• Format EXACTLY like this:

Day {day}/365 — "Short poetic title"

Line 1 (soft emotion)
Line 2 (calm reassurance)

Final supportive sentence.

Blank line, then these hashtags:

{tag_block}

Soft tone. Minimal words.
Do NOT exceed 6 lines total.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write peaceful, minimal meditation captions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=150,
        )

        caption = response.choices[0].message.content.strip()
        caption += "\n\n— Rufas Sam"

        print("✅ Caption created")
        return caption

    except Exception as e:
        print("⚠️ AI failed, fallback used:", e)

        fallback = f"""
Day {day}/365 — "Calm & Release"

Close your eyes.
Let your body soften.

Save this for tonight 🌿

#calm #peace #relaxation

— Rufas Sam
"""
        return fallback.strip()


# =========================
# CREATE REEL
# =========================
def create_reel():
    print("🎬 Creating reel...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    images = sorted([
        os.path.join(IMAGES_DIR, f)
        for f in os.listdir(IMAGES_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])

    audios = sorted([
        os.path.join(AUDIO_DIR, f)
        for f in os.listdir(AUDIO_DIR)
        if f.lower().endswith((".mp3", ".wav", ".m4a"))
    ])

    if not images or not audios:
        raise RuntimeError("❌ Images or audio missing")

    total_pairs = min(len(images), len(audios))
    history = load_history()

    if history["shuffle_seed"] is None:
        history["shuffle_seed"] = random.randint(1, 999999)
        save_history(history)

    random.seed(history["shuffle_seed"])
    shuffled_indices = list(range(total_pairs))
    random.shuffle(shuffled_indices)

    i = history["index"]

    if i >= total_pairs:
        raise RuntimeError(
            "🚫 All reels finished.\n"
            "Add more images/audio to continue."
        )

    # Day BEFORE increment
    day_number = i + 1

    pair_index = shuffled_indices[i]
    image = images[pair_index]
    audio = audios[pair_index]

    # increment after use
    history["index"] = i + 1
    save_history(history)

    remaining = total_pairs - history["index"]
    if remaining <= LOW_STOCK_THRESHOLD:
        try:
            send_low_stock_alert(remaining)
        except Exception as e:
            print("⚠️ Low stock alert failed:", e)

    output_path = f"{OUTPUT_DIR}/reel_{TODAY}.mp4"

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
        output_path,
    ]

    subprocess.run(cmd, check=True)

    print("✅ Reel created:", output_path)

    return output_path, os.path.basename(image), os.path.basename(audio), day_number


# =========================
# UPLOAD TO R2
# =========================
def upload_to_r2(file_path):
    print("☁️ Uploading…")

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        config=boto3.session.Config(signature_version="s3v4"),
    )

    object_key = f"reel_{TODAY}.mp4"

    s3.upload_file(
        file_path,
        R2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": "video/mp4"},
        Config=TransferConfig(
            multipart_threshold=1024 * 1024 * 1024,
            use_threads=False
        )
    )

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": R2_BUCKET,
            "Key": object_key,
            "ResponseContentType": "video/mp4",
            "ResponseContentDisposition": f'attachment; filename="{object_key}"'
        },
        ExpiresIn=86400
    )

    print("✅ Link ready")
    return url


# =========================
# EMAILS
# =========================

def send_low_stock_alert(remaining):
    msg = EmailMessage()
    msg["Subject"] = "⚠️ Reels automation — content running low"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    msg.set_content(
f"""
Only {remaining} reels remain.

Upload more:

📁 {IMAGES_DIR}
📁 {AUDIO_DIR}

– Automation bot
"""
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)


def send_email(video_url, caption, image, audio):
    msg = EmailMessage()
    msg["Subject"] = "🎥 Daily Instagram Reel Ready"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    msg.set_content(
f"""
Your daily reel is ready 🎉

📥 Download:
{video_url}

📝 Caption suggestion:
{caption}

Today used:
📸 {image}
🎵 {audio}

Have a peaceful day 🙏
"""
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

    print("✅ Email sent")


# =========================
# CLEANUP
# =========================

def cleanup_local():
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))


def cleanup_old_r2_files(days_to_keep=30):
    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        config=boto3.session.Config(signature_version="s3v4"),
    )

    cutoff = datetime.date.today() - datetime.timedelta(days=days_to_keep)

    resp = s3.list_objects_v2(Bucket=R2_BUCKET)
    if "Contents" not in resp:
        return

    for obj in resp["Contents"]:
        key = obj["Key"]
        if not key.startswith("reel_"):
            continue

        try:
            d = key.replace("reel_", "").replace(".mp4", "")
            file_date = datetime.datetime.strptime(d, "%Y-%m-%d").date()
        except:
            continue

        if file_date < cutoff:
            s3.delete_object(Bucket=R2_BUCKET, Key=key)


# =========================
# MAIN
# =========================
def main():
    print("▶️ START")

    if RESET_PROGRESS:
        reset_progress()

    video, img, aud, day = create_reel()
    url = upload_to_r2(video)
    caption = generate_ai_caption(day)

    send_email(url, caption, img, aud)

    cleanup_old_r2_files()
    cleanup_local()

    print("🎉 DONE")


if __name__ == "__main__":
    main()

