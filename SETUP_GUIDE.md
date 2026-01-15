# MangaNegus Complete Setup Guide

> **Version:** 3.1.0
> **Last Updated:** 2026-01-15
> **Platforms:** Windows 10/11, Linux (Arch, Ubuntu, Debian), macOS

A step-by-step guide to get MangaNegus running on your machine, written for beginners.

---

## Table of Contents

1. [Quick Start (If Already Set Up)](#quick-start-if-already-set-up)
2. [Windows Setup](#windows-setup)
3. [Linux Setup](#linux-setup)
4. [macOS Setup](#macos-setup)
5. [Installing Dependencies](#installing-dependencies)
6. [Database Setup (PostgreSQL)](#database-setup-postgresql)
7. [Running the Application](#running-the-application)
8. [IDE Setup (VSCode)](#ide-setup-vscode)
9. [Troubleshooting](#troubleshooting)
10. [Optional: Redis & Celery](#optional-redis--celery)

---

## Quick Start (If Already Set Up)

If you've already completed setup, just run:

**Linux/macOS:**
```bash
cd /path/to/Manga-Negus
source .venv/bin/activate
python run.py
```

**Windows (PowerShell):**
```powershell
cd C:\path\to\Manga-Negus
.venv\Scripts\Activate.ps1
python run.py
```

**Windows (Command Prompt):**
```cmd
cd C:\path\to\Manga-Negus
.venv\Scripts\activate.bat
python run.py
```

Then open your browser to: **http://127.0.0.1:5000**

---

## Windows Setup

### Step 1: Install Python

1. **Download Python:**
   - Go to https://www.python.org/downloads/
   - Download Python 3.11 or 3.12 (recommended)
   - **IMPORTANT:** Download the Windows installer (64-bit)

2. **Run the Installer:**
   - **CRITICAL:** Check the box that says **"Add Python to PATH"** at the bottom of the installer
   - Click "Customize installation" for more control
   - Make sure these are checked:
     - pip
     - py launcher
     - Add Python to environment variables
   - Click "Install Now"

3. **Verify Installation:**
   Open PowerShell or Command Prompt and run:
   ```powershell
   python --version
   # Should show: Python 3.11.x or 3.12.x

   pip --version
   # Should show: pip 24.x.x from ...
   ```

### Step 2: Fix PATH (If Python Not Found)

If you get "python is not recognized", you need to add Python to PATH manually:

1. **Find Python Installation Path:**
   - Usually: `C:\Users\YourUsername\AppData\Local\Programs\Python\Python311\`
   - Or: `C:\Python311\`

2. **Add to PATH:**
   - Press `Win + R`, type `sysdm.cpl`, press Enter
   - Click "Advanced" tab → "Environment Variables"
   - Under "User variables", find "Path" and click "Edit"
   - Click "New" and add these paths (replace with your Python version):
     ```
     C:\Users\YourUsername\AppData\Local\Programs\Python\Python311\
     C:\Users\YourUsername\AppData\Local\Programs\Python\Python311\Scripts\
     ```
   - Click "OK" on all windows
   - **Restart PowerShell/Command Prompt**

3. **Verify Again:**
   ```powershell
   python --version
   pip --version
   ```

### Step 3: Install Visual C++ Build Tools (Required for some packages)

Some packages like `lupa` (Lua runtime) need compilation:

1. Download "Build Tools for Visual Studio" from:
   https://visualstudio.microsoft.com/visual-cpp-build-tools/

2. Run the installer and select:
   - "Desktop development with C++"
   - Make sure "Windows 10 SDK" is checked

3. This is about 3-5 GB download. Wait for installation to complete.

### Step 4: Clone the Repository

1. **Install Git** (if not installed):
   Download from https://git-scm.com/download/win

2. **Clone the repo:**
   ```powershell
   cd C:\Users\YourUsername\projects
   git clone https://github.com/bookers1897/Manga-Negus.git
   cd Manga-Negus
   ```

### Step 5: Create Virtual Environment (Windows)

```powershell
# Create virtual environment
python -m venv .venv

# Activate it (PowerShell)
.venv\Scripts\Activate.ps1

# If you get a security error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try again:
.venv\Scripts\Activate.ps1
```

**For Command Prompt instead of PowerShell:**
```cmd
.venv\Scripts\activate.bat
```

Your prompt should now show `(.venv)` at the beginning.

---

## Linux Setup

### Arch Linux / CachyOS / Manjaro

```bash
# Install Python and pip
sudo pacman -S python python-pip

# Install development tools (needed for some packages)
sudo pacman -S base-devel

# Verify installation
python --version  # Should show 3.11+
pip --version

# Navigate to your projects folder
cd ~/projects

# Clone the repository
git clone https://github.com/bookers1897/Manga-Negus.git
cd Manga-Negus

# Create virtual environment
python -m venv .venv

# Activate it
source .venv/bin/activate
```

### Ubuntu / Debian / Linux Mint

```bash
# Update package lists
sudo apt update

# Install Python and required tools
sudo apt install python3 python3-pip python3-venv python3-dev

# Install build tools (needed for lupa, psycopg2)
sudo apt install build-essential libpq-dev

# Verify installation
python3 --version
pip3 --version

# Navigate to your projects folder
cd ~/projects

# Clone the repository
git clone https://github.com/bookers1897/Manga-Negus.git
cd Manga-Negus

# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate
```

### Fedora / RHEL / CentOS

```bash
# Install Python and development tools
sudo dnf install python3 python3-pip python3-devel
sudo dnf groupinstall "Development Tools"
sudo dnf install postgresql-devel

# Clone and setup
cd ~/projects
git clone https://github.com/bookers1897/Manga-Negus.git
cd Manga-Negus
python3 -m venv .venv
source .venv/bin/activate
```

---

## macOS Setup

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.11

# Install PostgreSQL (needed for psycopg2)
brew install postgresql

# Verify installation
python3 --version
pip3 --version

# Clone the repository
cd ~/projects
git clone https://github.com/bookers1897/Manga-Negus.git
cd Manga-Negus

# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate
```

---

## Installing Dependencies

**Make sure your virtual environment is activated first!** You should see `(.venv)` in your prompt.

### Install All Packages

```bash
# Upgrade pip first (important!)
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt
```

### If You Get Errors

**lupa fails to build (Windows):**
```powershell
# Make sure Visual C++ Build Tools are installed
# If still failing, try:
pip install lupa --no-cache-dir
```

**psycopg2 fails (Linux):**
```bash
# Ubuntu/Debian:
sudo apt install libpq-dev

# Arch:
sudo pacman -S postgresql-libs
```

**curl_cffi fails:**
```bash
# Try installing with no cache:
pip install curl_cffi --no-cache-dir

# On Windows, make sure you have Visual C++ Build Tools
```

### Install Packages One by One (If requirements.txt Fails)

```bash
# Core packages (required)
pip install flask flask-limiter requests beautifulsoup4 lxml

# Database (required)
pip install psycopg2-binary sqlalchemy alembic

# Web scraping helpers
pip install curl_cffi cloudscraper aiohttp httpx aiofiles

# Selenium for JavaScript-heavy sites (optional)
pip install selenium webdriver-manager

# Metadata and utilities
pip install jikanpy rapidfuzz cachetools Pillow

# Lua runtime (optional, for FMD modules)
pip install lupa

# Background jobs (optional, needs Redis)
pip install celery redis
```

### Verify Installation

```bash
# Check that Flask is installed
python -c "import flask; print(f'Flask {flask.__version__}')"

# Check SQLAlchemy
python -c "import sqlalchemy; print(f'SQLAlchemy {sqlalchemy.__version__}')"

# List all installed packages
pip list
```

---

## Database Setup (PostgreSQL)

MangaNegus can run with SQLite (default) or PostgreSQL (recommended for production).

### Option A: SQLite (Zero Setup, Good for Testing)

No setup needed! MangaNegus will automatically create a `manganegus.db` file.

### Option B: PostgreSQL (Recommended for Real Use)

**Windows:**
1. Download PostgreSQL from https://www.postgresql.org/download/windows/
2. Run the installer
3. Remember the password you set for the `postgres` user
4. Open pgAdmin or psql and create a database:
   ```sql
   CREATE DATABASE manganegus;
   ```

**Linux (Arch):**
```bash
sudo pacman -S postgresql
sudo -u postgres initdb -D /var/lib/postgres/data
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo -u postgres createdb manganegus
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres createdb manganegus
```

**Create .env File:**
```bash
# In the Manga-Negus directory, create a file called .env:
echo "DATABASE_URL=postgresql://postgres:yourpassword@localhost/manganegus" > .env
```

Replace `yourpassword` with your actual PostgreSQL password.

**Run Database Migrations:**
```bash
# With virtual environment activated:
alembic upgrade head
```

---

## Running the Application

### Start the Server

```bash
# Make sure virtual environment is activated!
# You should see (.venv) in your prompt

# Run the server
python run.py
```

**Expected Output:**
```
============================================================
  MangaNegus v3.1.0 - Multi-Source Edition
============================================================

📚 Loaded 34 sources
🌐 Server: http://127.0.0.1:5000
============================================================
 * Running on http://127.0.0.1:5000
```

### Access the App

Open your browser to: **http://127.0.0.1:5000**

### Stop the Server

Press `Ctrl+C` in the terminal.

---

## IDE Setup (VSCode)

### Configure Python Interpreter

1. Open VSCode
2. Open the Manga-Negus folder
3. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
4. Type "Python: Select Interpreter"
5. Choose the one that shows `.venv` (e.g., `Python 3.11.x ('.venv': venv)`)

### Create settings.json

Create `.vscode/settings.json` in the project:

**Windows:**
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
    "python.terminal.activateEnvironment": true,
    "python.analysis.typeCheckingMode": "basic"
}
```

**Linux/macOS:**
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.terminal.activateEnvironment": true,
    "python.analysis.typeCheckingMode": "basic"
}
```

### Run from VSCode

1. Open `run.py`
2. Click the "Play" button in the top right
3. Or press `F5` to run with debugging

---

## Troubleshooting

### "Python is not recognized" (Windows)

Python isn't in your PATH. See [Step 2: Fix PATH](#step-2-fix-path-if-python-not-found) above.

### "No module named 'flask'"

Virtual environment isn't activated:
```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows Command Prompt
.venv\Scripts\activate.bat
```

### "Permission denied" running PowerShell script (Windows)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Port 5000 already in use

**Linux/macOS:**
```bash
# Find what's using port 5000
lsof -i :5000

# Kill the process
kill -9 <PID>
```

**Windows:**
```powershell
# Find what's using port 5000
netstat -ano | findstr :5000

# Kill the process (replace PID)
taskkill /PID <PID> /F
```

### lupa/psycopg2 won't install (Windows)

Make sure Visual C++ Build Tools are installed. See [Step 3](#step-3-install-visual-c-build-tools-required-for-some-packages).

### Database connection error

1. Make sure PostgreSQL is running
2. Check your `.env` file has the correct password
3. Make sure the database exists:
   ```bash
   psql -U postgres -c "\l"  # List databases
   ```

### Virtual environment missing

```bash
# Recreate it
python -m venv .venv

# Activate and reinstall packages
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

---

## Optional: Redis & Celery

For background download jobs that survive server restarts:

### Install Redis

**Windows:**
- Download from https://github.com/microsoftarchive/redis/releases
- Or use WSL2 with Ubuntu

**Linux (Arch):**
```bash
sudo pacman -S redis
sudo systemctl start redis
sudo systemctl enable redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install redis-server
sudo systemctl start redis
```

**macOS:**
```bash
brew install redis
brew services start redis
```

### Configure Celery

Create `.env` file:
```
CELERY_BROKER_URL=redis://localhost:6379/0
```

### Start Celery Worker

In a separate terminal:
```bash
cd Manga-Negus
source .venv/bin/activate  # or Windows equivalent
celery -A manganegus_app.celery_app worker --loglevel=info
```

---

## Quick Reference

### Daily Workflow

```bash
# 1. Navigate to project
cd /path/to/Manga-Negus

# 2. Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\Activate.ps1  # Windows PowerShell

# 3. Run the app
python run.py

# 4. Open browser to http://127.0.0.1:5000
```

### Update Dependencies

```bash
# Activate venv first, then:
pip install -r requirements.txt --upgrade
```

### Run Database Migrations

```bash
alembic upgrade head
```

---

## Getting Help

- **GitHub Issues:** https://github.com/bookers1897/Manga-Negus/issues
- **Documentation:** See `CLAUDE.md` for architecture details

---

**Happy Reading!** 📚
