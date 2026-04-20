from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from fastapi import Request
from fastapi.responses import Response
from config import settings

_signer = TimestampSigner(settings.secret_key)
_COOKIE = "mc_session"
_MAX_AGE = 86400 * 7  # 7 jours


def check_password(password: str) -> bool:
    return password == settings.admin_password


def create_session(response: Response) -> None:
    token = _signer.sign(b"admin").decode()
    response.set_cookie(_COOKIE, token, httponly=True, samesite="lax", max_age=_MAX_AGE)


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(_COOKIE)
    if not token:
        return False
    try:
        _signer.unsign(token.encode(), max_age=_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False
