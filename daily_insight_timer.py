#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Dec 20 13:39:15 2025

@author: rufassamjebakumar
"""

import os
import random
import subprocess
import datetime
import smtplib
from email.message import EmailMessage
import boto3

# =========================
# CONFIG — UPDATE THESE
# =========================

# Email
EMAIL_SENDER = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_RECEIVER = os.environ["EMAIL_RECEIVER"]

# Cloudflare R2
R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"]
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"]
R2_BUCKET_NAME = "ig-reels"

# Public Worker base URL (IMPORTANT)
PUBLIC_BASE_URL = "https://ig-reels-public.rufassam.workers.dev"

# Media folders (relative paths in repo)
IMAGES_DIR = "images"
AUDIO_DIR = "audio"
OUTPUT_DIR = "output"

# =========================
# HELPERS
# =========================

def get_random_file(root_dir, extensions):
    files = []
    for root, _, filenames in os.walk(root_dir):
        for f in filenames:
            if f.lower().endswith(extensions):
                files.append(os.path.join(root, f))

    if not files:
        raise RuntimeError(f"❌ No valid files found in {root_dir}")

    return random.choice(files)


def create_reel():
    print("🎬 Creating reel...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    image = get_random_file(IMAGES_DIR, (".jpg", ".jpeg", ".png"))
    audio = get_random_file(AUDIO_DIR, (".mp3", ".wav", ".m4a"))

    today = datetime.date.today().isoformat()
    output_path = f"{OUTPUT_DIR}/reel_{today}.mp4"

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

    return output_path


from boto3.s3.transfer import TransferConfig
import boto3
import os

def upload_to_r2(file_path):
    print("☁️ Uploading to R2...")

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        config=boto3.session.Config(
            signature_version="s3v4"
        ),
    )

    filename = os.path.basename(file_path)
    object_key = f"reel_{TODAY}.mp4"

    # 🚫 Disable multipart uploads (CRITICAL FIX)
    config = TransferConfig(
        multipart_threshold=1024 * 1024 * 1024,  # 1 GB
        multipart_chunksize=1024 * 1024 * 1024,
        use_threads=False,
    )

    s3.upload_file(
        file_path,
        R2_BUCKET,
        object_key,
        ExtraArgs={
            "ContentType": "video/mp4",
        },
        Config=config,
    )

    public_url = f"{R2_PUBLIC_BASE}/{object_key}"
    print(f"✅ Uploaded to R2: {public_url}")

    return public_url


def send_email(video_url):
    print("📧 Sending email...")

    sender = EMAIL_SENDER.strip()
    receiver = EMAIL_RECEIVER.strip()
    password = EMAIL_PASSWORD.strip()

    msg = EmailMessage()
    msg["Subject"] = "🎥 Daily Insight Timer Reel"
    msg["From"] = sender
    msg["To"] = receiver

    body = (
        "Your daily reel is ready 🎉\n\n"
        "Watch & download here:\n"
        f"{video_url}\n\n"
        "Have a great day 🙏"
    )

    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

    print("✅ Email sent!")


def cleanup_local_files():
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))
        print("🧹 Local cleanup done")


def main():
    video_path = create_reel()
    public_url = upload_to_r2(video_path)
    send_email(public_url)
    cleanup_local_files()


if __name__ == "__main__":
    main()
