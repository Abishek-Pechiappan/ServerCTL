import hashlib
import hmac
import os

# scrypt parameters (stdlib, no external deps). N=2**14/r=8/p=1 is the standard
# "interactive login" cost; it needs ~16 MiB, so we cap maxmem well above that.
_N = 2 ** 14
_R = 8
_P = 1
_DKLEN = 32
_MAXMEM = 64 * 1024 * 1024

# Fields are joined with ":" (not "$"). The hash lands in backend/.env, which
# docker-compose reads with variable interpolation — a "$" would let it eat
# "$16384" etc. as undefined variables and silently truncate the hash, so every
# login would fail. ":" has no special meaning to the interpolator. All fields
# are digits or hex, so ":" is an unambiguous separator.
_SEP = ":"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM
    )
    return _SEP.join(["scrypt", str(_N), str(_R), str(_P), salt.hex(), dk.hex()])


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = encoded.split(_SEP)
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)
