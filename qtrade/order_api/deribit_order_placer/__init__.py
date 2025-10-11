import requests

url = "https://test.deribit.com/api/v2/public/auth"

api_config = {
    "grant_type": "client_credentials",
    "client_id": "Y1Dn2LBT",
    "client_secret": "BNRxchFAqHBFTI6m8tbKsVHbd1Zb-vO__ZFIY3u_lhY"
}

real_api_config = {
    "grant_type": "client_credentials",
    "client_id": "wa_pJwWn",
    "client_secret": "W1o5bS5bm1adFhXBodPZd4BE5JGQJuFCkiYDc41pntA"
}


if __name__ == "__main__":
    resp = requests.get(url, params=api_config).json()
    print(resp)
