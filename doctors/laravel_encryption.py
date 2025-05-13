import base64
import hashlib
import hmac
import json
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


APP_KEY_BASE64 = 'k7jHCfy8Ad+1Bb2/egJtOcDb/qEXd6mbR1FmtGdr0jg='
APP_KEY = base64.b64decode(APP_KEY_BASE64)

def encrypt_laravel_style(plain_text):
    iv = os.urandom(16)
    cipher = AES.new(APP_KEY, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plain_text.encode(), AES.block_size))

    encrypted_base64 = base64.b64encode(encrypted).decode()
    iv_base64 = base64.b64encode(iv).decode()

    payload = {
        'iv': iv_base64,
        'value': encrypted_base64,
        'mac': hmac.new(APP_KEY, (iv_base64 + encrypted_base64).encode(), hashlib.sha256).hexdigest()
    }

    json_payload = json.dumps(payload)
    final_encrypted = base64.b64encode(json_payload.encode()).decode()

    return final_encrypted
