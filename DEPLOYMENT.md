# Deployment Guide

## Overview

This application will be deployed as:
- **Frontend**: Vercel (React + TypeScript)
- **Backend**: Render (Node.js + Express + Python)

---

## Architecture

```
analyst/ (Workspace - NOT a git repo)
├── AI Analyst/                                    → Git Repo 1: Deploy to Vercel (Frontend)
│   └── (all React/frontend files)
│
└── MultiAgent Financial analyst/                  → Git Repo 2: Deploy to Render (Backend + Python)
    ├── src/                                       → Node.js/Express backend
    │   ├── server.ts
    │   ├── routes/
    │   └── services/
    │       └── pythonService.ts
    ├── agents/                                    → Python agent files
    ├── graph/                                     → LangGraph orchestration
    ├── tools/                                     → Data fetching tools
    ├── schemas/                                   → State schemas
    ├── services/                                  → LLM service layer (Python)
    ├── config.py                                  → Python configuration
    ├── main.py                                    → Python entry point
    ├── requirements.txt                           → Python dependencies
    ├── package.json                               → Node.js dependencies
    └── tsconfig.json                              → TypeScript config
```

### Key Points:

1. **Two separate git repositories**:
   - `AI Analyst/` - Frontend repository (deploy to Vercel)
   - `MultiAgent Financial analyst/` - Backend + Python repository (deploy to Render)

2. **Main `analyst/` folder is NOT a git repo** - It's just a workspace containing the two repos

3. **All files in root of MultiAgent Financial analyst/** - No subdirectories for backend/model, everything is merged together

4. **Path resolution** - The Node.js backend uses relative paths (`../../main.py`) to find Python files in the same directory

---

## Frontend Deployment (Vercel)

### Directory Structure

Deploy **only** the `AI Analyst/` directory to Vercel.

### Steps

1. **Connect Repository**
   - Go to [Vercel Dashboard](https://vercel.com/dashboard)
   - Import your GitHub/GitLab repository
   - Set **Root Directory** to: `AI Analyst`

2. **Build Settings**
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
   - **Install Command**: `npm install`

3. **Environment Variables**
   - `VITE_API_URL`: Your Render backend URL (e.g., `https://your-backend.onrender.com/api`)
   - This is used by the frontend to communicate with the backend

4. **Deploy**
   - Vercel will automatically deploy on every push to main branch
   - Or trigger manual deployment

### Frontend Environment Variables

Create `.env.production` in `AI Analyst/`:
```env
VITE_API_URL=https://your-backend-name.onrender.com/api
```

---

## Backend Deployment (Render)

### Directory Structure

Deploy the **entire `MultiAgent Financial analyst/` directory** to Render (this is a separate git repository). All files (Node.js backend and Python files) are in the root of this directory.

### Option 1: Deploy Root Directory (Recommended)

1. **Create New Web Service on Render**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your repository

2. **Build & Start Commands**

   **Root Directory**: (leave empty - use project root)

   **Build Command**:
   ```bash
   pip install -r requirements.txt && npm install && npm run build
   ```
   
   **Start Command**:
   ```bash
   npm start
   ```

3. **Python Setup**

   Render needs Python installed. Add this to your build command:
   ```bash
   # Install Python dependencies
   pip install -r requirements.txt
   
   # Then install Node.js dependencies
   npm install && npm run build
   ```

   **Full Build Command**:
   ```bash
   pip install -r requirements.txt && npm install && npm run build
   ```

4. **Environment Variables** (Required)

   Set these in Render Dashboard → Environment:
   ```
   GEMINI_API_KEY=your_gemini_api_key
   HUGGINGFACE_API_KEY=your_hf_api_key
   FRED_API_KEY=your_fred_api_key (optional)
   NODE_ENV=production
   PORT=10000 (Render sets this automatically, but can override)
   ```

5. **Python Path**

   The backend service expects Python to be available. Render provides Python 3.x by default.
   - The backend will use system Python (not venv) on Render
   - Make sure Python 3.x is available in PATH

### Option 2: Alternative Structure (Not Needed)

The current structure (`MultiAgent Financial analyst/` with `backend/` and `model/` subdirectories) is already clean and organized. No further restructuring needed.

---

## Backend Configuration Updates

### Update pythonService.ts for Production

The current code looks for Python files relative to the backend. For production on Render:

```typescript
// In MultiAgent Financial analyst/src/services/pythonService.ts
// The path resolution works as follows:
const projectRoot = path.resolve(__dirname, '../..');
const pythonScript = path.resolve(projectRoot, 'main.py');
```

### Verify Path Resolution

The backend service resolves paths as:
- `__dirname` = `MultiAgent Financial analyst/dist/services` (after build)
- `../..` = `MultiAgent Financial analyst/` (project root where Python files are)
- `../../main.py` = `MultiAgent Financial analyst/main.py`

This should work correctly on Render.

---

## Required Files for Deployment

### 1. render.yaml (Optional but Recommended)

Create `render.yaml` at project root:

```yaml
services:
  - type: web
    name: analyst-backend
    runtime: node
    plan: free  # or starter/pro
    buildCommand: pip install -r requirements.txt && npm install && npm run build
    startCommand: npm start
    envVars:
      - key: GEMINI_API_KEY
        sync: false  # Set manually in dashboard
      - key: HUGGINGFACE_API_KEY
        sync: false
      - key: FRED_API_KEY
        sync: false
      - key: NODE_ENV
        value: production
```

### 2. .renderignore (Optional)

Create `.renderignore` at project root to exclude unnecessary files:

```
# Development files
venv/
__pycache__/
*.pyc
node_modules/
.env
.env.local

# Output files
outputs/
dist/

# IDE files
.vscode/
.idea/
*.swp
*.swo

# Documentation (optional - can include if small)
# PLAN.md
# timeline.md
```

### 3. Update package.json Build Script

Ensure `MultiAgent Financial analyst/package.json` has:
```json
{
  "scripts": {
    "build": "tsc",
    "start": "node dist/server.js"
  }
}
```

---

## Testing Deployment

### Local Testing (Simulate Render)

1. **Build backend**:
   ```bash
   cd "MultiAgent Financial analyst"
   npm run build
   ```

2. **Test Python path resolution**:
   ```bash
   cd "MultiAgent Financial analyst"
   npm run build
   node dist/services/pythonService.js  # Should find Python files in ../main.py
   ```

3. **Run production build**:
   ```bash
   NODE_ENV=production npm start
   ```

### After Deployment

1. **Test backend endpoint**:
   ```bash
   curl https://your-backend.onrender.com/api/health
   ```

2. **Test analysis endpoint** (should return 200):
   ```bash
   curl -X POST https://your-backend.onrender.com/api/analyze \
     -H "Content-Type: application/json" \
     -d '{"ticker":"AAPL","horizon":"medium","risk_profile":"moderate"}'
   ```

3. **Update frontend environment variable**:
   - Set `VITE_API_URL` in Vercel to your Render backend URL

4. **Test frontend**:
   - Visit your Vercel URL
   - Try analyzing a stock
   - Check browser console for errors

---

## Troubleshooting

### Backend Issues

**Python not found**:
- Render should have Python 3.x by default
- Check build logs for Python version
- May need to specify Python version in build command

**Python dependencies not installed**:
- Ensure `pip install -r requirements.txt` runs in build command
- Check build logs for pip installation errors

**Path resolution errors**:
- Verify Python files exist at expected location
- Check Render logs for path resolution
- May need to adjust path in `pythonService.ts`

**Environment variables not set**:
- Double-check all API keys are set in Render dashboard
- Ensure `.env` file is NOT committed (use Render environment variables)

### Frontend Issues

**API connection errors**:
- Verify `VITE_API_URL` is set correctly in Vercel
- Check CORS is enabled in backend (should already be configured)
- Verify backend is running and accessible

**CORS errors**:
- Ensure backend CORS middleware allows your Vercel domain
- Check `MultiAgent Financial analyst/src/server.ts` for CORS configuration

---

## Cost Considerations

### Vercel (Frontend)
- **Free tier**: Sufficient for small projects
- Limits: 100GB bandwidth/month
- Perfect for static React apps

### Render (Backend)
- **Free tier**: Available but has limitations
  - Spins down after 15 minutes of inactivity
  - Cold starts take 30-60 seconds
  - 750 hours/month limit
- **Starter tier**: $7/month
  - Always on (no spin-down)
  - Better for production use

### Recommendation
- Start with free tier for testing
- Upgrade to Starter ($7/month) for production if needed

---

## Security Considerations

1. **Never commit API keys**:
   - Use `.gitignore` for `.env` files
   - Use environment variables in Vercel/Render

2. **CORS Configuration**:
   - Only allow your Vercel domain
   - Don't allow all origins (`*`) in production

3. **Rate Limiting** (Future enhancement):
   - Consider adding rate limiting to prevent abuse
   - Render free tier has built-in limits

---

## Next Steps

1. ✅ Create `render.yaml` (optional)
2. ✅ Create `.renderignore` (optional)
3. ✅ Test backend build locally
4. ✅ Deploy backend to Render
5. ✅ Get backend URL and update frontend env var
6. ✅ Deploy frontend to Vercel
7. ✅ Test full flow end-to-end

---

## Quick Reference

### Frontend (Vercel)
- **Root**: `AI Analyst/`
- **Build**: `npm run build`
- **Output**: `dist/`
- **Env Var**: `VITE_API_URL`

### Backend (Render)
- **Root**: `MultiAgent Financial analyst/` (git repository root)
- **Build**: `pip install -r requirements.txt && npm install && npm run build`
- **Start**: `npm start`
- **Env Vars**: `GEMINI_API_KEY`, `HUGGINGFACE_API_KEY`, `FRED_API_KEY`, `NODE_ENV`
- **Python**: Uses system Python 3 (provided by Render)

## Directory Structure Summary

### What Goes Where?

**Frontend (Vercel)**:
- Git Repository: `AI Analyst/`
- All React/frontend files in root of this directory
- React app (Vite build)

**Backend (Render)**:
- Git Repository: `MultiAgent Financial analyst/`
- All files (Node.js backend + Python) in root of this directory:
  - Node.js: `src/`, `package.json`, `tsconfig.json`
  - Python: `agents/`, `graph/`, `tools/`, `schemas/`, `services/`, `config.py`, `main.py`, `requirements.txt`
- Build process: Installs Python deps, then installs Node.js deps and builds TypeScript

**Why this structure?**
- **Two separate git repositories** for clean separation
- **Frontend repo** (`AI Analyst/`) is standalone and deploys to Vercel
- **Backend repo** (`MultiAgent Financial analyst/`) contains everything needed for the backend service
- **No subdirectories** - everything is in the root for simplicity
- **Main `analyst/` folder** is just a workspace, not a git repo

