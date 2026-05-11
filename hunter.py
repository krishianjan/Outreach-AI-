import requests
from typing import List, Optional
from .key_rotator import KeyRotator

class HunterClient:
    def __init__(self, keys: List[str]):
        self.rotator = KeyRotator(keys)
        self.base_url = "https://api.hunter.io/v2"
        
    def domain_search(self, domain: str) -> Optional[List[str]]:
        """Search for emails using domain search"""
        try:
            response = requests.get(
                f"{self.base_url}/domain-search",
                params={
                    "domain": domain,
                    "api_key": self.rotator.get_key()
                },
                timeout=10
            )
            data = response.json()
            return [e['value'] for e in data.get('data', {}).get('emails', [])]
        except Exception:
            return None

    def email_finder(self, domain: str, first_name: str, last_name: str) -> Optional[str]:
        """Find specific person's email"""
        try:
            response = requests.get(
                f"{self.base_url}/email-finder",
                params={
                    "domain": domain,
                    "first_name": first_name,
                    "last_name": last_name,
                    "api_key": self.rotator.get_key()
                },
                timeout=10
            )
            data = response.json()
            return data.get('data', {}).get('email')
        except Exception:
            return None