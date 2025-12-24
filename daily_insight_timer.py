import os
import random
import subprocess
import datetime
import smtplib
from email.message import EmailMessage
import boto3
from boto3.s3.transfer import TransferConfig

# =========================
# ENV CONFIG
# =========================

EMAIL_SENDER = os.environ["EMAIL_SENDER"].strip()
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"].strip()
EMAIL_RECEIVER = os.environ["EMAIL_RECEIVER"].strip()

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"].strip()
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"].strip()
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"].strip()

R2_BUCKET = "ig-reels"
R2_ENDPOINT = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

IMAGES_DIR = "images"
AUDIO_DIR = "audio"
OUTPUT_DIR = "output"

TODAY = datetime.date.today().isoformat()

# =========================
# HELPERS
# =========================

def get_random_file(folder, extensions):
    files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(extensions)
    ]
    if not files:
        raise RuntimeError(f"No valid files found in {folder}")
    return random.choice(files)

# =========================
# CREATE REEL
# =========================

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
        output_path
    ]

    subprocess.run(cmd, check=True)
    print("✅ Reel created:", output_path)
    return output_path

# =========================
# UPLOAD TO R2
# =========================

def upload_to_r2(file_path):
    print("☁️ Uploading to R2...")

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )

    object_key = f"reel_{TODAY}.mp4"

    config = TransferConfig(
        multipart_threshold=1024 * 1024 * 1024,
        use_threads=False
    )

    s3.upload_file(
        file_path,
        R2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": "video/mp4"},
        Config=config
    )

    download_url = f"{R2_ENDPOINT}/{R2_BUCKET}/{object_key}"
    print("✅ Uploaded:", download_url)
    return download_url

# =========================
# SEND EMAIL
# =========================

def send_email(video_url):
    print("📧 Sending email...")

    msg = EmailMessage()
    msg["Subject"] = "🎥 Daily Instagram Reel Ready"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    msg.set_content(f"""
Your daily reel is ready 🎉

Download link:
{video_url}

Suggested caption:
Take a deep breath and let this moment flow. 🌿✨

Have a peaceful day 🙏
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

    print("✅ Email sent")

# =========================
# CLEANUP
# =========================

def cleanup():
    if os.path.exists(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))
        print("🧹 Cleanup done")

# =========================
# MAIN
# =========================

def main():
    video = create_reel()
    link = upload_to_r2(video)
    send_email(link)
    cleanup()

if __name__ == "__main__":
    main()

