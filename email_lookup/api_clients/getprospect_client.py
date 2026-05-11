import requests
from typing import List, Optional

class GetProspectClient:
    BASE_URL = "https://api.getprospect.com/v2"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def search_emails(self, domain: str, position: str = None) -> Optional[List[str]]:
        try:
            params = {"domain": domain}
            if position:
                params["position"] = position
                
            response = requests.get(
                f"{self.BASE_URL}/company/emails",
                params=params,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )
            data = response.json()
            return [e['email'] for e in data.get('data', [])]
        except Exception as e:
            print(f"GetProspect Error: {e}")
            return None