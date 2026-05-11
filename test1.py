import requests

# Test Hunter.io
hunter_key = "ce30cece6b5145208b0a40948921632bc88df32e"
response = requests.get(
    f"https://api.hunter.io/v2/domain-search?domain=stripe.com&api_key={hunter_key}"
)
print(response.json())

# Test GetProspect
getprospect_key = "612dca7b-067b-4bfc-8803-399648b4defd"
response = requests.get(
    "https://api.getprospect.com/v2/company/emails",
    params={"domain": "stripe.com"},
    headers={"Authorization": f"Bearer {getprospect_key}"}
)
print(response.json())