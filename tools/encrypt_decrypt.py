import base64
import hashlib
from cryptography.fernet import Fernet


class EncryptionUtil:
    def __init__(self, secret_key: str):
        self._fernet = Fernet(self._derive_key(secret_key))

    @staticmethod
    def _derive_key(secret_key: str) -> bytes:
        hashed = hashlib.sha256(secret_key.encode()).digest()
        return base64.urlsafe_b64encode(hashed[:32])

    def encrypt(self, text: str) -> str:
        return self._fernet.encrypt(text.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        return self._fernet.decrypt(encrypted.encode()).decode()

    @classmethod
    def from_app_config(cls, app_config) -> "EncryptionUtil":
        """从 Flask app.config 中构建"""
        return cls(app_config["SECRET_KEY"])

    @classmethod
    def from_dumpsight_config(cls, config) -> "EncryptionUtil":
        """从 DumpSightConfig 中构建"""
        return cls(config.encryption_key)