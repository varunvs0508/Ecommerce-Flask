import razorpay
from flask import Blueprint, redirect, request, render_template, url_for, flash, current_app, jsonify, abort,  send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from extensions import db
from models.models import Cart, Product, Address, Order, OrderItem
from payments import get_razorpay_client
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask import send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter

cart = Blueprint("cart", __name__)

# View Cart
@cart.route("/cart")
@jwt_required()
def view_cart():
    user_id = get_jwt_identity()
    page = request.args.get("page", 1, type=int)
    items_data = (
        db.session.query(Cart, Product)
        .join(Product)
        .filter(Cart.user_id == user_id)
        .paginate(page=page, per_page=10)
    )
    items = []
    for cart_item, product in items_data.items:
        price = product.discount_price or product.price
        subtotal = price * cart_item.quantity
        items.append({
            "product": product,
            "quantity": cart_item.quantity,
            "subtotal": subtotal
        })
    total = sum(item["subtotal"] for item in items)
    return render_template(
        "cart.html",
        items=items,
        total=total,
        pagination=items_data
    )

# Add To Cart
@cart.route("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except NoAuthorizationError:
        flash("Please login to add items to cart")
        return redirect(url_for("auth.login", next=request.url))
    product = Product.query.filter_by(id=product_id).with_for_update().first()
    if not product:
        return redirect(url_for("product.products_page"))
    if product.stock <= 0:
        flash("Product is out of stock")
        return redirect(request.referrer or url_for("product.products_page"))
    item = Cart.query.filter_by(
        user_id=user_id,
        product_id=product_id
    ).with_for_update().first()
    if item:
        if item.quantity < product.stock:
            item.quantity += 1
        else:
            flash("Maximum stock reached")
    else:
        db.session.add(Cart(
            user_id=user_id,
            product_id=product_id,
            quantity=1
        ))
    try:
        db.session.commit()
    except:
        db.session.rollback()
        flash("Something went wrong")
    return redirect(request.referrer or url_for("product.products_page"))

# Increase Quantity
@cart.route("/cart/increase/<int:product_id>")
@jwt_required()
def increase_quantity(product_id):
    user_id = get_jwt_identity()
    item = Cart.query.filter_by(
        user_id=user_id,
        product_id=product_id
    ).with_for_update().first()
    if item:
        product = Product.query.filter_by(id=product_id).with_for_update().first()
        if product and item.quantity < product.stock:
            item.quantity += 1
            try:
                db.session.commit()
            except:
                db.session.rollback()
                flash("Something went wrong")
        else:
            flash("Maximum stock reached")
    return redirect(url_for("cart.view_cart"))

# Decrease Quantity
@cart.route("/cart/decrease/<int:product_id>")
@jwt_required()
def decrease_quantity(product_id):
    user_id = get_jwt_identity()
    item = Cart.query.filter_by(
        user_id=user_id,
        product_id=product_id
    ).with_for_update().first()
    if item:
        if item.quantity > 1:
            item.quantity -= 1
        else:
            db.session.delete(item)
        try:
            db.session.commit()
        except:
            db.session.rollback()
            flash("Something went wrong")
    return redirect(url_for("cart.view_cart"))

# Remove Item
@cart.route("/cart/remove/<int:product_id>")
@jwt_required()
def remove_from_cart(product_id):
    user_id = get_jwt_identity()
    item = Cart.query.filter_by(
        user_id=user_id,
        product_id=product_id
    ).with_for_update().first()
    if item:
        db.session.delete(item)
        try:
            db.session.commit()
        except:
            db.session.rollback()
            flash("Something went wrong")
    return redirect(url_for("cart.view_cart"))

# Checkout Page
@cart.route("/checkout")
@jwt_required()
def checkout_page():
    user_id = get_jwt_identity()
    items = (
        db.session.query(Cart, Product)
        .join(Product)
        .filter(Cart.user_id == user_id)
        .all()
    )
    if not items:
        return redirect(url_for("cart.view_cart"))
    cart_items = []
    total = 0
    for c, p in items:
        price = p.discount_price or p.price
        subtotal = price * c.quantity
        total += subtotal
        client = get_razorpay_client()
        cart_items.append({
            "product": p,
            "quantity": c.quantity,
            "subtotal": subtotal
        })
    client = get_razorpay_client()
    razorpay_order = client.order.create({
        "amount": int(total * 100),
        "currency": "INR",
        "payment_capture": 1
    })
    addresses = Address.query.filter_by(user_id=user_id).all()
    return render_template(
        "checkout.html",
        items=cart_items,
        total=total,
        addresses=addresses,
        razorpay_order=razorpay_order,
        razorpay_key=current_app.config["RAZORPAY_KEY_ID"]
    )

# Place Order (COD)
@cart.route("/place-order", methods=["POST"])
@jwt_required()
def place_order():
    user_id = get_jwt_identity()
    address_id = request.form.get("address_id")
    payment_method = request.form.get("payment_method", "cod")
    # PAYMENT VALIDATION
    if payment_method not in ["cod"]:
        flash("Invalid payment method")
        return redirect(url_for("cart.checkout_page"))
    try:
        # HANDLE ADDRESS
        if address_id == "new":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            address_line = request.form.get("address", "").strip()
            city = request.form.get("city", "").strip()
            state = request.form.get("state", "").strip()
            pincode = request.form.get("pincode", "").strip()
            errors = []
            if not name:
                errors.append("Name is required")
            if not phone or not phone.isdigit() or len(phone) != 10:
                errors.append("Invalid phone number")
            if not address_line:
                errors.append("Address is required")
            if not city:
                errors.append("City is required")
            if not state:
                errors.append("State is required")
            if not pincode or not pincode.isdigit() or len(pincode) != 6:
                errors.append("Invalid pincode")
            if errors:
                for e in errors:
                    flash(e)
                return redirect(url_for("cart.checkout_page"))
            # CREATE ADDRESS (not committed yet)
            address = Address(
                user_id=user_id,
                full_name=name,
                phone="+91" + phone,
                address_line=address_line,
                city=city,
                state=state,
                pincode=pincode,
                is_default=False
            )
            db.session.add(address)
            db.session.flush()
        else:
            address = Address.query.filter_by(id=address_id,user_id=user_id).first()
        if not address:
            flash("Invalid address")
            return redirect(url_for("cart.checkout_page"))
        # LOCK CART + PRODUCTS
        items = (
            db.session.query(Cart, Product)
            .join(Product)
            .filter(Cart.user_id == user_id)
            .with_for_update()
            .all()
        )
        if not items:
            flash("Cart is empty")
            return redirect(url_for("cart.view_cart"))
        # CREATE ORDER
        order = Order(
            user_id=user_id,
            payment_method=payment_method,
            payment_status="pending",
            payment_id=None,
            status="placed",
            name=address.full_name,
            phone=address.phone,
            address=address.address_line,
            city=address.city,
            state=address.state,
            pincode=address.pincode
        )
        db.session.add(order)
        db.session.flush()  # get order.id
        total = 0
        # PROCESS ITEMS
        for c, p in items:
            # Lock each product row again (safe)
            product = Product.query.filter_by(id=p.id).with_for_update().first()
            if not product:
                raise Exception("Product not found")
            if product.stock < c.quantity:
                raise Exception(f"{product.product_display_name} out of stock")
            price = product.discount_price or product.price
            subtotal = price * c.quantity
            total += subtotal
            # Reduce stock
            product.stock -= c.quantity
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=c.quantity,
                price=price
            ))
        # FINALIZE ORDER
        order.total_amount = total
        # CLEAR CART
        Cart.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        flash("Order placed successfully ✅")
        return redirect(url_for("cart.orders_page"))
    except Exception as e:
        db.session.rollback()
        flash(str(e))
        return redirect(url_for("cart.checkout_page"))

# Orders Page
@cart.route("/orders")
@jwt_required()
def orders_page():
    user_id = get_jwt_identity()
    page = request.args.get("page", 1, type=int)
    orders = Order.query.filter_by(user_id=user_id)\
        .order_by(Order.created_at.desc())\
        .paginate(page=page, per_page=10)
    for order in orders.items:
        if order.delivered_at:
            expiry_date = order.delivered_at + timedelta(days=7)
            remaining = (expiry_date - datetime.utcnow()).days
            # if expired
            if remaining < 0:
                order.return_days_left = 0
            else:
                order.return_days_left = remaining
        else:
            order.return_days_left = None
    return render_template("orders.html", orders=orders)

@cart.route("/orders/<int:order_id>")
@jwt_required()
def order_details(order_id):
    user_id = get_jwt_identity()
    order = Order.query.filter_by(id=order_id,user_id=user_id).first()
    if not order:
        flash("Order not found")
        return redirect(url_for("cart.orders_page"))
    items = (
        db.session.query(OrderItem, Product)
        .join(Product, OrderItem.product_id == Product.id)
        .filter(OrderItem.order_id == order_id)
        .all()
    )
    order_items = []
    for oi, p in items:
        order_items.append({
            "product": p,
            "quantity": oi.quantity,
            "price": oi.price,
            "subtotal": oi.price * oi.quantity
        })
    return render_template(
        "order_details.html",
        order=order,
        items=order_items,
        status_steps = ["placed", "shipped", "delivered"]
    )

@cart.route("/verify-payment", methods=["POST"])
@jwt_required()
def verify_payment():
    data = request.get_json()
    address_id = data.get("address_id")
    user_id = get_jwt_identity()
    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": data["razorpay_order_id"],
            "razorpay_payment_id": data["razorpay_payment_id"],
            "razorpay_signature": data["razorpay_signature"]
        })
    except:
        return jsonify({"success": False})    
    existing = Order.query.filter_by(payment_id=data["razorpay_payment_id"]).first()
    if existing:
        return jsonify({"success": True})
    # PAYMENT SUCCESS → NOW CREATE ORDER
    items = (
        db.session.query(Cart, Product)
        .join(Product)
        .filter(Cart.user_id == user_id)
        .with_for_update()
        .all()
    )
    if not items:
        return jsonify({"success": False})
    total = 0
    if address_id == "new":
      name = data.get("name")
      phone = data.get("phone")
      address_line = data.get("address")
      city = data.get("city")
      state = data.get("state")
      pincode = data.get("pincode")
      if not all([name, phone, address_line, city, state, pincode]):
        return jsonify({"success": False, "message": "Missing address fields"})
      address = Address(
        user_id=user_id,
        full_name=name,
        phone="+91" + phone,
        address_line=address_line,
        city=city,
        state=state,
        pincode=pincode
     )
      db.session.add(address)
      db.session.flush()
    else:
     address = Address.query.filter_by(id=address_id,user_id=user_id).first()
    if not address:
        return jsonify({"success": False, "message": "Invalid address"})
    try:
        order = Order(
        user_id=user_id,
        payment_method="razorpay",
        payment_id=data["razorpay_payment_id"],
        payment_status="success",
        status="placed",
        name=address.full_name,
        phone=address.phone,
        address=address.address_line,
        city=address.city,
        state=address.state,
        pincode=address.pincode
    )
        db.session.add(order)
        db.session.flush()
        for c, p in items:
            product = Product.query.filter_by(id=p.id).with_for_update().first()
            if product.stock < c.quantity:
                raise Exception("Out of stock")
            price = product.discount_price or product.price
            subtotal = price * c.quantity
            total += subtotal
            product.stock -= c.quantity
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=c.quantity,
                price=price
            ))
        order.total_amount = total
        Cart.query.filter_by(user_id=user_id).with_for_update().delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False})
    
@cart.route('/download-invoice/<int:order_id>')
@jwt_required()
def download_invoice(order_id):
    user_id = get_jwt_identity()
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return "Order not found", 404
    
    # Use memory instead of file
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
   
    # HEADER
    styles['Title'].alignment = 1
    elements.append(Paragraph("CopVizz Pvt Ltd", styles['Title']))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Invoice - Order #{order.id}", styles['Heading2']))
    elements.append(Spacer(1, 10))
    
    # CUSTOMER DETAILS
    elements.append(Paragraph(f"<b>Name:</b> {order.name}", styles['Normal']))
    elements.append(Paragraph(f"<b>Address:</b> {order.address}", styles['Normal']))
    elements.append(Paragraph(f"<b>City:</b> {order.city}", styles['Normal']))
    elements.append(Paragraph(f"<b>Pincode:</b> {order.pincode}", styles['Normal']))
    elements.append(Spacer(1, 10))
    
    # ORDER INFO
    elements.append(Paragraph(f"<b>Date:</b> {order.created_at.strftime('%d %b %Y')}", styles['Normal']))
    elements.append(Paragraph(f"<b>Status:</b> {order.status}", styles['Normal']))
    elements.append(Paragraph(f"<b>Payment:</b> {order.payment_method}", styles['Normal']))
    elements.append(Paragraph(f"<b>Transaction:</b> {order.payment_id or 'N/A'}", styles['Normal']))
    elements.append(Spacer(1, 10))
    
    # ITEMS TABLE
    table_data = [["Product", "Qty", "Price", "Subtotal"]]
    total = 0
    for item in order.items:
        subtotal = item.price * item.quantity
        total += subtotal
        table_data.append([
            item.product.product_display_name[:30],
            str(item.quantity),
            f"₹{item.price}",
            f"₹{subtotal}"
        ])
    table = Table(table_data, colWidths=[200, 60, 80, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.black),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))
    
    # TOTAL
    elements.append(Paragraph(f"<b>Total Amount: ₹{total}</b>", styles['Heading2']))
    
    # BUILD
    doc.build(elements)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{order.id}.pdf",
        mimetype='application/pdf'
    )

@cart.route("/request-refund/<int:order_id>", methods=["POST"])
@jwt_required()
def request_refund(order_id):
    user_id = get_jwt_identity()
    order = Order.query.get_or_404(order_id)
    if order.user_id != user_id:
        abort(403)
    refund_details = request.form.get("refund_details")

    # Only after delivery
    if order.status != "delivered":
        flash("Refund allowed only after delivery")
        return redirect(url_for("cart.orders_page"))

    # Return window (7 days)
    if not order.delivered_at:
        flash("Delivery date not available")
        return redirect(url_for("cart.orders_page"))

    if datetime.utcnow() > order.delivered_at + timedelta(days=7):
        flash("Return window expired (7 days)")
        return redirect(url_for("cart.orders_page"))

    # Payment must be successful
    if order.payment_method != "cod" and order.payment_status != "success":
        flash("Refund not allowed for unpaid orders")
        return redirect(url_for("cart.orders_page"))

    # Prevent duplicate
    if order.refund_status in ["requested", "processed"]:
        flash("Refund already requested")
        return redirect(url_for("cart.orders_page"))

    # Save data
    order.refund_status = "requested"
    order.refund_reason = request.form.get("reason")

    if order.payment_method == "cod":
        order.refund_details = refund_details

    try:
        db.session.commit()
        flash("Refund requested successfully")
    except:
        db.session.rollback()
        flash("Error requesting refund")

    return redirect(url_for("cart.orders_page"))