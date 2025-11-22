import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document
from schemas import (
    User as UserSchema,
    Product as ProductSchema,
    Click as ClickSchema,
    Order as OrderSchema,
    AdminSetting as AdminSettingSchema,
    Subscription as SubscriptionSchema,
)
import hashlib

app = FastAPI(title="Shopearn Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def strip_password(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = {**doc}
    doc.pop("password_hash", None)
    doc["_id"] = str(doc["_id"]) if "_id" in doc else None
    return doc


# Root and health
@app.get("/")
def read_root():
    return {"app": "Shopearn Pro API", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Auth models
class SignupIn(BaseModel):
    name: str
    email: str
    password: str
    role: Optional[str] = "buyer"  # buyer | affiliate
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/auth/signup")
def signup(payload: SignupIn):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Account exists — please login instead.")

    user = UserSchema(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role if payload.role in {"buyer", "affiliate"} else "buyer",
        phone=payload.phone,
        age=payload.age,
        gender=payload.gender,
    )
    uid = create_document("user", user)
    created = db["user"].find_one({"_id": ObjectId(uid)})
    return {"user": strip_password(created)}


@app.post("/auth/login")
def login(payload: LoginIn):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"user": strip_password(user)}


# Users
class UserUpdateIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    ad_free: Optional[bool] = None


@app.put("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdateIn):
    to_set = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not to_set:
        return {"user": strip_password(db["user"].find_one({"_id": oid(user_id)}))}
    to_set["updated_at"] = datetime.now(timezone.utc)
    res = db["user"].update_one({"_id": oid(user_id)}, {"$set": to_set})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    user = db["user"].find_one({"_id": oid(user_id)})
    return {"user": strip_password(user)}


@app.get("/users")
def list_users(role: Optional[str] = None, email: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if role:
        filt["role"] = role
    if email:
        filt["email"] = {"$regex": email, "$options": "i"}
    users = list(db["user"].find(filt).sort("created_at", -1))
    return {"items": [strip_password(u) for u in users]}


# Products
@app.get("/products")
def list_products(q: Optional[str] = Query(None), category: Optional[str] = None, vendor: Optional[str] = None, hot_only: bool = False, affiliate_id: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if q:
        filt["title"] = {"$regex": q, "$options": "i"}
    if category:
        filt["category"] = {"$regex": f"^{category}$", "$options": "i"}
    if vendor:
        filt["vendor"] = {"$regex": f"^{vendor}$", "$options": "i"}
    if affiliate_id:
        filt["affiliate_id"] = affiliate_id
    if hot_only:
        now = datetime.now(timezone.utc)
        filt["hot_deal"] = True
        filt["$or"] = [{"hot_deal_expires_at": None}, {"hot_deal_expires_at": {"$gt": now}}]

    items = list(db["product"].find(filt).sort("updated_at", -1))
    for it in items:
        it["_id"] = str(it["_id"]) 
    return {"items": items}


class ProductIn(BaseModel):
    affiliate_id: str
    title: str
    description: Optional[str] = None
    price: float
    margin: Optional[float] = None
    images: List[str] = []
    vendor: str
    affiliate_link: str
    category: Optional[str] = None
    tags: List[str] = []
    rating: float = 0
    hot_deal: bool = False
    hot_deal_expires_at: Optional[datetime] = None


@app.post("/products")
def create_product(payload: ProductIn):
    prod = ProductSchema(**payload.model_dump())
    pid = create_document("product", prod)
    created = db["product"].find_one({"_id": ObjectId(pid)})
    created["_id"] = str(created["_id"])
    return created


@app.get("/products/{product_id}")
def get_product(product_id: str):
    doc = db["product"].find_one({"_id": oid(product_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    doc["_id"] = str(doc["_id"])
    return doc


@app.put("/products/{product_id}")
def update_product(product_id: str, payload: Dict[str, Any]):
    payload.pop("_id", None)
    payload["updated_at"] = datetime.now(timezone.utc)
    res = db["product"].update_one({"_id": oid(product_id)}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return get_product(product_id)


@app.delete("/products/{product_id}")
def delete_product(product_id: str):
    res = db["product"].delete_one({"_id": oid(product_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


# Click tracking and redirects
@app.get("/r/{vendor}")
async def redirect_vendor(vendor: str, request: Request, user_id: Optional[str] = None):
    settings = db["adminsetting"].find_one({})
    url = None
    if settings and vendor in settings:
        url = settings.get(vendor)
    if not url:
        raise HTTPException(status_code=404, detail="Link not available yet")

    click = ClickSchema(
        target="vendor_logo",
        vendor=vendor,  # type: ignore
        user_id=user_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    create_document("click", click)
    return RedirectResponse(url=url, status_code=302)


@app.get("/r/product/{product_id}")
async def redirect_product(product_id: str, request: Request, user_id: Optional[str] = None):
    prod = db["product"].find_one({"_id": oid(product_id)})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    db["product"].update_one({"_id": prod["_id"]}, {"$inc": {"clicks": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}})

    click = ClickSchema(
        target="product",
        product_id=str(prod["_id"]),
        affiliate_id=prod.get("affiliate_id"),
        user_id=user_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    create_document("click", click)

    return RedirectResponse(url=prod.get("affiliate_link"), status_code=302)


# Orders
class OrderIn(BaseModel):
    user_id: str
    product_id: str


@app.post("/orders")
def create_order(payload: OrderIn):
    prod = db["product"].find_one({"_id": oid(payload.product_id)})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    order = OrderSchema(
        user_id=payload.user_id,
        product_id=payload.product_id,
        affiliate_id=prod.get("affiliate_id"),
        status="redirected",
        vendor_url=prod.get("affiliate_link"),
    )
    oid_str = create_document("order", order)
    db["product"].update_one({"_id": prod["_id"]}, {"$inc": {"orders": 1}})
    created = db["order"].find_one({"_id": ObjectId(oid_str)})
    created["_id"] = str(created["_id"])
    return created


@app.get("/orders")
def list_orders(user_id: Optional[str] = None, affiliate_id: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if user_id:
        filt["user_id"] = user_id
    if affiliate_id:
        filt["affiliate_id"] = affiliate_id
    items = list(db["order"].find(filt).sort("created_at", -1))
    for it in items:
        it["_id"] = str(it["_id"])
    return {"items": items}


# Subscriptions
class SubscriptionIn(BaseModel):
    user_id: str
    tx_id: str
    amount: float


@app.post("/subscriptions")
def create_subscription(payload: SubscriptionIn):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    sub = SubscriptionSchema(
        user_id=payload.user_id, tx_id=payload.tx_id, amount=payload.amount, starts_at=now, expires_at=expires
    )
    create_document("subscription", sub)
    db["user"].update_one({"_id": oid(payload.user_id)}, {"$set": {"ad_free": True, "updated_at": now}})
    return {"ok": True, "expires_at": expires.isoformat()}


@app.get("/subscriptions")
def list_subscriptions(user_id: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if user_id:
        filt["user_id"] = user_id
    items = list(db["subscription"].find(filt).sort("created_at", -1))
    for it in items:
        it["_id"] = str(it["_id"])
    return {"items": items}


# Admin settings and stats
@app.get("/admin/settings")
def get_admin_settings():
    doc = db["adminsetting"].find_one({})
    if not doc:
        return {}
    doc["_id"] = str(doc["_id"]) if "_id" in doc else None
    return doc


@app.post("/admin/settings")
def save_admin_settings(payload: Dict[str, Any]):
    payload.pop("_id", None)
    existing = db["adminsetting"].find_one({})
    if existing:
        db["adminsetting"].update_one({"_id": existing["_id"]}, {"$set": payload})
    else:
        create_document("adminsetting", AdminSettingSchema(**payload))
    return get_admin_settings()


@app.get("/admin/stats")
def admin_stats():
    buyers = db["user"].count_documents({"role": "buyer"})
    affiliates = db["user"].count_documents({"role": "affiliate"})
    subscribers = db["subscription"].count_documents({"expires_at": {"$gt": datetime.now(timezone.utc)}})
    earnings = db["subscription"].aggregate([
        {"$group": {"_id": None, "sum": {"$sum": "$amount"}}}
    ])
    total_earnings = 0
    for r in earnings:
        total_earnings = r.get("sum", 0)
    return {
        "total_buyers": buyers,
        "total_affiliates": affiliates,
        "subscribers": subscribers,
        "app_earnings": total_earnings,
    }


@app.get("/schema")
def get_schema():
    return {"collections": [
        "user", "product", "order", "click", "adminsetting", "subscription", "notification"
    ]}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
