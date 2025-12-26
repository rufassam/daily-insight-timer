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
HISTORY_FILE = ".history.json"

# Font for watermark
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# =========================
# HISTORY HELPERS
# =========================
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"index": 0, "shuffle_seed": None}

    with open(HISTORY_FILE, "r") as f:
        return json.load(f)


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# =========================
# AI CAPTION
# =========================
def generate_ai_caption():
    print("🧠 Generating AI caption...")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=env("OPENAI_API_KEY"))

        prompt = (
            "Write a calm meditation/sleep Instagram caption. "
            "2–3 lines. Gentle tone. Add 2–3 soft hashtags."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You write peaceful meditation captions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=80,
        )

        caption = response.choices[0].message.content.strip()
        print("✅ Caption created")
        return caption

    except Exception as e:
        print("⚠️ AI failed, fallback:", e)
        return "Take a deep breath… let your body unwind. 🌿✨ #Calm #Stillness"


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

    # shuffle once
    if history["shuffle_seed"] is None:
        history["shuffle_seed"] = random.randint(1, 999999)
        save_history(history)

    random.seed(history["shuffle_seed"])
    shuffled_indices = list(range(total_pairs))
    random.shuffle(shuffled_indices)

    i = history["index"]

    if i >= total_pairs:
        raise RuntimeError("🚫 No unused files left — upload more content")

    pair_index = shuffled_indices[i]

    image = images[pair_index]
    audio = audios[pair_index]

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

        "-vf",
        (
            "scale=1080:1920,format=yuv420p,"
            "drawtext="
            f"fontfile='{FONT_PATH}':"
            "text='Rufas Sam':"
            "fontcolor=white@0.7:"
            "fontsize=48:"
            "shadowcolor=black@0.6:"
            "shadowx=2:shadowy=2:"
            "x=(w-text_w)/2:"
            "y=h-(text_h*3)"
        ),

        "-c:v", "libx264",
        "-preset", "veryfast",

        "-c:a", "aac",
        "-b:a", "192k",

        "-shortest",

        output_path,
    ]

    subprocess.run(cmd, check=True)

    print("✅ Reel created:", output_path)
    return output_path, os.path.basename(image), os.path.basename(audio)


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
            "ResponseContentDisposition": f'attachment; filename=\"{object_key}\"'
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

Upload more files here:

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

    video, img, aud = create_reel()
    url = upload_to_r2(video)
    caption = generate_ai_caption()

    send_email(url, caption, img, aud)

    cleanup_old_r2_files()
    cleanup_local()

    print("🎉 DONE")


if __name__ == "__main__":
    main()
