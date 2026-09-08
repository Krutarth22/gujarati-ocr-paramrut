# Gujarati OCR Web App - Walkthrough

## Overview
You have successfully converted your local OCR script into a full-stack web application.
- **Frontend**: React (Vite) with Drag-and-Drop.
- **Backend**: FastAPI.
- **Processing**: Celery + Redis (for background tasks).

## How to Run

### Option 1: The Easy Way (Local Script)
Use the provided script to start everything (Redis, Backend, Worker, Frontend) in one go.

```bash
./start_app.sh
```
*   **Frontend**: [http://localhost:5173](http://localhost:5173)
*   **Backend**: [http://localhost:8000](http://localhost:8000)

### Option 2: Docker (Recommended for Stability)
If you have Docker installed:

```bash
docker-compose up --build
```

## How to Share (Zero Cost)
To share this with your select group without paying for a server, use **Cloudflare Tunnel**.

1.  **Install Cloudflared**:
    ```bash
    brew install cloudflare/cloudflared
    ```
2.  **Start the App**:
    Make sure your app is running (using `./start_app.sh`).
3.  **Start the Tunnel**:
    Run this command to expose your local frontend (port 5173) to the internet:
    ```bash
    cloudflared tunnel --url http://localhost:5173
    ```
4.  **Share the Link**:
    Cloudflare will generate a random URL (e.g., `https://random-name.trycloudflare.com`). Share this link with your group.

> [!NOTE]
> For a permanent URL, you can set up a named tunnel if you have a domain name on Cloudflare.

## Cloud Deployment (24/7 Online)
Since you don't want to keep your laptop on, here are the best low-cost/free options for hosting this heavy OCR app:

### Option 1: Oracle Cloud Free Tier (Best "Free" Option)
Oracle offers a very generous "Always Free" tier.
1.  Sign up for Oracle Cloud Free Tier.
2.  Create a VM instance.
3.  **Image & Shape**: Select **Ampere** (VM.Standard.A1.Flex).
4.  **Configuration**: Drag the sliders to the maximum free limit:
    -   **OCPUs**: 4
    -   **Memory**: 24 GB
5.  **SSH Key**: Download the private key (e.g., `ssh-key-2024-11-30.key`) when prompted.
6.  **Connect**:
    Open your terminal and run:
    ```bash
    # 1. Set permissions (required)
    chmod 400 /path/to/your/private.key

    # 2. Connect (username is usually 'ubuntu' or 'opc')
    ssh -i /path/to/your/private.key ubuntu@<YOUR_INSTANCE_IP>
    ```
    ```
7.  Once connected, clone your code and run `docker-compose up -d`.

> [!WARNING]
> **"Out of Capacity" Error**: This is common for the free Ampere instances.
> *   **Try a different Availability Domain** (AD-1, AD-2, AD-3) in the "Placement" section.
> *   **Retry later**: Capacity fluctuates.
>
> **Alternative: AMD Shape (VM.Standard.E2.1.Micro)**
> *   **Pros**: Always available.
> *   **Cons**: VERY weak (1 CPU, 1GB RAM).
> *   **Critical Change**: If you use this, you **MUST** edit `main.py` and change `batch_size=5` to `batch_size=1`. If you don't, the server will crash immediately due to lack of RAM.

### Option 2: DigitalOcean / Hetzner (~$5-7/mo)
If you want something easier to set up:
1.  Create a "Droplet" (DigitalOcean) or "Cloud Server" (Hetzner).
2.  Choose Ubuntu.
3.  Install Docker.
4.  Copy your code and run `docker-compose up -d`.

### Option 3: Google Cloud Run (Pay-per-use)
Runs only when used.
1.  Install Google Cloud CLI.
2.  Deploy the container.
*Note: You might need to increase the timeout settings as OCR takes time.*

### ❌ Why NOT Vercel / Netlify?
You might be tempted to use Vercel, but it **will not work** for the backend because:
1.  **Timeouts**: Vercel functions time out after 10-60 seconds. Your OCR takes minutes/hours.
2.  **Dependencies**: You cannot easily install `tesseract-ocr` (system binary) on Vercel.
3.  **Storage**: Vercel has no persistent storage for your PDF files.

*You CAN host the Frontend on Vercel, but you still need a VPS (like Oracle) for the Backend.*

## 🚀 Step-by-Step Deployment Guide

### 1. Transfer Code to Server
Run this **on your computer** (not the server) to copy your code:
```bash
# Replace with your actual key path and server IP
scp -i /path/to/key.key -r . ubuntu@<SERVER_IP>:~/gujarati_ocr
```

### 2. Connect to Server
```bash
ssh -i /path/to/key.key ubuntu@<SERVER_IP>
```

### 3. Install Docker (Run on Server)
*Assuming you chose Ubuntu:*
```bash
# Update and install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
# Add your user to the docker group
sudo usermod -aG docker $USER
# Log out and back in for permissions to take effect
exit
```

### 4. Start the App
Reconnect (`ssh ...`) and run:
```bash
cd gujarati_ocr

# IMPORTANT: If using AMD instance, edit docker-compose.yml first!
# nano docker-compose.yml -> Change OCR_BATCH_SIZE=1

docker-compose up -d --build
```
Your app will be live at `http://<SERVER_IP>:5173`!

## 🆘 Troubleshooting

### SSH "Permission Denied" (publickey)
If you cannot connect to your server, it means your **Private Key** does not match the **Public Key** on the server.
1.  **Wrong Username?**: Try `ubuntu` (for Ubuntu images) or `opc` (for Oracle Linux images).
2.  **Wrong Key?**: If you created the instance but didn't save the key *at that exact moment*, you cannot recover it.
    *   **Crucial**: In the "Add SSH keys" section, select **"Generate a key pair"** and click **"Save Private Key"** immediately. Use *that* file.

## 🌐 Permanent Domain Setup (Optional)

The quick tunnel URL (`trycloudflare.com`) changes every time you restart it. To get a **permanent URL** (like `ocr.yourdomain.com`), follow these steps:

### 1. Prerequisites
*   You must **own a domain name** (buy one from Namecheap, Porkbun, etc. for ~$10/yr).
*   Create a free **Cloudflare** account and add your domain to it (change nameservers).

### 2. Create the Tunnel
1.  Go to the [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/).
2.  Navigate to **Networks** -> **Tunnels** -> **Create a tunnel**.
3.  Choose **Cloudflared** as the connector.
4.  Name it (e.g., "gujarati-ocr").
5.  **Install the connector**: It will give you a command starting with `sudo cloudflared service install...`. Run this on your Oracle server.
6.  **Public Hostname**: In the tunnel settings, verify the connection, then go to the "Public Hostname" tab.
    *   **Subdomain**: `ocr` (or whatever you want)
    *   **Domain**: `yourdomain.com`
    *   **Service**: `http://localhost:5173`
7.  Save the tunnel.

Now your app will be permanently accessible at `https://ocr.yourdomain.com`!
