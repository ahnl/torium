"""
HMAC-SHA512 request signing for the Tori.fi API.

This module implements the signature scheme required by the Tori.fi
API gateway. The signing parameters below are compatibility values
necessary to establish interoperability with the service, in
accordance with the principles set out in Directive 2009/24/EC
Article 6 on decompilation for interoperability purposes.

Message format: {METHOD};{path}{?query};{finn-gw-service};{body bytes}
"""

import base64
import codecs
import hashlib
import hmac

_SIGNING_KEY = base64.b64decode(codecs.decode(
    "Z2V1ZmIzZmLgAmyvMF00ZwEvYJR2MzDgZGR2LmMyAwyzZGZ3", "rot13"
))


def gw_key(
    method: str,
    path: str,
    service: str = "",
    body: bytes = b"",
    query: str = "",
) -> str:
    """
    Compute the finn-gw-key header value for a request.

    Args:
        method:   HTTP method, e.g. "GET", "POST"
        path:     URL path without query string, e.g. "/public/users/123/messages"
                  Pass "" or "/" for root (treated as empty).
        service:  Value of the finn-gw-service header, e.g. "MESSAGING-API"
        body:     Raw request body bytes. Pass b"" for GET/DELETE.
        query:    Raw query string WITHOUT leading "?", e.g. "limit=20&offset=0"
    """
    if path == "/":
        path = ""

    query_part = ("?" + query) if query else ""
    prefix = f"{method.upper()};{path}{query_part};{service};"
    message = prefix.encode("utf-8") + body

    sig = hmac.new(_SIGNING_KEY, message, hashlib.sha512).digest()
    return base64.b64encode(sig).decode("ascii")


if __name__ == "__main__":
    result = gw_key(
        method="GET",
        path="/public/users/697554341/unreadmessagecount",
        service="MESSAGING-API",
    )
    expected = "bbAqA7PQNmE6YbhPHwTmhasqW/n2rXnHl+f2UTJjxQWcIDynRvYR2sDCBxDpWgJkTfVfPOkbjzVR78rnn/1ojg=="
    print("PASS" if result == expected else f"FAIL\n  got:      {result}\n  expected: {expected}")
