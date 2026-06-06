# Frontend Dev Server

Start the Vite dev server for the React frontend.

## When to Use
- User asks to "run the frontend" or "start the dev server"
- User says "npm run dev" or "vite"
- Starting a frontend development session

## Steps

### 1. Clear NODE_ENV (Critical)
VS Code injects `NODE_ENV=production` at the process level, which causes npm to skip devDependencies (vite, typescript, tailwind, etc. are never installed).

**Always run this first:**
```powershell
$env:NODE_ENV = ""
```

### 2. Install Dependencies (if needed)
Check if `node_modules/.bin/vite` exists. If not:
```powershell
cd D:\RAG\Web-RAG\frontend
npm install
```

### 3. Start Dev Server
```powershell
cd D:\RAG\Web-RAG\frontend
npm run dev
```

## Troubleshooting

### "vite is not recognized"
- **Cause:** `NODE_ENV=production` is set, npm skipped devDependencies
- **Fix:** `$env:NODE_ENV = ""; npm install; npm run dev`

### Port already in use
- Default Vite port is 5173
- Check: `netstat -ano | findstr :5173`
- Kill: `taskkill /PID <pid> /F`

### Stale build
- Clear cache: `rm -rf node_modules/.vite`
- Reinstall: `$env:NODE_ENV = ""; npm install`

## Environment
- **Working directory:** `D:\RAG\Web-RAG\frontend`
- **Node version:** v25.2.1
- **npm version:** 11.7.0
- **Default port:** 5173
