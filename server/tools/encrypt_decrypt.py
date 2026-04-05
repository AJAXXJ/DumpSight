import base64
import hashlib
from main import app
from cryptography.fernet import Fernet

SECRET_KEY_STRING = app.config["SECRET_KEY"]

def generate_key_from_string(input_string):
    hashed = hashlib.sha256(input_string.encode()).digest()
    key = base64.urlsafe_b64encode(hashed[:32])
    return key


def encrypt(text):
    key = generate_key_from_string(SECRET_KEY_STRING)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(text.encode())
    return encrypted


def decrypt(encrypted):
    key = generate_key_from_string(SECRET_KEY_STRING)
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted).decode()
    return decrypted
