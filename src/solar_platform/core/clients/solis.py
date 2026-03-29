"""
Solis / SolisCloud authentication helpers.

Solis API uses HMAC-SHA1 signature-based auth.
API docs: https://www.soliscloud.com/doc

Signature formula:
    Sign = Base64( HMAC-SHA1( apiSecret,
               "POST\\n" + Content-MD5 + "\\napplication/json\\n" + Date + "\\n" + path ) )
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime


BASE_URL = "https://www.soliscloud.com:13333"


def build_auth_headers(api_id: str, api_secret: str, body: str, path: str) -> dict:
    """
    Return the full set of HTTP headers needed to authenticate a Solis API request.

    Args:
        api_id:     Solis API ID (from SolisCloud developer portal).
        api_secret: Solis API Secret.
        body:       JSON-serialised request body (str).
        path:       API path, e.g. '/v1/api/userStationList'.

    Returns:
        dict with keys: Content-Type, Content-MD5, Date, Authorization.
    """
    md5_hash = hashlib.md5(body.encode("utf-8")).digest()
    content_md5 = base64.b64encode(md5_hash).decode("utf-8")

    date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    content_type = "application/json"
    string_to_sign = f"POST\n{content_md5}\n{content_type}\n{date}\n{path}"

    signature = hmac.new(
        api_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    return {
        "Content-Type": content_type,
        "Content-MD5": content_md5,
        "Date": date,
        "Authorization": f"API {api_id}:{signature_b64}",
    }


def build_auth_headers_from_dict(api_id: str, api_secret: str, data: dict, path: str) -> dict:
    """Convenience wrapper that serialises `data` to JSON before signing."""
    return build_auth_headers(api_id, api_secret, json.dumps(data), path)
