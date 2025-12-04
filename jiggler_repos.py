#!/usr/bin/env python3
"""
Mouse Jiggler Repo Finder
Finds GitHub repos containing mouse jigglers
"""

import requests
import time
import os

class JigglerFinder:
    def __init__(self, token=None):
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"
        
        self.search_terms = [
            "mouse jiggler",
            "mouse mover",
            "mouse wiggler",
            "jiggle mouse",
            "wiggle mouse",
            "mouse shaker",
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
            "caffeine mouse",
            "nosleep mouse",
            "insomnia mouse",
            "stay awake pc",
            "dont sleep",
            "no sleep app",
            "awake tool",
            "teams status active",
            "slack status green",
            "keep teams active",
            "teams away prevent",
            "zoom presence",
            "teams green dot",
            "slack away prevent",
            "wfh mouse",
            "remote work mouse",
            "auto move mouse",
            "automatic mouse movement",
            "simulate mouse movement",
            "fake mouse input",
            "mouse automation idle",
            "cursor mover",
            "move cursor automatically",
            "random mouse movement",
            "usb mouse jiggler",
            "pico jiggler",
            "arduino mouse mover",
            "teensy mouse",
            "digispark mouse",
            "attiny85 mouse",
            "raspberry pi mouse jiggler",
            "esp32 mouse",
            "hid mouse emulator",
            "move mouse python",
            "pyautogui idle",
            "autohotkey mouse move",
            "powershell mouse move",
            "keep pc awake",
            "prevent computer sleep",
            "stop screensaver",
            "disable screen lock"
        ]
        
        # Skip repos containing these keywords
        self.exclude_keywords = [
            "owasp",
            "security-list",
            "awesome-",
            "cheatsheet",
        ]
        
        self.seen_repos = set()

    def is_excluded(self, repo_url):
        repo_url_lower = repo_url.lower()
        for keyword in self.exclude_keywords:
            if keyword in repo_url_lower:
                return True
        return False

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

    def run(self):
        print("# Mouse Jiggler Repos", flush=True)
        print("#" + "=" * 50, flush=True)
        
        for term in self.search_terms:
            print(f"# Searching: {term}", flush=True)
            repos = self.search_repos(term)
            
            for repo in repos:
                repo_id = repo["id"]
                repo_url = repo["html_url"]
                
                if repo_id in self.seen_repos:
                    continue
                if self.is_excluded(repo_url):
                    continue
                    
                self.seen_repos.add(repo_id)
                print(repo_url, flush=True)
                
            time.sleep(3)
        
        print(f"#\n# Total unique repos: {len(self.seen_repos)}", flush=True)


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    finder = JigglerFinder(token)
    finder.run()
