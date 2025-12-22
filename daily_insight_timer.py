#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Dec 20 13:39:15 2025

@author: rufassamjebakumar
"""

import os
import random
import subprocess
import boto3
import smtplib
import hashlib
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

# ============================================================
# 🔐 SECRETS (FROM GITHUB ACTIONS)
# ============================================================

EMAIL_SENDER = os.environ["EMAIL_SENDER"].strip()
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"].strip()
EMAIL_RECEIVER = os.environ["EMAIL_RECEIVER"].strip()

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"].strip()
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"].strip()
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"].strip()

R2_BUCKET = "ig-reels"

# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_BASE_URL = f"https://{R2_BUCKET}.{R2_ACCOUNT_ID}.r2.dev"

IMAGE_DIR = os.path.join(BASE_DIR, "images", "sleep")
AUDIO_DIR = os.path.join(BASE_DIR, "audio", "sleep")

TODAY = str(date.today())
OUTPUT_VIDEO = os.path.join(BASE_DIR, f"reel_{TODAY}.mp4")

# ============================================================
# SETTINGS
# ============================================================

MAX_DURATION = 30            # seconds
MAX_REELS_TO_KEEP = 7        # auto-clean R2

CAPTIONS = [
    "🧘 Calm music for deep relaxation\nListen free on Insight Timer",
    "🌙 Music for sleep & peace\nAvailable on Insight Timer",
    "🎧 Gentle focus music\nFree on Insight Timer",
    "✨ Mindful soundscapes\nFree sessions on Insight Timer",
]

# ============================================================
# CLOUDFARE R2 CLIENT
# ============================================================

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name="auto",
)

# ============================================================
# HELPERS
# ============================================================

def caption_for_today():
    h = int(hashlib.md5(TODAY.encode()).hexdigest(), 16)
    return CAPTIONS[h % len(CAPTIONS)]


def pick_random_image():
    images = [
        f for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    if not images:
        raise RuntimeError("No images found in images/sleep")
    return os.path.join(IMAGE_DIR, random.choice(images))


def pick_random_audio():
    audio_files = [
        f for f in os.listdir(AUDIO_DIR)
        if f.lower().endswith((".mp3", ".wav", ".m4a"))
    ]
    if not audio_files:
        raise RuntimeError("No audio files found in audio/sleep")
    return os.path.join(AUDIO_DIR, random.choice(audio_files))

# ============================================================
# CREATE REEL
# ============================================================

def create_reel():
    print("🎬 Creating reel...")

    image = pick_random_image()
    audio = pick_random_audio()

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image,
        "-i", audio,
        "-t", str(MAX_DURATION),
        "-vf", "scale=1080:1920,format=yuv420p",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        OUTPUT_VIDEO
    ]

    subprocess.run(cmd, check=True)
    print("✅ Video created:", OUTPUT_VIDEO)

# ============================================================
# UPLOAD TO R2 + PRESIGNED URL
# ============================================================

import os

def upload_to_r2(local_path):
    print("☁️ Uploading to Cloudflare R2...")

    filename = os.path.basename(local_path)  # 🔑 THIS IS THE FIX

    s3.upload_file(
        local_path,          # local file on GitHub runner
        R2_BUCKET,
        filename,            # R2 object key (clean!)
        ExtraArgs={
            "ContentType": "video/mp4",
        },
    )

    public_url = f"{PUBLIC_BASE_URL}/{filename}"
    print("🔗 Public URL:", public_url)

    return public_url


# ============================================================
# CLEAN OLD REELS
# ============================================================

def cleanup_old_reels():
    print("🧹 Cleaning old reels...")

    resp = s3.list_objects_v2(Bucket=R2_BUCKET)
    if "Contents" not in resp:
        return

    objects = sorted(
        resp["Contents"],
        key=lambda x: x["LastModified"],
        reverse=True,
    )

    for obj in objects[MAX_REELS_TO_KEEP:]:
        print("Deleting:", obj["Key"])
        s3.delete_object(Bucket=R2_BUCKET, Key=obj["Key"])

# ============================================================
# SEND EMAIL
# ============================================================

def send_email(video_url, caption):
    print("📧 Sending email...")

    body = f"""
Your Instagram Reel is ready ✅

🎥 Video:
{video_url}

📝 Caption:
{caption}

Steps:
1. Download video
2. Upload as Reel
3. Paste caption
4. Publish 🚀

— Daily Insight Timer Automation
"""

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = "🎬 Daily Insight Timer Reel"
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

    print("✅ Email sent")

# ============================================================
# MAIN
# ============================================================

def main():
    create_reel()
    video_url = upload_to_r2(OUTPUT_VIDEO)
    caption = random.choice(CAPTIONS)
    send_email(video_url, caption)



if __name__ == "__main__":
    main()
