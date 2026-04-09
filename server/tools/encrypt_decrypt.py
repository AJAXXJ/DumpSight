import base64
import hashlib
from flask import current_app
from cryptography.fernet import Fernet

def generate_key_from_string(input_string):
    hashed = hashlib.sha256(input_string.encode()).digest()
    key = base64.urlsafe_b64encode(hashed[:32])
    return key


def encrypt(text):
    SECRET_KEY_STRING = current_app.config["SECRET_KEY"]
    key = generate_key_from_string(SECRET_KEY_STRING)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(text.encode())
    return encrypted


def decrypt(encrypted):
    SECRET_KEY_STRING = current_app.config["SECRET_KEY"]
    key = generate_key_from_string(SECRET_KEY_STRING)
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted).decode()
    return decrypted
