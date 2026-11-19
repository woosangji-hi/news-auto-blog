"""공용 유틸: 경로, 설정 로드, URL 정규화, 텍스트 정리."""
from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import sys

import yaml

# Windows(cp949) 콘솔·로그 파일에서도 한글/기호가 깨지지 않도록
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
KST = ZoneInfo("Asia/Seoul")

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "from")


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def settings() -> dict:
    return load_yaml(ROOT / "config" / "settings.yaml")


def norm_url(url: str) -> str:
    """추적 파라미터·프래그먼트를 지우고 비교 가능한 형태로 만든다."""
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    host = parts.netloc.lower()
    if host.startswith("m."):
        host = "www." + host[2:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def url_key(url: str) -> str:
    return hashlib.sha1(norm_url(url).encode("utf-8")).hexdigest()[:16]


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return _WS_RE.sub(" ", text).strip()


def squash(text: str) -> str:
    """공백·문장부호 일부를 제거해 복제 여부 비교용 문자열을 만든다."""
    return re.sub(r"[\s\"'“”‘’·…,.!?()\[\]<>-]", "", text or "")
