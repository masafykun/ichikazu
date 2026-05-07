import os
import random
import secrets
import string
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import AccessLog, ShortURL

Base.metadata.create_all(bind=engine)

app = FastAPI(title="いちカズ", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="/root/ichikazu/app/static"), name="static")
templates = Jinja2Templates(directory="/root/ichikazu/app/templates")

DOMAIN = "1qaz.jp"
CODE_LENGTH = 6
CHARS = string.ascii_letters + string.digits

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "")

security = HTTPBasic()


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
    for _ in range(10):
        code = "".join(random.choices(CHARS, k=CODE_LENGTH))
        if not db.query(ShortURL).filter(ShortURL.code == code).first():
            return code
    raise RuntimeError("短縮コードの生成に失敗しました")


class ShortenRequest(BaseModel):
    url: str


# ── 一般ページ ────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"domain": DOMAIN})


@app.post("/api/shorten")
async def shorten(body: ShortenRequest, request: Request, db: Session = Depends(get_db)):
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    existing = db.query(ShortURL).filter(ShortURL.original_url == url).first()
    if existing:
        return {"short_url": f"https://{DOMAIN}/{existing.code}", "code": existing.code}

    code = generate_code(db)
    entry = ShortURL(
        code=code,
        original_url=url,
        creator_ip=get_client_ip(request),
        creator_ua=request.headers.get("User-Agent", "")[:512],
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {"short_url": f"https://{DOMAIN}/{entry.code}", "code": entry.code}


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


# ── 管理者ダッシュボード ──────────────────────────────────
# ※ /{code} より先に定義しないとキャッチされてしまう

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


@app.get("/{code}")
async def redirect(code: str, request: Request, db: Session = Depends(get_db)):
    if code in ("favicon.ico", "robots.txt"):
        raise HTTPException(status_code=404)

    entry = db.query(ShortURL).filter(ShortURL.code == code).first()
    if not entry:
        raise HTTPException(status_code=404, detail="短縮URLが見つかりませんでした")

    entry.click_count += 1
    entry.last_accessed_at = datetime.utcnow()

    log = AccessLog(
        short_url_id=entry.id,
        accessed_at=datetime.utcnow(),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:512],
        referer=request.headers.get("Referer", "")[:2048],
    )
    db.add(log)
    db.commit()

    return RedirectResponse(url=entry.original_url, status_code=301)
