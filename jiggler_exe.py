#!/usr/bin/env python3
"""
Mouse Jiggler Executable Finder
Just lists executable names - no downloads
"""

import requests
import time
import os
import sys

class JigglerExeFinder:
    def __init__(self, token=None):
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"
        
        self.search_terms = [
            # Direct jiggler terms
            "mouse jiggler",
            "mouse mover", 
            "mouse wiggler",
            "jiggle mouse",
            "wiggle mouse",
            "mouse shaker",
            
            # Anti-idle / keep awake
            "keep awake mouse",
            "anti idle mouse",
            "prevent idle mouse",
            "prevent sleep mouse",
            "prevent screen lock",
            "anti afk",
            "anti away",
            "stay active",
            "keep active mouse",
            "idle buster",
            "idle preventer",
            
            # Caffeine-style tools
            "caffeine mouse",
            "nosleep mouse",
            "insomnia mouse",
            "stay awake pc",
            "dont sleep",
            "no sleep app",
            "awake tool",
            
            # Work-from-home / teams status
            "teams status active",
            "slack status green",
            "keep teams active",
            "teams away prevent",
            "zoom presence",
            "teams green dot",
            "slack away prevent",
            "wfh mouse",
            "remote work mouse",
            
            # Generic auto-move
            "auto move mouse",
            "automatic mouse movement",
            "simulate mouse movement",
            "fake mouse input",
            "mouse automation idle",
            "cursor mover",
            "move cursor automatically",
            "random mouse movement",
            
            # Hardware-based
            "usb mouse jiggler",
            "pico jiggler",
            "arduino mouse mover",
            "teensy mouse",
            "digispark mouse",
            "attiny85 mouse",
            "raspberry pi mouse jiggler",
            "esp32 mouse",
            "hid mouse emulator",
            
            # Specific tools/languages
            "move mouse python",
            "pyautogui idle",
            "autohotkey mouse move",
            "powershell mouse move",
            "keep pc awake",
            "prevent computer sleep",
            "stop screensaver",
            "disable screen lock",
            
            # Additional terms
            "mouse keep alive",
            "jiggler software",
            "mouse activity simulator",
            "fake activity",
            "simulate activity",
            "appear online",
            "appear active",
            "presence keeper",
            "status keeper",
            "away preventer",
            "afk bypass",
            "idle bypass",
            "screen lock bypass",
            "screensaver bypass",
            "workrave bypass",
            "mouse clicker idle",
            "auto clicker idle",
            "keep session alive",
            "session keeper",
            "vnc keep alive",
            "rdp keep alive",
            "citrix keep alive",
            "virtual desktop awake",
            "vm keep awake",
            "nomouse",
            "wiggler",
            "jiggler",
            "movemouse",
            "caffeine app",
            "amphetamine windows",
            "nosleep app",
            "stayawake",
            "keepawake",
            "dontlock",
            "nolock screen",
        ]
        
        self.exclude_keywords = [
            "owasp",
            "security-list",
            "awesome-",
            "cheatsheet",
            "vulnerability",
            "cve-",
            "exploit",
            "pentest",
            "malware-sample",
            "virus-sample",
        ]
        
        self.extensions = ['.exe', '.msi']
        self.seen_names = set()
        self.seen_repos = set()

    def is_excluded(self, owner, repo):
        full_name = f"{owner}/{repo}".lower()
        for keyword in self.exclude_keywords:
            if keyword in full_name:
                return True
        return False

    def search_repos(self, query, max_results=15):
        url = "https://api.github.com/search/repositories"
        params = {"q": query, "sort": "stars", "per_page": max_results}
        
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code == 403:
                print("# Rate limited, waiting 60s...", file=sys.stderr, flush=True)
                time.sleep(60)
                resp = requests.get(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code != 200:
                return []
            return resp.json().get("items", [])
        except:
            return []

    def scan_repo(self, owner, repo, path="", depth=0):
        if depth > 4:
            return
        
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                return
            
            items = resp.json()
            if not isinstance(items, list):
                return
            
            for item in items:
                if item["type"] == "file":
                    name = item["name"]
                    if any(name.lower().endswith(ext) for ext in self.extensions):
                        if name not in self.seen_names:
                            self.seen_names.add(name)
                            print(name, flush=True)
                
                elif item["type"] == "dir":
                    skip = ['.git', 'node_modules', '__pycache__', 'docs', 'test', 'tests', '.github']
                    if item["name"].lower() not in skip:
                        self.scan_repo(owner, repo, item["path"], depth + 1)
        except:
            pass

    def scan_releases(self, owner, repo):
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                return
            
            for release in resp.json()[:5]:
                for asset in release.get("assets", []):
                    name = asset["name"]
                    if any(name.lower().endswith(ext) for ext in self.extensions):
                        if name not in self.seen_names:
                            self.seen_names.add(name)
                            print(name, flush=True)
        except:
            pass

    def run(self):
        total = len(self.search_terms)
        
        print(f"# Starting scan with {total} search terms", file=sys.stderr, flush=True)
        print(f"# Excluding repos matching: {self.exclude_keywords}", file=sys.stderr, flush=True)
        print("#" + "=" * 50, file=sys.stderr, flush=True)
        
        for i, term in enumerate(self.search_terms):
            print(f"# [{i+1}/{total}] {term}", file=sys.stderr, flush=True)
            
            for repo in self.search_repos(term):
                repo_id = repo["id"]
                if repo_id in self.seen_repos:
                    continue
                self.seen_repos.add(repo_id)
                
                owner = repo["owner"]["login"]
                name = repo["name"]
                
                if self.is_excluded(owner, name):
                    print(f"#   Skipping excluded: {owner}/{name}", file=sys.stderr, flush=True)
                    continue
                
                self.scan_repo(owner, name)
                self.scan_releases(owner, name)
                time.sleep(0.5)
            
            time.sleep(1)
        
        print("#" + "=" * 50, file=sys.stderr, flush=True)
        print(f"# COMPLETE", file=sys.stderr, flush=True)
        print(f"# Total unique executables: {len(self.seen_names)}", file=sys.stderr, flush=True)
        print(f"# Repos scanned: {len(self.seen_repos)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("# WARNING: No GITHUB_TOKEN - will hit rate limits fast", file=sys.stderr)
    finder = JigglerExeFinder(token)
    finder.run()
