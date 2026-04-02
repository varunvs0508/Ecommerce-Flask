from flask import Blueprint, render_template, redirect, request, flash, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from extensions import db
from models.models import Wishlist, Cart, Product
from flask_jwt_extended.exceptions import NoAuthorizationError

wishlist_bp = Blueprint("wishlist", __name__)

# View Wishlist
@wishlist_bp.route("/wishlist")
@jwt_required()
def wishlist_page():
    user_id = get_jwt_identity()
    page = request.args.get("page", 1, type=int)
    items = (
        db.session.query(Wishlist, Product)
        .join(Product, Wishlist.product_id == Product.id)
        .filter(Wishlist.user_id == user_id)
        .paginate(page=page, per_page=10)
    )
    wishlist_items = []
    for w, p in items.items:
        wishlist_items.append({"product": p})
    return render_template(
        "wishlist.html",
        items=wishlist_items,
        pagination=items
    )

# Add to Wishlist
@wishlist_bp.route("/wishlist/add/<int:id>")
def add_to_wishlist(id):
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
    except NoAuthorizationError:
        flash("Please login to use wishlist")
        return redirect(url_for("auth.login", next=request.url))
    exists = Wishlist.query.filter_by(user_id=user_id, product_id=id).first()
    if not exists:
        item = Wishlist(user_id=user_id,product_id=id)
        db.session.add(item)
        db.session.commit()
    return redirect(request.referrer or "/wishlist")

# Remove from Wishlist
@wishlist_bp.route("/wishlist/remove/<int:id>")
@jwt_required()
def remove_from_wishlist(id):
    user_id = get_jwt_identity()
    item = Wishlist.query.filter_by(user_id=user_id,product_id=id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return redirect("/wishlist")

# Move Wishlist Item to Cart
@wishlist_bp.route("/wishlist/move_to_cart/<int:id>")
@jwt_required()
def move_to_cart(id):
    user_id = get_jwt_identity()
    try:
        # Lock product FIRST
        product = (Product.query.filter_by(id=id).with_for_update().first())
        if not product:
            return redirect(url_for("wishlist.wishlist_page"))
        if product.stock <= 0:
            flash("Product is out of stock")
            return redirect(url_for("wishlist.wishlist_page"))
        # Lock cart item
        cart_item = (
            Cart.query
            .filter_by(user_id=user_id, product_id=id)
            .with_for_update()
            .first()
        )
        if cart_item:
            if cart_item.quantity < product.stock:
                cart_item.quantity += 1
            else:
                flash("Maximum stock reached")
                return redirect(url_for("wishlist.wishlist_page"))
        else:
            cart_item = Cart(
                user_id=user_id,
                product_id=id,
                quantity=1
            )
            db.session.add(cart_item)

        # Lock wishlist item before deleting
        wish = (
            Wishlist.query
            .filter_by(user_id=user_id, product_id=id)
            .with_for_update()
            .first()
        )
        if wish:
            db.session.delete(wish)
        db.session.commit()
        return redirect("/wishlist")
    except Exception:
        db.session.rollback()
        flash("Something went wrong")
        return redirect(url_for("wishlist.wishlist_page"))