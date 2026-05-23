# Deploying to Railway — Step by Step

This gets you a permanent public URL (e.g. `https://sky130-converter.up.railway.app`)
that anyone can access without installing anything.

---

## Prerequisites

- A [GitHub](https://github.com) account (free)
- A [Railway](https://railway.app) account — sign up with GitHub (free)

---

## Step 1 — Push to GitHub

Open a terminal in the `sky130_converter` folder and run:

```bash
git init
git add .
git commit -m "Initial commit — Sky130 to GF180MCU converter"
```

Go to [github.com/new](https://github.com/new) and create a new **public** repository
called `sky130-converter`. Do NOT initialize with README (you already have one).

Then link and push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/sky130-converter.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Deploy on Railway

1. Go to [railway.app](https://railway.app) and click **Login with GitHub**
2. Click **New Project**
3. Click **Deploy from GitHub repo**
4. Select your `sky130-converter` repository
5. Railway auto-detects Python and reads your `Procfile` — click **Deploy**

That's it. Railway will:
- Install dependencies from `requirements.txt`
- Start the app using `gunicorn` from your `Procfile`
- Give you a public URL

---

## Step 3 — Get your public URL

1. In your Railway project dashboard, click your service
2. Go to the **Settings** tab
3. Under **Networking**, click **Generate Domain**
4. You get a URL like `https://sky130-converter-production.up.railway.app`

Share this URL with anyone — they can use the tool directly in their browser, no install needed.

---

## Updates

Whenever you push a new commit to GitHub, Railway auto-redeploys:

```bash
git add .
git commit -m "your update message"
git push
```

---

## Free tier limits

Railway's free Hobby plan gives you:
- $5 of compute credits per month
- This app uses ~0.1–0.3 vCPU at idle, so it runs comfortably within free limits
- App stays live 24/7 (no sleep like Render's free tier)

---

## Troubleshooting

**App crashes on deploy:**
- Check the Railway logs tab for errors
- Make sure `requirements.txt` lists `flask` and `gunicorn`
- Make sure `Procfile` says `web: gunicorn app:app --bind 0.0.0.0:$PORT`

**Symbol not found in Xschem after conversion:**
- Verify your `PDK_ROOT` environment variable points to your GF180MCU PDK install
- The `symbols/` path resolves relative to `$PDK_ROOT/libs.tech/xschem/`
