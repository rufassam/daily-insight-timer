#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Dec 20 13:39:15 2025

@author: rufassamjebakumar
"""

import os
import random
import smtplib
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import boto3

# =========================
# 🔐 CONFIG — EDIT THESE
# =========================

# Email
EMAIL_SENDER = "rufassam@gmail.com"
EMAIL_PASSWORD = "YOUR_GMAIL_APP_PASSWORD"
EMAIL_RECEIVER = "rufassam@gmail.com"

# Cloudflare R2
R2_ACCOUNT_ID = "6f497117b8dcc2118de21a1443d527cd"
R2_ACCESS_KEY = "YOUR_R2_ACCESS_KEY"
R2_SECRET_KEY = "YOUR_R2_SECRET_KEY"
R2_BUCKET = "ig-reels"

# Public R2 base URL (from Cloudflare dashboard)
PUBLIC_R2_BASE_URL = "https://pub-03f0b7ece4e434f8a4e7c40b7bf2c7b.r2.dev"

# Media folders (inside repo)
AUDIO_DIR = "audio"
IMAGE_DIR = "images"
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# ☁️ R2 CLIENT
# =========================

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name="auto",
)

# =========================
# 🎬 CREATE REEL
# =========================

def create_reel():
    audio = random.choice(os.listdir(AUDIO_DIR))
    image = random.choice(os.listdir(IMAGE_DIR))

    audio_path = os.path.join(AUDIO_DIR, audio)
    image_path = os.path.join(IMAGE_DIR, image)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_file = f"reel_{today}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_file)

    print("🎬 Creating reel...")

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    subprocess.run(cmd, check=True)
    return output_path

# =========================
# ☁️ UPLOAD TO R2
# =========================

def upload_to_r2(file_path):
    object_name = os.path.basename(file_path)

    print(f"☁️ Uploading {object_name} to R2...")

    s3.upload_file(
        file_path,
        R2_BUCKET,
        object_name,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    public_url = f"{PUBLIC_R2_BASE_URL}/{object_name}"
    return public_url

# =========================
# 📧 SEND EMAIL
# =========================

def send_email(video_url):
    subject = "🎧 Daily Insight Timer Reel"
    body = f"""
Your daily reel is ready 🎬

👉 Download / Watch:
{video_url}

Have a beautiful day 🌿
"""

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

    print("📧 Email sent")

# =========================
# 🚀 MAIN
# =========================

def main():
    video_path = create_reel()
    video_url = upload_to_r2(video_path)
    send_email(video_url)

if __name__ == "__main__":
    main()

