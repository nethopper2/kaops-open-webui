import os
from cryptography.fernet import Fernet
import base64

# It's crucial to manage this key securely.
# For production, fetch from environment variables, a secrets manager, or a KMS.
# DO NOT HARDCODE IN PRODUCTION.
# For local development:
print(Fernet.generate_key().decode()) # Run this once to generate a key
# export ENCRYPTION_KEY='your_generated_key_here'
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if ENCRYPTION_KEY is None:
    raise ValueError("ENCRYPTION_KEY environment variable not set. Please set it securely.")

try:
    _fernet = Fernet(ENCRYPTION_KEY.encode('utf-8'))
except Exception as e:
    raise ValueError(f"Invalid ENCRYPTION_KEY: {e}. Ensure it's a base64-encoded URL-safe string.")


def encrypt_data(data: str) -> bytes:
    """Encrypts a string and returns bytes."""
    return _fernet.encrypt(data.encode('utf-8'))

def decrypt_data(encrypted_data: bytes) -> str:
    """Decrypts bytes and returns a string."""
    return _fernet.decrypt(encrypted_data).decode('utf-8')

# Example usage for generating a key:
# if __name__ == "__main__":
#     key = Fernet.generate_key()
#     print(key.decode())