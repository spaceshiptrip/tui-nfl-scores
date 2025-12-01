#!/usr/bin/env python3
import requests

URL = "https://www.footballdb.com/data/gamescores.php"

HEADERS_API = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.footballdb.com/",
    "X-Requested-With": "XMLHttpRequest",
}

def main():
    resp = requests.get(URL, headers=HEADERS_API, timeout=10)
    resp.raise_for_status()
    print(resp.text)          # raw payload
    # or if it's valid JSON and you want it pretty:
    # import json
    # data = resp.json()
    # print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
