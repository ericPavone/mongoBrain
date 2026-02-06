"""Shared MongoDB connection, JSON encoder, and text-search helpers."""

import json
import os
from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient


def get_client() -> MongoClient:
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    kwargs: dict = {}

    ca = os.environ.get("MONGODB_TLS_CA_FILE")
    cert = os.environ.get("MONGODB_TLS_CERT_KEY_FILE")
    allow_invalid = os.environ.get("MONGODB_TLS_ALLOW_INVALID_CERTS", "false").lower() == "true"

    if "+srv" in uri and not ca:
        try:
            import certifi
            ca = certifi.where()
        except ImportError:
            pass

    if ca:
        kwargs["tls"] = True
        kwargs["tlsCAFile"] = ca
    if cert:
        kwargs["tls"] = True
        kwargs["tlsCertificateKeyFile"] = cert
    if allow_invalid:
        kwargs["tls"] = True
        kwargs["tlsAllowInvalidCertificates"] = True

    return MongoClient(uri, **kwargs)


def get_db():
    return get_client()[os.environ.get("MONGODB_DB", "openclaw_memory")]


class MongoEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def dump(obj):
    print(json.dumps(obj, cls=MongoEncoder, ensure_ascii=False, indent=2))


def dump_error(msg: str, **extra):
    dump({"error": msg, **extra})


def text_search_query(term: str) -> dict:
    return {"$text": {"$search": term}}


_TEXT_SCORE = {"$meta": "textScore"}
TEXT_SCORE_PROJ = {"score": _TEXT_SCORE}
TEXT_SCORE_SORT = [("score", _TEXT_SCORE)]
