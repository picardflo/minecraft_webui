import base64
import json

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)


def generate_vapid_keys() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode()
    pub_bytes = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_key = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    return private_pem, public_key


def send_push(sub: dict, title: str, body: str, vapid_private: str) -> None:
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=vapid_private,
            vapid_claims={"sub": "mailto:admin@localhost"},
        )
    except WebPushException as e:
        print(f"[push] {e}")
    except Exception as e:
        print(f"[push] {e}")
