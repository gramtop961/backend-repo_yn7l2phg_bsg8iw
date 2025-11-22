"""
Database Schemas for Shopearn Pro

Each Pydantic model corresponds to one MongoDB collection. The collection name is the lowercase class name.

- User -> "user"
- Product -> "product"
- Order -> "order"
- Click -> "click"
- AdminSetting -> "adminsetting"
- Subscription -> "subscription"
- Notification -> "notification"
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

Role = Literal["buyer", "affiliate", "admin"]
Gender = Literal["male", "female", "other", "prefer_not_to_say"]
Vendor = Literal[
    "amazon", "flipkart", "meesho", "shopify", "myntra", "ajio", "alibaba", "snapdeal"
]

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email (login)")
    password_hash: str = Field(..., description="Hashed password")
    role: Role = Field("buyer", description="User role")
    phone: Optional[str] = Field(None, description="Phone number")
    age: Optional[int] = Field(None, ge=0, le=120)
    gender: Optional[Gender] = None
    photo_url: Optional[str] = None
    is_active: bool = True
    ad_free: bool = False

class Product(BaseModel):
    affiliate_id: str = Field(..., description="Uploader (affiliate) user id")
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    margin: Optional[float] = Field(None, ge=0, description="Affiliate commission")
    images: List[HttpUrl] = Field(default_factory=list)
    vendor: Vendor
    affiliate_link: HttpUrl
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    rating: float = Field(0, ge=0, le=5)
    hot_deal: bool = False
    hot_deal_expires_at: Optional[datetime] = None
    featured: bool = False
    clicks: int = 0
    orders: int = 0

class Order(BaseModel):
    user_id: str
    product_id: str
    affiliate_id: Optional[str] = None
    status: Literal["redirected", "placed_on_vendor", "cancelled"] = "redirected"
    vendor_url: Optional[str] = None

class Click(BaseModel):
    product_id: Optional[str] = None
    affiliate_id: Optional[str] = None
    user_id: Optional[str] = None
    target: Literal["product", "vendor_logo"]
    vendor: Optional[Vendor] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None

class AdminSetting(BaseModel):
    # Map vendor -> affiliate URL
    amazon: Optional[HttpUrl] = None
    flipkart: Optional[HttpUrl] = None
    meesho: Optional[HttpUrl] = None
    shopify: Optional[HttpUrl] = None
    myntra: Optional[HttpUrl] = None
    ajio: Optional[HttpUrl] = None
    alibaba: Optional[HttpUrl] = None
    snapdeal: Optional[HttpUrl] = None

class Subscription(BaseModel):
    user_id: str
    tx_id: str
    amount: float
    starts_at: datetime
    expires_at: datetime

class Notification(BaseModel):
    user_id: Optional[str] = None  # if None => broadcast
    title: str
    body: str
    product_id: Optional[str] = None
