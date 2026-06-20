import io
import os
import random
import re
import secrets
import string
from datetime import datetime, timedelta

import qrcode
import qrcode.image.svg
import stripe as stripe_sdk
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import (
    get_current_user,
    get_optional_user,
    hash_password,
    is_pro,
    make_token,
    new_api_key,
    verify_password,
)
from .database import Base, engine, get_db, run_migrations
from .models import AccessLog, ShortURL, StripeEvent, User

Base.metadata.create_all(bind=engine)
run_migrations()

app = FastAPI(title="いちカズ", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="/root/ichikazu/app/static"), name="static")
templates = Jinja2Templates(directory="/root/ichikazu/app/templates")

DOMAIN = "1qaz.jp"
CODE_LENGTH = 6
CHARS = string.ascii_letters + string.digits

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

APP_URL = os.getenv("APP_URL", "https://1qaz.jp")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
if STRIPE_SECRET_KEY:
    stripe_sdk.api_key = STRIPE_SECRET_KEY

security = HTTPBasic()

# カスタムslugで使えない予約語（アプリのパス/紛らわしいもの）
RESERVED = {
    "api", "admin", "stats", "static", "dashboard", "pricing", "terms",
    "privacy", "tokushoho", "webhook", "qr", "login", "register", "logout",
    "me", "health", "www", "favicon.ico", "robots.txt", ".well-known",
    "billing", "account", "settings", "help", "about", "contact",
}
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# ── ヘルパー ──────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="認証に失敗しました",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def generate_code(db: Session) -> str:
    for _ in range(12):
        code = "".join(random.choices(CHARS, k=CODE_LENGTH))
        if not db.query(ShortURL).filter(ShortURL.code == code).first():
            return code
    raise RuntimeError("短縮コードの生成に失敗しました")


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def user_dict(u: User) -> dict:
    d = {"id": u.id, "email": u.email, "plan": u.plan}
    if u.plan == "pro":
        d["api_key"] = u.api_key
    return d


def url_dict(u: ShortURL) -> dict:
    return {
        "code": u.code,
        "short_url": f"https://{DOMAIN}/{u.code}",
        "original_url": u.original_url,
        "title": u.title,
        "click_count": u.click_count,
        "is_custom": bool(u.is_custom),
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_accessed_at": u.last_accessed_at.isoformat() if u.last_accessed_at else None,
        "expires_at": u.expires_at.isoformat() if u.expires_at else None,
    }


def qr_svg(data: str) -> bytes:
    qr = qrcode.QRCode(box_size=12, border=2, image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image()
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


def create_short(db, request, url, user, slug, title, expires_days):
    """短縮URLを作成。slug/title/expires は Pro 限定。"""
    url = normalize_url(url)
    wants_pro = bool(slug or title or expires_days)
    if wants_pro:
        if not user:
            raise HTTPException(status_code=401, detail="この機能はログインが必要です")
        if not is_pro(user):
            raise HTTPException(status_code=403, detail="カスタムslug・タイトル・有効期限は Pro プラン限定です")

    if slug:
        slug = slug.strip()
        if not SLUG_RE.match(slug):
            raise HTTPException(status_code=400, detail="slugは半角英数字・ハイフン・アンダースコア3〜32文字にしてください")
        if slug.lower() in RESERVED:
            raise HTTPException(status_code=400, detail="そのslugは予約語のため使用できません")
        if db.query(ShortURL).filter(ShortURL.code == slug).first():
            raise HTTPException(status_code=409, detail="そのslugは既に使われています")
        code = slug
        is_custom = True
    else:
        # 匿名・非カスタムは従来どおり「同じURLは同じコード」を維持（匿名リンク内で重複排除）
        if not user and not wants_pro:
            existing = (
                db.query(ShortURL)
                .filter(ShortURL.original_url == url, ShortURL.user_id.is_(None), ShortURL.is_custom == False)  # noqa: E712
                .first()
            )
            if existing:
                return existing
        code = generate_code(db)
        is_custom = False

    expires_at = None
    if expires_days:
        try:
            days = int(expires_days)
            if days > 0:
                expires_at = datetime.utcnow() + timedelta(days=days)
        except (TypeError, ValueError):
            expires_at = None

    entry = ShortURL(
        code=code,
        original_url=url,
        creator_ip=get_client_ip(request),
        creator_ua=request.headers.get("User-Agent", "")[:512],
        user_id=user.id if user else None,
        title=(title.strip()[:255] if title else None),
        is_custom=is_custom,
        expires_at=expires_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ── Pydantic ─────────────────────────────────────────────

class ShortenRequest(BaseModel):
    url: str
    slug: str | None = None
    title: str | None = None
    expires_days: int | None = None


class AuthRequest(BaseModel):
    email: str
    password: str


class UpdateLinkRequest(BaseModel):
    original_url: str | None = None
    title: str | None = None
    expires_days: int | None = None


# ── 一般ページ ────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"domain": DOMAIN})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"domain": DOMAIN})


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {"domain": DOMAIN})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {"domain": DOMAIN})


@app.get("/tokushoho", response_class=HTMLResponse)
async def tokushoho(request: Request):
    return templates.TemplateResponse(request, "tokushoho.html", {"domain": DOMAIN})


# ── 短縮API（匿名OK、Pro機能はゲート） ─────────────────────

@app.post("/api/shorten")
async def shorten(
    body: ShortenRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URLを入力してください")
    entry = create_short(db, request, url, user, body.slug, body.title, body.expires_days)
    return {"short_url": f"https://{DOMAIN}/{entry.code}", "code": entry.code}


# ── 認証 ──────────────────────────────────────────────────

@app.post("/api/auth/register")
async def register(body: AuthRequest, db: Session = Depends(get_db)):
    email = (body.email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="メールアドレスの形式が正しくありません")
    if len(body.password or "") < 8:
        raise HTTPException(status_code=400, detail="パスワードは8文字以上にしてください")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="このメールアドレスは既に登録されています")
    u = User(email=email, password=hash_password(body.password), plan="free")
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"token": make_token(u), "user": user_dict(u)}


@app.post("/api/auth/login")
async def login(body: AuthRequest, db: Session = Depends(get_db)):
    email = (body.email or "").strip().lower()
    u = db.query(User).filter(User.email == email).first()
    if not u or not verify_password(body.password or "", u.password):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが正しくありません")
    return {"token": make_token(u), "user": user_dict(u)}


@app.get("/api/auth/me")
async def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.plan == "pro" and not user.api_key:
        user.api_key = new_api_key()
        db.commit()
        db.refresh(user)
    return user_dict(user)


# ── リンク管理（自分のリンク） ─────────────────────────────

@app.get("/api/links")
async def my_links(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    urls = (
        db.query(ShortURL)
        .filter(ShortURL.user_id == user.id)
        .order_by(ShortURL.created_at.desc())
        .all()
    )
    return {"plan": user.plan, "links": [url_dict(u) for u in urls]}


@app.patch("/api/links/{code}")
async def update_link(
    code: str,
    body: UpdateLinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_pro(user):
        raise HTTPException(status_code=403, detail="リンクの編集は Pro プラン限定です")
    entry = db.query(ShortURL).filter(ShortURL.code == code, ShortURL.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="リンクが見つかりません")
    if body.original_url is not None and body.original_url.strip():
        entry.original_url = normalize_url(body.original_url)
    if body.title is not None:
        entry.title = body.title.strip()[:255] or None
    if body.expires_days is not None:
        if body.expires_days and int(body.expires_days) > 0:
            entry.expires_at = datetime.utcnow() + timedelta(days=int(body.expires_days))
        else:
            entry.expires_at = None
    db.commit()
    db.refresh(entry)
    return url_dict(entry)


@app.delete("/api/links/{code}")
async def delete_link(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = db.query(ShortURL).filter(ShortURL.code == code, ShortURL.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="リンクが見つかりません")
    db.delete(entry)
    db.commit()
    return {"deleted": True}


@app.get("/api/links/{code}/logs")
async def link_logs(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not is_pro(user):
        raise HTTPException(status_code=403, detail="詳細解析は Pro プラン限定です")
    entry = db.query(ShortURL).filter(ShortURL.code == code, ShortURL.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="リンクが見つかりません")
    logs = (
        db.query(AccessLog)
        .filter(AccessLog.short_url_id == entry.id)
        .order_by(AccessLog.accessed_at.desc())
        .limit(200)
        .all()
    )
    return {
        "code": entry.code,
        "click_count": entry.click_count,
        "logs": [
            {
                "accessed_at": log.accessed_at.isoformat() if log.accessed_at else None,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "referer": log.referer,
            }
            for log in logs
        ],
    }


# ── QRコード（短縮URLのSVG） ───────────────────────────────

@app.get("/qr/{code}")
async def qr(code: str, db: Session = Depends(get_db)):
    entry = db.query(ShortURL).filter(ShortURL.code == code).first()
    if not entry:
        raise HTTPException(status_code=404, detail="短縮URLが見つかりません")
    svg = qr_svg(f"https://{DOMAIN}/{entry.code}")
    return Response(content=svg, media_type="image/svg+xml")


# ── API v1（Proのapi_keyで叩く） ───────────────────────────

@app.post("/api/v1/shorten")
async def api_v1_shorten(
    body: ShortenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    key = request.headers.get("X-API-Key", "")
    user = db.query(User).filter(User.api_key == key).first() if key else None
    if not user or not is_pro(user):
        raise HTTPException(status_code=401, detail="有効なAPIキーが必要です（Proプラン）")
    if not (body.url or "").strip():
        raise HTTPException(status_code=400, detail="urlは必須です")
    entry = create_short(db, request, body.url, user, body.slug, body.title, body.expires_days)
    return {"short_url": f"https://{DOMAIN}/{entry.code}", "code": entry.code}


# ── 決済（Stripe） ────────────────────────────────────────

@app.post("/api/billing/checkout")
async def billing_checkout(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_PRO:
        raise HTTPException(status_code=503, detail="決済機能は現在準備中です")
    if is_pro(user):
        raise HTTPException(status_code=400, detail="すでにProプランをご利用中です")
    params = {
        "mode": "subscription",
        "line_items": [{"price": STRIPE_PRICE_PRO, "quantity": 1}],
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id)},
        "subscription_data": {"metadata": {"user_id": str(user.id)}},
        "success_url": f"{APP_URL}/dashboard?upgrade=success",
        "cancel_url": f"{APP_URL}/dashboard?upgrade=cancel",
        "allow_promotion_codes": True,
    }
    if user.stripe_customer_id:
        params["customer"] = user.stripe_customer_id
    else:
        params["customer_email"] = user.email
    try:
        session = stripe_sdk.checkout.Session.create(**params)
        return {"url": session.url}
    except Exception:
        raise HTTPException(status_code=500, detail="決済セッションの作成に失敗しました")


@app.post("/api/billing/portal")
async def billing_portal(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="決済機能は現在準備中です")
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="有効なサブスクリプションが見つかりません")
    try:
        session = stripe_sdk.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{APP_URL}/dashboard",
        )
        return {"url": session.url}
    except Exception:
        raise HTTPException(status_code=500, detail="ポータルの作成に失敗しました")


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_sdk.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook Error: {e}")

    # stripe 15.x の StripeObject は .get() を持たない → subscript+try で安全に取得
    def sg(o, key, default=None):
        try:
            v = o[key]
        except Exception:
            return default
        return v if v is not None else default

    if db.query(StripeEvent).filter(StripeEvent.id == event["id"]).first():
        return {"received": True, "duplicate": True}
    db.add(StripeEvent(id=event["id"], type=event["type"]))
    db.commit()

    etype = event["type"]
    obj = event["data"]["object"]
    try:
        if etype == "checkout.session.completed":
            md = sg(obj, "metadata")
            user_id = sg(obj, "client_reference_id") or (sg(md, "user_id") if md is not None else None)
            if user_id:
                u = db.query(User).filter(User.id == int(user_id)).first()
                if u:
                    u.plan = "pro"
                    u.stripe_customer_id = sg(obj, "customer")
                    u.stripe_subscription_id = sg(obj, "subscription")
                    if not u.api_key:
                        u.api_key = new_api_key()
                    db.commit()
        elif etype == "customer.subscription.updated":
            customer = sg(obj, "customer")
            status = sg(obj, "status")
            u = db.query(User).filter(User.stripe_customer_id == customer).first()
            if u:
                if status in ("active", "trialing"):
                    u.plan = "pro"
                    u.stripe_subscription_id = sg(obj, "id")
                    if not u.api_key:
                        u.api_key = new_api_key()
                elif status in ("canceled", "unpaid", "incomplete_expired"):
                    u.plan = "free"
                db.commit()
        elif etype == "customer.subscription.deleted":
            customer = sg(obj, "customer")
            u = db.query(User).filter(User.stripe_customer_id == customer).first()
            if u:
                u.plan = "free"
                db.commit()
    except Exception:
        db.rollback()
    return {"received": True}


# ── 統計（公開） ──────────────────────────────────────────

@app.get("/stats/{code}", response_class=HTMLResponse)
async def stats(request: Request, code: str, db: Session = Depends(get_db)):
    entry = db.query(ShortURL).filter(ShortURL.code == code).first()
    if not entry:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "該当する短縮URLが見つかりませんでした。"},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "stats.html",
        {"domain": DOMAIN, "entry": entry},
    )


# ── 管理者ダッシュボード（Basic認証） ──────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    urls = db.query(ShortURL).order_by(ShortURL.created_at.desc()).all()
    total_clicks = sum(u.click_count for u in urls)
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "domain": DOMAIN,
            "urls": urls,
            "total_urls": len(urls),
            "total_clicks": total_clicks,
        },
    )


@app.get("/admin/url/{code}", response_class=HTMLResponse)
async def admin_url_detail(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    entry = db.query(ShortURL).filter(ShortURL.code == code).first()
    if not entry:
        raise HTTPException(status_code=404, detail="URLが見つかりません")

    logs = (
        db.query(AccessLog)
        .filter(AccessLog.short_url_id == entry.id)
        .order_by(AccessLog.accessed_at.desc())
        .limit(500)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin_detail.html",
        {
            "domain": DOMAIN,
            "entry": entry,
            "logs": logs,
        },
    )


# ── リダイレクト（必ず最後に定義） ─────────────────────────

@app.get("/{code}")
async def redirect(code: str, request: Request, db: Session = Depends(get_db)):
    if code in ("favicon.ico", "robots.txt"):
        raise HTTPException(status_code=404)

    entry = db.query(ShortURL).filter(ShortURL.code == code).first()
    if not entry:
        raise HTTPException(status_code=404, detail="短縮URLが見つかりませんでした")

    if entry.expires_at and entry.expires_at < datetime.utcnow():
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "このリンクは有効期限が切れています。"},
            status_code=410,
        )

    entry.click_count += 1
    entry.last_accessed_at = datetime.utcnow()
    db.add(
        AccessLog(
            short_url_id=entry.id,
            accessed_at=datetime.utcnow(),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:512],
            referer=request.headers.get("Referer", "")[:2048],
        )
    )
    db.commit()

    return RedirectResponse(url=entry.original_url, status_code=302)
