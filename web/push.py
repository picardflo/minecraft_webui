import base64
import json

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def generate_vapid_keys() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_int = key.private_numbers().private_value
    private_raw = private_int.to_bytes(32, "big")
    private_key = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()
    pub_bytes = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    public_key = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    return private_key, public_key


def send_push(sub: dict, title: str, body: str, vapid_private: str) -> bool:
    """Returns True if push succeeded, False if subscription should be removed."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=vapid_private,
            vapid_claims={"sub": "mailto:admin@localhost"},
        )
        print(f"[push] OK → {sub['endpoint'][:60]}...")
        return True
    except WebPushException as e:
        print(f"[push] {e}")
        # 410 Gone ou 404 = subscription expirée, à supprimer
        if e.response is not None and e.response.status_code in (404, 410):
            return False
        return True  # autre erreur (403, réseau…) : on garde la sub
    except Exception as e:
        print(f"[push] {e}")
        return True
