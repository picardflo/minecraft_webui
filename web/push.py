import base64
import json

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def generate_vapid_keys() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    # pywebpush expects raw base64url-encoded 32-byte private key
    private_int = key.private_numbers().private_value
    private_raw = private_int.to_bytes(32, "big")
    private_key = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()
    # Uncompressed public key point for the browser
    pub_bytes = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_key = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    return private_key, public_key


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
