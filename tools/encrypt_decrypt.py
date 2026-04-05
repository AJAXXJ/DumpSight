import base64
import hashlib
from cryptography.fernet import Fernet

def generate_key_from_string(input_string):
    hashed = hashlib.sha256(input_string.encode()).digest()
    key = base64.urlsafe_b64encode(hashed[:32])
    return key


def encrypt(text, encryption_key):
    key = generate_key_from_string(encryption_key)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(text.encode())
    return encrypted


def decrypt(encrypted, encryption_key):
    key = generate_key_from_string(encryption_key)
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted).decode()
    return decrypted
