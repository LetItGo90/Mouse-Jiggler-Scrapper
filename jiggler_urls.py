#!/usr/bin/env python3
"""
Mouse Jiggler Repo Finder
Finds repos containing mouse jigglers across multiple platforms
"""

import requests
import time
import os

class JigglerFinder:
    def __init__(self, github_token=None):
        self.github_headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            self.github_headers["Authorization"] = f"token {github_token}"
        
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
        
        self.exclude_keywords = [
            "owasp",
            "security-list",
            "awesome-",
            "cheatsheet",
        ]
        
        self.seen_urls = set()

    def is_excluded(self, url):
        url_lower = url.lower()
        for keyword in self.exclude_keywords:
            if keyword in url_lower:
                return True
        return False

    def add_url(self, url):
        if url in self.seen_urls:
            return
        if self.is_excluded(url):
            return
        self.seen_urls.add(url)
        print(url, flush=True)

    # GitHub
    def search_github(self, query, max_results=10):
        url = "https://api.github.com/search/repositories"
        params = {"q": query, "sort": "stars", "per_page": max_results}
        
        try:
            resp = requests.get(url, headers=self.github_headers, params=params, timeout=10)
            if resp.status_code == 403:
                time.sleep(60)
                resp = requests.get(url, headers=self.github_headers, params=params, timeout=10)
            if resp.status_code != 200:
                return []
            return resp.json().get("items", [])
        except:
            return []

    # GitLab
    def search_gitlab(self, query, max_results=10):
        url = "https://gitlab.com/api/v4/projects"
        params = {"search": query, "per_page": max_results}
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return []
            return resp.json()
        except:
            return []

    # SourceForge
    def search_sourceforge(self, query, max_results=10):
        url = "https://sourceforge.net/api/search"
        params = {"q": query, "format": "json", "limit": max_results}
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return []
            return resp.json().get("items", [])
        except:
            return []

    # Codeberg (Gitea-based, similar to GitHub)
    def search_codeberg(self, query, max_results=10):
        url = "https://codeberg.org/api/v1/repos/search"
        params = {"q": query, "limit": max_results}
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return []
            return resp.json().get("data", [])
        except:
            return []

    def run(self):
        for term in self.search_terms:
            # GitHub
            for repo in self.search_github(term):
                self.add_url(repo.get("html_url", ""))
            
            # GitLab
            for repo in self.search_gitlab(term):
                self.add_url(repo.get("web_url", ""))
            
            # SourceForge
            for repo in self.search_sourceforge(term):
                url = repo.get("url", "")
                if url:
                    self.add_url(url)
            
            # Codeberg
            for repo in self.search_codeberg(term):
                self.add_url(repo.get("html_url", ""))
            
            time.sleep(3)


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    finder = JigglerFinder(github_token=token)
    finder.run()
