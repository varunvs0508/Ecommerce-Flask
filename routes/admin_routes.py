from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.models import User, Product, Order, OrderItem
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sqlalchemy import func, and_
from datetime import datetime, timedelta, timezone
from functools import wraps
import matplotlib.ticker as ticker
from payments import get_razorpay_client

admin = Blueprint("admin", __name__)

# GLOBAL CONSTANTS (ONLY ONCE)
ALLOWED_STATUS = ["placed", "shipped", "delivered", "cancelled"]
VALID_TRANSITIONS = {
    "placed": ["shipped", "cancelled"],
    "shipped": ["delivered", "cancelled"],
    "delivered": [],
    "cancelled": [],
    "refunded": [] 
}


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        if not is_admin(user_id):
            flash("Access denied")
            return redirect("/")
        return fn(*args, **kwargs)
    return wrapper


def is_admin(user_id):
    user = db.session.get(User, user_id)
    return user and user.role == "admin"


# DASHBOARD
@admin.route("/admin")
@jwt_required()
@admin_required
def admin_dashboard():
    total_users = User.query.filter_by(role="user").count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).scalar() or 0
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template(
        "admin/admin_dashboard.html",
        is_admin=True,
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue,
        recent_orders=recent_orders
    )

# ORDERS
@admin.route("/admin/orders")
@jwt_required()
@admin_required
def all_orders():
    page = request.args.get("page", 1, type=int)
    orders = Order.query.order_by(Order.created_at.desc()).paginate(page=page, per_page=9)
    return render_template("admin/admin_orders.html", orders=orders)

# UPDATE ORDER
@admin.route("/admin/orders/<int:order_id>/update", methods=["POST"])
@jwt_required()
@admin_required
def update_order(order_id):
    order = Order.query.get(order_id)
    # SAFE CHECK FIRST
    if not order:
        flash("Order not found")
        return redirect(url_for("admin.all_orders"))

    # BLOCK REFUNDED
    if order.status == "refunded":
        flash("Cannot modify refunded order")
        return redirect(url_for("admin.all_orders"))

    new_status = request.form.get("status")

    if new_status not in ALLOWED_STATUS:
        flash("Invalid status")
        return redirect(url_for("admin.all_orders"))

    current_status = order.status

    if new_status not in VALID_TRANSITIONS.get(current_status, []):
        flash(f"Invalid status change: {current_status} → {new_status}")
        return redirect(url_for("admin.all_orders"))

    order.status = new_status
    if new_status == "delivered":
        order.delivered_at = datetime.utcnow()

    try:
        db.session.commit()
        flash("Order updated successfully")
    except:
        db.session.rollback()
        flash("Something went wrong")

    return redirect(url_for("admin.all_orders"))

# USERS
@admin.route("/admin/users")
@jwt_required()
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    users = User.query.filter_by(role="user").paginate(page=page, per_page=10)
    return render_template("admin/users.html", users=users)

# TOGGLE USER
@admin.route("/admin/users/<user_id>/toggle", methods=["POST"])
@jwt_required()
@admin_required
def toggle_user(user_id):
    user = User.query.get(user_id)
    if not user:
        flash("User not found")
        return redirect(url_for("admin.users"))
    if user.role == "admin":
        flash("Cannot block admin")
        return redirect(url_for("admin.users"))
    user.status = "blocked" if user.status == "active" else "active"
    db.session.commit()
    flash("User updated")
    return redirect(url_for("admin.users"))

# PRODUCTS
@admin.route("/admin/products")
@jwt_required()
@admin_required
def products():
    page = request.args.get("page", 1, type=int)
    products = Product.query.order_by(
        Product.created_at.desc()
    ).paginate(page=page, per_page=12)
    low_stock_products = Product.query.filter(Product.stock < 10).all()
    return render_template("admin/admin_products.html", products=products, low_stock_products=low_stock_products)

# ADD PRODUCT
@admin.route("/admin/products/add", methods=["POST"])
@jwt_required()
@admin_required
def add_product():
    product = Product(
        product_display_name=request.form.get("name"),
        price=request.form.get("price"),
        stock=request.form.get("stock"),
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(product)
    db.session.commit()
    flash("Product added")
    return redirect(url_for("admin.products"))

# DELETE PRODUCT
@admin.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@jwt_required()
@admin_required
def delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        if product.order_items:
            flash("Cannot delete product used in orders")
            return redirect(url_for("admin.products"))
        db.session.delete(product)
        db.session.commit()
    flash("Product deleted")
    return redirect(url_for("admin.products"))

# SALES REPORT
@admin.route("/admin/sales")
@jwt_required()
@admin_required
def sales_report():
    today = datetime.utcnow().date()
    last_7_days = datetime.utcnow() - timedelta(days=7)
    
    # TOTAL REVENUE
    total_revenue = db.session.query(func.sum(Order.total_amount))\
        .filter(Order.status != "refunded").scalar() or 0

    # REFUNDED
    refunded_amount = db.session.query(func.sum(Order.total_amount))\
        .filter(Order.status == "refunded").scalar() or 0

    # TOTAL ORDERS
    total_orders = Order.query.count()

    # TODAY SALES
    today_sales = db.session.query(func.sum(Order.total_amount))\
        .filter(
            func.date(Order.created_at) == today,
            Order.status != "refunded"
        ).scalar() or 0

    # LAST 7 DAYS SALES
    daily_sales = db.session.query(func.date(Order.created_at),func.sum(Order.total_amount)
    ).filter(
        and_(
            Order.created_at >= last_7_days,
            Order.status != "refunded"
        )
    ).group_by(func.date(Order.created_at)).all()
    days = [str(d[0]) for d in daily_sales]
    day_revenue = [float(d[1]) for d in daily_sales]

    # MONTHLY SALES
    monthly_sales = db.session.query(
        func.date_format(Order.created_at, '%Y-%m'),
        func.sum(Order.total_amount)
    ).filter(
        Order.status != "refunded"
    ).group_by(func.date_format(Order.created_at, '%Y-%m')).all()
    months = [m[0] for m in monthly_sales]
    revenue = [float(m[1]) for m in monthly_sales]

    # TOP PRODUCTS
    top_products = db.session.query(
        Product.product_display_name,
        func.sum(OrderItem.quantity)
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .group_by(Product.product_display_name)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(5).all()
    product_names = [p[0] for p in top_products]
    quantities = [int(p[1]) for p in top_products]
    return render_template(
        "admin/sales.html",
        total_revenue=total_revenue,
        refunded_amount=refunded_amount,
        total_orders=total_orders,
        today_sales=today_sales,
        days=days,
        day_revenue=day_revenue,
        months=months,
        revenue=revenue,
        product_names=product_names,
        quantities=quantities
    )

# REFUND ORDER
@admin.route("/admin/refund/<int:order_id>", methods=["POST"])
@jwt_required()
@admin_required
def refund_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        return "Order not found", 404
    if order.status == "refunded" or order.refund_status in ["processed", "failed"]:
        return "Refund already attempted"
    if order.payment_method != "razorpay":
        return "Refund only for Razorpay payments"
    if order.payment_status != "success":
        return "Payment not completed"
    client = get_razorpay_client()
    try:
        refund = client.payment.refund(
            order.payment_id,
            {"amount": int(order.total_amount * 100)}
        )
        order.refund_status = "processed"
        order.refund_id = refund["id"]
        order.status = "refunded"
        db.session.commit()
    except Exception as e:
        order.refund_status = "failed"
        db.session.commit()
        return str(e)
    return redirect(url_for('admin.all_orders'))

# APPROVE REFUND
@admin.route("/admin/approve-refund/<int:order_id>", methods=["POST"])
@jwt_required()
@admin_required
def approve_refund(order_id):
    order = Order.query.get(order_id)
    if not order:
        return "Order not found"
    # Prevent duplicate processing
    if order.status == "refunded" or order.refund_status == "processed":
        return "Already refunded"

    # No request made
    if order.refund_status != "requested":
        return "No refund request"
    try:
        # ONLINE PAYMENT (RAZORPAY)
        if order.payment_method == "razorpay":
            if order.payment_status != "success":
                return "Payment not completed"
            client = get_razorpay_client()
            refund = client.payment.refund(
                order.payment_id,
                {"amount": int(order.total_amount * 100)}
            )
            order.refund_id = refund["id"]
        # COD (MANUAL REFUND)
        elif order.payment_method == "cod":
            order.refund_id = None
        else:
            return "Unsupported payment method"

        # COMMON UPDATE
        order.refund_status = "processed"
        order.status = "refunded"
        db.session.commit()
    except Exception as e:
        order.refund_status = "failed"
        db.session.commit()
        return str(e)
    return redirect(url_for('admin.all_orders'))

@admin.route("/admin/update-stock/<int:product_id>", methods=["POST"])
@jwt_required()
@admin_required
def update_stock(product_id):
    product = Product.query.get_or_404(product_id)
    new_stock = int(request.form.get("stock"))
    product.stock += new_stock   # adds stock
    try:
        db.session.commit()
        flash("Stock updated successfully")
    except:
        db.session.rollback()
        flash("Error updating stock")
    return redirect(url_for("admin.products"))