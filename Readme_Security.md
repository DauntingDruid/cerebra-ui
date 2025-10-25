# Cloudflare Turnstile Integration — CerebraUI Security Setup

This document explains how to connect and configure **Cloudflare Turnstile** for human verification in the CerebraUI authentication system.  
After following these steps, users will have a **CAPTCHA** on the Sign-In page and proper **backend token verification** for secure login.

## Overview

CerebraUI uses **Cloudflare Turnstile** to verify that a human is signing in.  
The Turnstile widget appears on the Sign-In page, and the backend validates each token using your **Turnstile secret key**.

---

## Step 0: Pull the Git Changes from the specific branch

Before running the project, user should make sure to be on the correct branch that contains the latest security updates.

```bash
# Fetch all the latest branches from remote
git fetch origin

# Switch to the specific branch (replace <branch-name> with the actual branch)
git checkout <branch-name>

# Pull the latest updates from that branch
git pull origin <branch-name>
```

---

## Step 1: Create Turnstile Keys

1. Go to https://dash.cloudflare.com/ and login with your **email address** which was used to create account on **Resend** to get the API key.  
2. From the left sidebar, open **Turnstile** → click **“Add Widget”**.  
3. Fill in the form:  
   - **Widget name:** `CerebraUI Local`  
   - **Add Hostname** `localhost`  
     *(Add both `http://localhost:3000` and `http://localhost:5173` if using Vite)*  
   - **Widget Mode:** `Managed` 
4. Click **Create**.  
5. Copy your: **Site Key** and **Secret Key** from the page.

---

## Step 2: Add Keys to Your `.env` File

Open your project’s `.env` file and add the keys into the following lines:

```bash
# For local testing (Cloudflare Turnstile)
VITE_TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=
```

**Note:**Please don't push your **SITE_KEY** and **SECRET_KEY** on github or any other platform for security reason.

---

## Step 3: Step 5: Run the System Locally

Once user has added your .env file with the Cloudflare keys:

```bash
# Install dependencies
npm install
```

```bash
# Build and open the app
NODE_OPTIONS=--max-old-space-size=4096 npm run build && OPEN_WEBUI_PORT=3000 docker compose -f docker-compose.yaml -f docker-compose.override.yaml up -d --build --force-recreate
```

User should now see the Cloudflare Turnstile CAPTCHA on your Sign-In page.

---