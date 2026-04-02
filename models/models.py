from extensions import db
from datetime import datetime, timezone

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255))
    phone = db.Column(db.String(20), unique=True)
    role = db.Column(db.Enum('admin','user'), default='user')
    is_email_verified = db.Column(db.Boolean, default=False)
    is_phone_verified = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum('active','inactive','blocked'), default='active')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime(timezone=True))
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime(timezone=True))   
    account_locked_until = db.Column(db.DateTime(timezone=True))
    orders = db.relationship("Order", backref="user", lazy=True)
    addresses = db.relationship("Address", backref="user", lazy=True)
    cart_items = db.relationship("Cart", backref="user", lazy=True)
    wishlist_items = db.relationship("Wishlist", backref="user", lazy=True)

class OTPVerification(db.Model):
    __tablename__ = "otp_verification"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20), index=True)
    otp_code = db.Column(db.String(6), nullable=False)
    otp_type = db.Column(db.Enum('email','phone','password_reset','phone_update'),nullable=False)
    attempts = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    locked_until = db.Column(db.DateTime(timezone=True))

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.BigInteger, primary_key=True)
    product_display_name = db.Column(db.String(255))
    description = db.Column(db.Text)
    brand = db.Column(db.String(100))
    gender = db.Column(db.String(20), index=True)
    master_category = db.Column(db.String(100), index=True)
    sub_category = db.Column(db.String(100))
    article_type = db.Column(db.String(100))
    base_colour = db.Column(db.String(50), index=True)
    season = db.Column(db.String(20))
    year = db.Column(db.Integer, index=True)
    usage_type = db.Column(db.String(50))
    price = db.Column(db.Numeric(10,2))
    discount_price = db.Column(db.Numeric(10,2))
    stock = db.Column(db.Integer)
    rating = db.Column(db.Float)
    review_count = db.Column(db.Integer)
    image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    cart_items = db.relationship("Cart", backref="product", lazy=True)
    wishlist_items = db.relationship("Wishlist", backref="product", lazy=True)
    order_items = db.relationship("OrderItem", backref="product", lazy=True)

class APIKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Cart(db.Model):
    __tablename__ = "cart"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20),db.ForeignKey("users.id"),nullable=False)
    product_id = db.Column(db.BigInteger,db.ForeignKey("products.id"),nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint('user_id', 'product_id', name='unique_cart_item'),)

class Wishlist(db.Model):
    __tablename__ = "wishlist"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20),db.ForeignKey("users.id"),nullable=False)
    product_id = db.Column(db.BigInteger,db.ForeignKey("products.id"),nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint('user_id','product_id', name='unique_wishlist_item'),)

class Address(db.Model):
    __tablename__ = "addresses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20),db.ForeignKey("users.id"),nullable=False,index=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address_line = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))

class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20), db.ForeignKey("users.id"))
    total_amount = db.Column(db.Numeric(10,2))
    payment_method = db.Column(db.String(20))  # cod/razorpay
    payment_id = db.Column(db.String(100), unique=True)
    payment_status = db.Column(db.String(20), default="pending")
    status = db.Column(db.String(20), default="placed")
    refund_id = db.Column(db.String(100))
    refund_status = db.Column(db.String(20), default=None)
    refund_reason = db.Column(db.String(255))
    refund_details = db.Column(db.String(255))
    delivered_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime(timezone=True),default=lambda: datetime.now(timezone.utc))
    # Address snapshot
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pincode = db.Column(db.String(10))
    items = db.relationship("OrderItem", backref="order", lazy=True)

class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    product_id = db.Column(db.BigInteger, db.ForeignKey("products.id"))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Numeric(10,2))