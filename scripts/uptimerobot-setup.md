# UptimeRobot Keep-Alive Setup

## Why
Render free tier spins down after 15 minutes of idle. UptimeRobot pings every 5 minutes to keep it warm.

## Quick Setup (Dashboard)
1. Go to https://uptimerobot.com and log in (xiaobingwo15@gmail.com)
2. Click **"+ Add New Monitor"**
3. Configure:
   - **Monitor Type:** HTTP(s)
   - **Friendly Name:** `Render Keep-Alive`
   - **URL:** `https://web-rag-163b.onrender.com/api/health`
   - **Monitoring Interval:** 5 minutes
4. Click **"Create Monitor"**

## API Key
```
u3540713-e9064ed06e633b97c88eea1b
```

## Verify
After creating, run:
```bash
curl -s -X POST "https://api.uptimerobot.com/v2/getMonitors" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"u3540713-e9064ed06e633b97c88eea1b"}'
```
Should return your monitor with `status: "2"` (up).

## When to Disable
- When upgrading to Render paid tier ($7/mo)
- When you have paying tenants and need guaranteed uptime
