"""Versnelt de tests: goedkope wachtwoord-hash. Alleen voor tests, nooit in productie."""
import functools
import werkzeug.security as _security

_orig_generate = _security.generate_password_hash


@functools.wraps(_orig_generate)
def _fast_generate(password, method="pbkdf2:sha256:1", salt_length=16):
    return _orig_generate(password, method=method, salt_length=salt_length)


_security.generate_password_hash = _fast_generate
