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
from boto3.s3.transfer import TransferConfig
from openai import OpenAI

# =========================
# CONFIG — ENV VARS
# =========================

# Email
EMAIL_SENDER = os.environ["EMAIL_SENDER"].strip()
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"].strip()
EMAIL_RECEIVER = os.environ["EMAIL_RECEIVER"].strip()

# Cloudflare R2
R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"].strip()
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"].strip()
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"].strip()

R2_BUCKET = "ig-reels"

# R2 endpoint (REQUIRED)
R2_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Public Worker URL (WORKING)
R2_PUBLIC_BASE = f"https://pub-{R2_ACCOUNT_ID}.r2.dev/{R2_BUCKET}"

# Media folders
IMAGES_DIR = "images"
AUDIO_DIR = "audio"
OUTPUT_DIR = "output"

TODAY = datetime.date.today().isoformat()

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



def generate_ai_caption():
    print("🧠 Generating AI caption...")

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"].strip()
    )

    prompt = (
        "Write a calm, soothing Instagram caption for a meditation or relaxation video. "
        "Keep it short, peaceful, and inspiring. Add 2–3 relevant hashtags."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a mindfulness and meditation content creator."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=80,
    )

    caption = response.choices[0].message.content.strip()
    print("✅ Caption generated")

    return caption


def create_reel():
    print("🎬 Creating reel...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    image = get_random_file(IMAGES_DIR, (".jpg", ".jpeg", ".png"))
    audio = get_random_file(AUDIO_DIR, (".mp3", ".wav", ".m4a"))

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

    return output_path


def upload_to_r2(file_path):
    print("☁️ Uploading to R2...")

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        config=boto3.session.Config(signature_version="s3v4"),
    )

    object_key = f"reel_{TODAY}.mp4"

    config = TransferConfig(
        multipart_threshold=1024 * 1024 * 1024,
        multipart_chunksize=1024 * 1024 * 1024,
        use_threads=False,
    )

    s3.upload_file(
        file_path,
        R2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": "video/mp4"},
        Config=config,
    )

    public_url = f"https://pub-{R2_ACCOUNT_ID}.r2.dev/{R2_BUCKET}/{object_key}"

    print("✅ Uploaded:", public_url)
    return public_url


def send_email(video_url, caption):
    print("📧 Sending email...")

    msg = EmailMessage()
    msg["Subject"] = "🎥 Daily Insight Timer Reel"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    msg.set_content(
        f"""Your daily reel is ready 🎉

🎬 Video:
{video_url}

📝 AI Caption:
{caption}

Have a peaceful day 🙏
"""
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

    print("✅ Email sent!")

def cleanup():
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))
        print("🧹 Cleanup done")

def main():
    video_path = create_reel()
    public_url = upload_to_r2(video_path)

    try:
        caption = generate_ai_caption()
    except Exception as e:
        print("⚠️ Caption generation failed:", e)
        caption = "Take a deep breath and allow this moment of calm to settle in. 🌿"

    send_email(public_url, caption)
    cleanup()



if __name__ == "__main__":
    main()
