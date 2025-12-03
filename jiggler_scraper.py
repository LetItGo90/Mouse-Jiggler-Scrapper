#!/usr/bin/env python3
"""
Simple Mouse Jiggler MD5 Collector
Downloads files to memory (not disk), hashes them, prints MD5
"""

import requests
import hashlib
import base64
import time
import os

class JigglerHasher:
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
            
            # Specific tool names (popular ones)
            "move mouse python",
            "pyautogui idle",
            "autohotkey mouse move",
            "powershell mouse move",
            "mouse without borders idle",
            "keep pc awake",
            "prevent computer sleep",
            "stop screensaver",
            "disable screen lock"
        ]
        
        self.extensions = ['.exe', '.msi', '.py', '.ps1', '.bat', '.ahk', '.jar']
        self.seen_hashes = set()
        self.seen_repos = set()

    def search_repos(self, query, max_results=10):
        url = "https://api.github.com/search/repositories"
        params = {"q": query, "sort": "stars", "per_page": max_results}
        
        resp = requests.get(url, headers=self.headers, params=params)
        if resp.status_code == 403:
            print(f"# Rate limited, waiting 60s...", flush=True)
            time.sleep(60)
            resp = requests.get(url, headers=self.headers, params=params)
        if resp.status_code != 200:
            return []
        
        return resp.json().get("items", [])

    def get_file_bytes(self, owner, repo, path):
        """Download file content into memory - nothing saved to disk."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=self.headers)
        
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        
        if data.get("content"):
            try:
                return base64.b64decode(data["content"])
            except:
                pass
        
        if data.get("download_url"):
            try:
                r = requests.get(data["download_url"], timeout=30)
                return r.content if r.status_code == 200 else None
            except:
                pass
        
        return None

    def scan_repo(self, owner, repo, path="", depth=0):
        """Recursively scan repo for target files."""
        if depth > 3:
            return
        
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        resp = requests.get(url, headers=self.headers)
        
        if resp.status_code != 200:
            return
        
        items = resp.json()
        if not isinstance(items, list):
            return
        
        for item in items:
            if item["type"] == "file":
                if any(item["name"].lower().endswith(ext) for ext in self.extensions):
                    if item.get("size", 0) > 10_000_000:
                        continue
                    
                    content = self.get_file_bytes(owner, repo, item["path"])
                    if content:
                        md5 = hashlib.md5(content).hexdigest()
                        if md5 not in self.seen_hashes:
                            self.seen_hashes.add(md5)
                            print(f"{md5}  {owner}/{repo}/{item['path']}", flush=True)
                    
                    time.sleep(0.5)
            
            elif item["type"] == "dir" and item["name"] not in ['.git', 'node_modules']:
                self.scan_repo(owner, repo, item["path"], depth + 1)

    def scan_releases(self, owner, repo):
        """Check release assets for executables."""
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        resp = requests.get(url, headers=self.headers)
        
        if resp.status_code != 200:
            return
        
        for release in resp.json()[:3]:
            for asset in release.get("assets", []):
                if any(asset["name"].lower().endswith(ext) for ext in self.extensions):
                    if asset.get("size", 0) > 50_000_000:
                        continue
                    
                    try:
                        r = requests.get(asset["browser_download_url"], timeout=60)
                        if r.status_code == 200:
                            md5 = hashlib.md5(r.content).hexdigest()
                            if md5 not in self.seen_hashes:
                                self.seen_hashes.add(md5)
                                print(f"{md5}  {owner}/{repo}/releases/{asset['name']}", flush=True)
                    except:
                        pass
                    
                    time.sleep(0.5)

    def run(self):
        print("# Mouse Jiggler MD5 Hashes", flush=True)
        print("# Format: MD5  source", flush=True)
        print("#" + "=" * 50, flush=True)
        
        for term in self.search_terms:
            print(f"# Searching: {term}", flush=True)
            repos = self.search_repos(term)
            
            for repo in repos:
                repo_id = repo["id"]
                if repo_id in self.seen_repos:
                    continue
                self.seen_repos.add(repo_id)
                
                owner = repo["owner"]["login"]
                name = repo["name"]
                
                self.scan_repo(owner, name)
                self.scan_releases(owner, name)
                
                time.sleep(1)
        
        print(f"#\n# Total unique hashes: {len(self.seen_hashes)}", flush=True)


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    hasher = JigglerHasher(token)
    hasher.run()
