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

IMAGES_DIR = "images/sleep"
AUDIO_DIR = "audio/sleep"
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

def generate_ai_caption():
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"].strip()
        )

        prompt = (
            "Write a calm, soothing Instagram caption for a meditation or sleep music reel. "
            "Keep it short (2–3 lines), peaceful, and inspiring. "
            "Add 2–3 gentle hashtags."
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
        print("🧠 AI caption generated")
        return caption

    except Exception as e:
        print("⚠️ AI caption failed, using fallback:", e)
        return "Take a deep breath and let this moment of calm flow through you. 🌿✨ #Relax #Calm"


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
        config=boto3.session.Config(signature_version="s3v4"),
    )

    object_key = f"reel_{TODAY}.mp4"

    # Upload (private)
    s3.upload_file(
        file_path,
        R2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    # ✅ Generate pre-signed download URL (24 hours)
    signed_url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": R2_BUCKET,
            "Key": object_key,
            "ResponseContentType": "video/mp4",
            "ResponseContentDisposition": f'attachment; filename="{object_key}"',
        },
        ExpiresIn=60 * 60 * 24,  # 24 hours
    )

    print("✅ Pre-signed download link generated")
    return signed_url

# =========================
# SEND EMAIL
# =========================

def send_email(video_url, caption):
    print("📧 Sending email...")

    msg = EmailMessage()
    msg["Subject"] = "🎥 Daily Instagram Reel Ready"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    msg.set_content(
        f"""Your daily reel is ready 🎉

📥 Download link:
{video_url}

📝 Suggested caption:
{caption}

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

    caption = generate_ai_caption()

    send_email(link, caption)
    cleanup()


