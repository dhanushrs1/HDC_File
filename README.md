# HD Cinema File Sharing & Media Toolkit Bot

An advanced, high-performance Telegram Bot for storing files, generating permanent shareable links, and processing media with a suite of powerful admin tools. Built for efficiency and a professional user experience.

---

## ✨ Core Features

- **Permanent Links:** Generate secure, unbreakable links for your files that survive bot restarts or token changes using a web redirector (Blogger or self-hosted).
- **Batch Processing:** Create a single shareable link for a large range of files at once.
- **Smart File Expiry:** Expired files are replaced with an interactive message, allowing users to request the file again within a customizable time window.
- **Content Protection:** Option to prevent users from forwarding files sent by the bot.
- **Force Subscription:** Require users to join a specific channel before using the bot.

---

## 🚀 Advanced Admin Toolkit

- **Full Admin Panel (`/admin`):** Central hub for all management tasks.
- **Statistics:** View bot uptime and total number of active (unbanned) users.
- **Analytics:** Daily download counts and top 5 most popular files.
- **User Management:** Paginated user list, ban/unban users, view detailed user info.
- **Temp File Manager:** View and delete leftover files from the server's temporary directory.
- **Pro Video Workspace (`/process`):** All-in-one media processing tool.
  - One-time download per session for fast subsequent actions.
  - **Screenshot Generation:** Random or timestamped screenshots.
  - **Video Clipping:** Generate clips up to 60 seconds with precise start time.
  - **Image Enhancement:** Custom watermark and timestamp on screenshots.
  - **Smart Cleanup:** Temporary files deleted after sending; main video deleted when session closes.
- **Advanced Search (`/search`):** Find users by ID/username or search files by keyword.
- **Forward-to-Index System:** Build and maintain a searchable index of all files with `/start_indexing` and `/stop_indexing`.
- **Advanced Request Management:** Handle user file requests interactively—accept, decline (with reason), or reply with custom text/media.

---

## ⚙️ How It Works

1. **Storage:** Admin sends a file to the bot.
2. **Database:** Bot copies the file to a private "database" Telegram channel.
3. **Link Generation:** Bot generates a unique, permanent link (e.g., `https://your-redirector.com/?start=...`).
4. **Redirection:** User clicks the link, lands on your redirector page, which redirects to the bot with a special start code.
5. **Delivery:** Bot decodes the start code, finds the file, and sends it to the user.

---

## 🚀 Deployment Guide

### Prerequisites

- A server or VPS (e.g., AWS EC2 Free Tier)
- FFmpeg installed (required for Video Workspace)
- MongoDB database URI
- Git installed locally

### Step 1: Launch an AWS EC2 Instance

1. Sign in to AWS EC2 dashboard.
2. Click **Launch instance**.
3. Name your server (e.g., `Telegram-Bot-Server`).
4. Select **Ubuntu** (latest Free Tier eligible).
5. Choose **t2.micro** instance type.
6. Create a new key pair (`.pem` format) and download it.
7. Enable public IP and SSH access.
8. Click **Launch instance**.

### Step 2: Connect to Your EC2 Instance

```sh
ssh -i "your-key-file.pem" ubuntu@your_public_ip_address
```

### Step 3: Prepare the Server

```sh
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git ffmpeg -y
```

### Step 4: Deploy the Bot Code

```sh
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
nano .env
# Paste your bot variables and save
```

### Step 5: Run the Bot Persistently

```sh
sudo apt install screen -y
screen -S bot
python3 main.py
# Detach: Ctrl+A, then D
# Re-attach: screen -r bot
```

Your bot is now live and running on your AWS server!

---

## 📋 Command Reference

### Admin Commands

- `/start` — Start the bot and see the main menu.
- `/admin` — Access the admin control panel.
- `/process` — Start Video Workspace session.
- `/search user <id>` — Get user details.
- `/search file <keyword>` — Search for a file.
- `/genlink` & `/batch` — Manually generate links.
- `/start_indexing` & `/stop_indexing` — Manage file search index.
- `/stats` — Quick overview of bot status.
- `/broadcast` — Send a message to all users.

### User Commands

- `/start` — Start the bot.
- `/request <description>` — Request a file from admins.

---

## Credits

- **Pyrogram Library:** Dan
- **Original Base:** CodeXBotz
- **Features & Enhancements:** Maintained and developed by HD Cinema & FilmyStop

---

⭐ **Star this repo if you find it useful!**
