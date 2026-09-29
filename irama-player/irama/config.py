"""Global configuration constants for Irama Nusantara CLI."""

import os

API_BASE_URL = os.getenv("IRAMA_API_BASE", "https://core.iramanusantara.org/api/records")
WEB_REFERER = "https://www.iramanusantara.org/"
DEFAULT_USER_AGENT = os.getenv(
    "IRAMA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# TTFB on Irama Nusantara Strapi is notoriously slow (~9s)
CONNECT_TIMEOUT = int(os.getenv("IRAMA_CONNECT_TIMEOUT", "10"))
READ_TIMEOUT = int(os.getenv("IRAMA_READ_TIMEOUT", "30"))
REQUEST_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

DEFAULT_DOWNLOAD_DIR = os.getenv("IRAMA_DOWNLOAD_DIR", "./downloads")
