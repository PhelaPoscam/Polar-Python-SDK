# 🚀 GitHub Push Guide - AWE Polar Project

## Prerequisites

### 1. Install Git (if not already installed)

Download and install Git from: https://git-scm.com/download/win

Or install via Windows Package Manager:
```powershell
winget install --id Git.Git -e --source winget
```

After installation, restart PowerShell and verify:
```powershell
git --version
```

### 2. Configure Git (First Time Only)

```powershell
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## 📤 Step-by-Step: Push to GitHub

### Option 1: Create New Repository on GitHub First (Recommended)

#### Step 1: Create Repository on GitHub
1. Go to https://github.com
2. Click the **"+"** icon → **"New repository"**
3. Repository name: `AWE_Polar_Project` (or your preferred name)
4. Description: `Real-time stress monitoring with Polar H10, ML, and LLM`
5. Choose **Public** or **Private**
6. ⚠️ **DO NOT** initialize with README, .gitignore, or license (we already have these)
7. Click **"Create repository"**

#### Step 2: Initialize Local Repository

Open PowerShell in your project directory:

```powershell
cd "c:\Python Project\AWE_Polar_Project"
```

Initialize git:
```powershell
git init
```

#### Step 3: Add All Files

```powershell
# Add all files (respecting .gitignore)
git add .

# Check what will be committed
git status
```

**Important**: The following files will be excluded (per `.gitignore`):
- `venv/` (virtual environment)
- `*.pkl` (model files)
- `.env` (API keys)
- `*.csv` (data files)
- `__pycache__/`

#### Step 4: Create First Commit

```powershell
git commit -m "Initial commit: AWE Polar stress monitoring project

- ML-based stress detection using Random Forest
- Real-time Polar H10 integration via Bluetooth
- Streamlit dashboard with live charts
- OpenAI LLM integration for insights
- Comprehensive test suite (36 tests)
- Complete documentation and setup scripts"
```

#### Step 5: Add Remote Repository

Replace `YOUR_USERNAME` with your GitHub username:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/AWE_Polar_Project.git
```

Or use SSH (if you have SSH keys set up):
```powershell
git remote add origin git@github.com:YOUR_USERNAME/AWE_Polar_Project.git
```

Verify remote:
```powershell
git remote -v
```

#### Step 6: Push to GitHub

```powershell
# Push to main branch
git branch -M main
git push -u origin main
```

If prompted, enter your GitHub credentials or use a Personal Access Token.

### Option 2: Using GitHub CLI (gh)

If you have GitHub CLI installed:

```powershell
# Login to GitHub
gh auth login

# Create repo and push
gh repo create AWE_Polar_Project --public --source=. --push
```

## 📝 What Gets Pushed to GitHub

### ✅ Files Included:
```
✓ ML_model3.py
✓ polar_awe9.py
✓ generate_sample_data.py
✓ requirements.txt
✓ README.md
✓ SETUP_SUMMARY.md
✓ CHECKLIST.md
✓ CONTRIBUTING.md
✓ LICENSE
✓ .gitignore
✓ .env.example
✓ setup.ps1
✓ start.ps1
✓ tests/
  ✓ __init__.py
  ✓ conftest.py
  ✓ test_ml_model.py
  ✓ test_polar_awe.py
  ✓ test_integration.py
```

### ❌ Files Excluded (by .gitignore):
```
✗ venv/ (virtual environment - too large)
✗ .env (contains API keys - SECURITY)
✗ *.pkl (model files - regenerated)
✗ *.csv (data files - too large)
✗ __pycache__/ (Python cache)
✗ .pytest_cache/
```

## 🔐 Security: Protecting Your API Keys

**CRITICAL**: Never commit `.env` file with API keys!

### If you accidentally committed .env:

```powershell
# Remove from git (keep local file)
git rm --cached .env

# Commit the removal
git commit -m "Remove .env from version control"

# Push changes
git push
```

Then:
1. Rotate your OpenAI API key immediately
2. Check GitHub for exposed secrets: https://github.com/settings/security

## 📊 GitHub Repository Setup

### Add Repository Badges (Optional)

Add to the top of your README.md:

```markdown
# AWE Polar Project

![Python](https://img.shields.io/badge/python-3.14-blue.svg)
![Tests](https://img.shields.io/badge/tests-36%20passed-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
```

### Enable GitHub Actions (Optional)

Create `.github/workflows/tests.yml` for automated testing:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.14'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    - name: Run tests
      run: pytest tests/ -v
```

## 🔄 Regular Workflow (After Initial Push)

### Making Changes:

```powershell
# 1. Check current status
git status

# 2. Add changed files
git add .

# 3. Commit with descriptive message
git commit -m "Add feature: XYZ"

# 4. Push to GitHub
git push
```

### Useful Git Commands:

```powershell
# View commit history
git log --oneline

# Check differences
git diff

# Create a new branch
git checkout -b feature/new-feature

# Switch branches
git checkout main

# Merge branch
git merge feature/new-feature

# Pull latest changes
git pull
```

## 📦 Creating a Release

```powershell
# Tag a version
git tag -a v1.0.0 -m "First release: Stress monitoring with ML and LLM"

# Push tags
git push --tags
```

Then create a release on GitHub:
1. Go to your repository
2. Click **"Releases"** → **"Create a new release"**
3. Select the tag (v1.0.0)
4. Add release notes
5. Publish release

## 🌟 Repository Settings

### Recommended Settings:
1. **Topics**: Add topics like `machine-learning`, `streamlit`, `polar-h10`, `stress-detection`, `hrv`
2. **Description**: "Real-time stress monitoring using Polar H10, ML, and LLM"
3. **Website**: Add your deployed Streamlit URL (if applicable)

### Branch Protection (Optional):
1. Go to Settings → Branches
2. Add rule for `main` branch
3. Require pull request reviews
4. Require status checks to pass

## 🎯 Quick Command Reference

```powershell
# One-time setup
cd "c:\Python Project\AWE_Polar_Project"
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/AWE_Polar_Project.git
git push -u origin main

# Regular updates
git add .
git commit -m "Description of changes"
git push
```

## ❗ Troubleshooting

### "Permission denied"
- Use Personal Access Token instead of password
- Generate at: https://github.com/settings/tokens

### "Remote already exists"
```powershell
git remote remove origin
git remote add origin YOUR_REPO_URL
```

### "Large files"
- Ensure .gitignore is working
- Check: `git status` should not show venv/, *.pkl, *.csv

### "Merge conflicts"
```powershell
git pull
# Resolve conflicts in files
git add .
git commit -m "Resolve merge conflicts"
git push
```

## 📚 Resources

- Git Documentation: https://git-scm.com/doc
- GitHub Guides: https://guides.github.com
- GitHub CLI: https://cli.github.com

---

**Ready to push?** Follow the steps above and your project will be on GitHub! 🚀
