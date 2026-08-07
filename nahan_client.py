"""
کلاینت اتصال به پنل Nahan Gateway — ساخت خودکار کاربر/کانفیگ از داخل ربات.
جای این فایل رو کنار bot_fixed.py بذار و توی بات با:
    from nahan_client import nahan_add_user
ایمپورتش کن.
"""

import os
import time
import uuid
import logging
import requests

logger = logging.getLogger(__name__)

NAHAN_BASE_URL = os.environ.get("NAHAN_BASE_URL", "https://nahan-core.moki1iliya.workers.dev")
NAHAN_API_ROUTE = os.environ.get("NAHAN_API_ROUTE", "sync")
NAHAN_KEY = os.environ.get("NAHAN_API_KEY", "")

_SESSION = requests.Session()
_SESSION.headers.update({"Content-Type": "application/json"})


class NahanError(Exception):
    """خطای مشخص برای شکست تماس با پنل، تا بات بتونه جدا از خطاهای دیگه هندلش کنه."""


def _unique_username(base: str) -> str:
    """چون پنل روی name یکتا حساسه، یه پسوند کوتاه بهش می‌چسبونیم تا تصادم نخوریم."""
    safe_base = "".join(ch for ch in base if ch.isalnum() or ch in ("_", "-")) or "user"
    return f"{safe_base}_{uuid.uuid4().hex[:6]}"


def nahan_add_user(username: str, volume_gb: float = None, days: int = None, retries: int = 2) -> dict:
    """
    یه کاربر جدید روی پنل می‌سازه و دیکشنری نتیجه (شامل subscriptionUrl) رو برمی‌گردونه.
    خطا در ارتباط → NahanError. خطای منطقی پنل (مثل نام تکراری) → NahanError با متن دقیق پنل.
    """
    if not NAHAN_KEY:
        raise NahanError("NAHAN_API_KEY تنظیم نشده — تو Railway/هاست ست کن")

    url = f"{NAHAN_BASE_URL}/{NAHAN_API_ROUTE}/api/users"
    headers = {"Authorization": f"Bearer {NAHAN_KEY}"}

    # 🛠 باگ زمان نامحدود: قبلاً فقط "expiryDays" فرستاده می‌شد و اگه پنل این کلید رو
    # نمی‌شناخت یا مقدارش float/None بود، بی‌سروصدا نادیده گرفته می‌شد و کانفیگ نامحدود می‌موند.
    # برای اطمینان، هم تعداد روز و هم تاریخ انقضا (به میلی‌ثانیه، مطلق) رو با چند اسم رایج
    # می‌فرستیم تا هرکدوم رو پنل بخونه، کار کنه.
    days_int = int(days) if days else None
    expire_ms = int(time.time() * 1000) + days_int * 86400000 if days_int else None
    payload = {
        "name": _unique_username(username),
        "trafficLimit": volume_gb,
        "expiryDays": days_int,
        "days": days_int,
        "expire": expire_ms,
        "expiryMs": expire_ms,
    }

    last_err = None
    for attempt in range(1, retries + 2):
        try:
            resp = _SESSION.post(url, json=payload, headers=headers, timeout=15)
        except requests.exceptions.Timeout:
            last_err = "تایم‌اوت — پنل جواب نداد"
            logger.warning("[NAHAN] timeout, attempt %d", attempt)
            continue
        except requests.exceptions.ConnectionError as e:
            last_err = f"خطا در اتصال به پنل: {e}"
            logger.warning("[NAHAN] connection error, attempt %d: %s", attempt, e)
            continue

        if resp.status_code in (200, 201):
            data = resp.json()
            if not data.get("success"):
                raise NahanError(data.get("error", "خطای نامشخص پنل"))
            # ⚠️ subscriptionUrl هم‌سطح "user" برمی‌گرده، نه داخلش — این‌جا مرجش می‌کنیم
            # تا هر جای دیگه‌ی بات فقط با یه دیکشنری کار کنه.
            user = dict(data.get("user", {}))
            user["subscriptionUrl"] = data.get("subscriptionUrl", "")
            if days_int and not user.get("expiryMs") and not user.get("expire"):
                logger.warning(
                    "[NAHAN] expiry may not have been applied by panel for user %s (requested %s days)",
                    user.get("id"), days_int,
                )
            return user

        if resp.status_code == 401:
            raise NahanError("توکن پنل نامعتبره (Unauthorized) — NAHAN_API_KEY رو چک کن")
        if resp.status_code == 400:
            try:
                err = resp.json().get("error", resp.text[:200])
            except ValueError:
                err = resp.text[:200]
            raise NahanError(f"درخواست نامعتبر: {err}")

        last_err = f"status={resp.status_code} body={resp.text[:200]}"
        logger.warning("[NAHAN] unexpected response, attempt %d: %s", attempt, last_err)

    raise NahanError(last_err or "خطای نامشخص در ارتباط با پنل")


def nahan_get_user(panel_user_id: str) -> dict:
    """
    وضعیت لحظه‌ای یه کاربر رو از پنل می‌گیره: حجم مصرف‌شده، سقف حجم، تاریخ انقضا، وضعیت، لینک اشتراک.
    خروجی بایت‌هاست (usage.total / usage.limit) — تبدیل به گیگ رو خود بات انجام می‌ده.
    """
    if not NAHAN_KEY:
        raise NahanError("NAHAN_API_KEY تنظیم نشده")

    url = f"{NAHAN_BASE_URL}/{NAHAN_API_ROUTE}/api/users"
    headers = {"Authorization": f"Bearer {NAHAN_KEY}"}
    try:
        resp = _SESSION.get(url, headers=headers, params={"id": panel_user_id}, timeout=15)
    except requests.exceptions.Timeout:
        raise NahanError("تایم‌اوت — پنل جواب نداد")
    except requests.exceptions.ConnectionError as e:
        raise NahanError(f"خطا در اتصال به پنل: {e}")

    if resp.status_code == 404:
        raise NahanError("این کاربر رو پنل پیدا نشد (شاید حذف شده)")
    if resp.status_code == 401:
        raise NahanError("توکن پنل نامعتبره (Unauthorized)")
    if resp.status_code != 200:
        raise NahanError(f"status={resp.status_code} body={resp.text[:200]}")

    data = resp.json()
    if not data.get("success"):
        raise NahanError(data.get("error", "خطای نامشخص پنل"))
    return data["user"]



    """حذف کاربر از پنل (برای لغو/بازگشت وجه). خطا رو می‌بلعه و False برمی‌گردونه، چون این معمولاً یه best-effort cleanup هست."""
    if not NAHAN_KEY:
        return False
    url = f"{NAHAN_BASE_URL}/{NAHAN_API_ROUTE}/api/users/{user_id}"
    headers = {"Authorization": f"Bearer {NAHAN_KEY}"}
    try:
        resp = _SESSION.delete(url, headers=headers, timeout=15)
        return resp.status_code in (200, 204)
    except requests.exceptions.RequestException as e:
        logger.warning("[NAHAN] delete failed for %s: %s", user_id, e)
        return False
