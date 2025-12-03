# Mouse Jiggler Hash Scraper

Scrapes GitHub for mouse jiggler executables and scripts, then generates MD5 hashes for use in EDR/DLP blocklists or insider threat detection tools.

## Setup

### Getting a GitHub Token

1. Go to **github.com** and log in
2. Click your **profile picture** (top right) → **Settings**
3. Scroll down the left sidebar → **Developer settings** (at the bottom)
4. **Personal access tokens** → **Tokens (classic)**
5. **Generate new token** → **Generate new token (classic)**
6. Give it a name like "jiggler-scraper"
7. For permissions, you only need **public_repo** (or leave all boxes unchecked since we're only reading public data)
8. Click **Generate token**
9. **Copy the token immediately** - you won't see it again

Without a token you're limited to 60 API requests/hour. With a token you get 5,000/hour.

## How to Run

```bash
# Clone the repo
git clone https://github.com/yourusername/mouse-jiggler-scraper.git
cd mouse-jiggler-scraper

# Set your token
export GITHUB_TOKEN="your_token_here"

# Run and save output
python3 jiggler_scraper.py | tee hashes.txt

Search Terms

The script searches GitHub for repos matching these keywords:

    mouse jiggler, mouse mover, mouse wiggler, jiggle mouse, wiggle mouse, mouse shaker
    keep awake mouse, anti idle mouse, prevent idle mouse, prevent sleep mouse, prevent screen lock
    anti afk, anti away, stay active, keep active mouse, idle buster, idle preventer
    caffeine mouse, nosleep mouse, insomnia mouse, stay awake pc, dont sleep, no sleep app, awake tool
    teams status active, slack status green, keep teams active, teams away prevent, zoom presence
    teams green dot, slack away prevent, wfh mouse, remote work mouse
    auto move mouse, automatic mouse movement, simulate mouse movement, fake mouse input
    mouse automation idle, cursor mover, move cursor automatically, random mouse movement
    usb mouse jiggler, pico jiggler, arduino mouse mover, teensy mouse, digispark mouse
    attiny85 mouse, raspberry pi mouse jiggler, esp32 mouse, hid mouse emulator
    move mouse python, pyautogui idle, autohotkey mouse move, powershell mouse move
    keep pc awake, prevent computer sleep, stop screensaver, disable screen lock
