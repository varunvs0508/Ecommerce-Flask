from flask import Blueprint, request, render_template, url_for, redirect
from models.models import Product, APIKey
from extensions import limiter
from sqlalchemy import or_
from sqlalchemy import func
from routes.auth_routes import get_current_user

product = Blueprint("product", __name__)

# SMART DETECTION FUNCTIONS
def detect_material(p):
    name = (p.product_display_name or "").lower()
    if "cotton" in name:
        return "Cotton"
    if "denim" in name:
        return "Denim"
    if "leather" in name:
        return "Leather"
    if "polyester" in name:
        return "Polyester"
    if "silk" in name:
        return "Silk"
    if "wool" in name:
        return "Wool"
    if p.article_type in ["Shirts", "Tshirts"]:
        return "Cotton Blend"
    if p.article_type in ["Shoes", "Sandals"]:
        return "Synthetic / Leather"
    return "Premium Fabric"

def detect_fit(p):
    name = (p.product_display_name or "").lower()
    if "slim fit" in name:
        return "Slim Fit"
    if "regular fit" in name:
        return "Regular Fit"
    if "skinny" in name:
        return "Skinny Fit"
    if "oversized" in name or "loose" in name:
        return "Loose Fit"
    return "Regular Fit"

def detect_occasion(p):
    usage_map = {
        "Casual": "Casual Wear",
        "Formal": "Office Wear",
        "Sports": "Sports Wear",
        "Party": "Party Wear",
        "Ethnic": "Festive Wear"
    }
    if p.usage_type in usage_map:
        return usage_map[p.usage_type]
    article_map = {
        "Shirts": "Office Wear",
        "Tshirts": "Casual Wear",
        "Jeans": "Casual Wear",
        "Blazers": "Formal Wear",
        "Kurtas": "Festive Wear",
        "Dresses": "Party Wear",
        "Sports Shoes": "Sports Wear"
    }
    if p.article_type in article_map:
        return article_map[p.article_type]
    name = (p.product_display_name or "").lower()
    if "party" in name:
        return "Party Wear"
    if "formal" in name:
        return "Office Wear"
    return "Everyday Wear"

# GENERATE FULL PRODUCT DETAILS
def build_product_details(p):
    material = detect_material(p)
    fit = detect_fit(p)
    occasion = detect_occasion(p)
    color = (p.base_colour or "standard")
    article = (p.article_type or "product")
    gender = (p.gender or "unisex")
    season = (p.season or "all seasons")
    usage = (p.usage_type or "daily")
    # Description
    description = f"""
Enhance your style with this {color} {article} for {gender}.
Designed for {occasion.lower()}, it offers a perfect balance of comfort and style.

Crafted using {material}, this piece ensures durability and a premium feel.
Its {fit} design makes it suitable for everyday wear, especially during {season}.

A versatile addition to your wardrobe, this product is ideal for {usage} use.
"""

    # Highlights
    highlights = [
        p.master_category or "",
        p.sub_category or "",
        p.article_type or "",
        p.base_colour or "",
        p.gender or ""
    ]

    # Features (dynamic)
    features = [
    f"{color.capitalize()} {article.capitalize()} for {gender.capitalize()}",
        f"Material: {material}",
        f"Fit: {fit}",
        f"Ideal for {occasion}",
        f"Suitable for {season}"
    ]

    # Specifications
    specs = {
        "Product Name": p.product_display_name or "N/A",
        "Brand": p.brand or "Generic",
    
        # Category Info
        "Master Category": p.master_category or "N/A",
        "Sub Category": p.sub_category or "N/A",
        "Article Type": p.article_type or "N/A",

        # Product Attributes
        "Color": p.base_colour or "N/A",
        "Gender": p.gender or "Unisex",
        "Usage": p.usage_type or "Daily",
        "Season": p.season or "All Seasons",
        "Year": p.year or "N/A",

        # Smart Generated Attributes
        "Material": material,
        "Fit": fit,
        "Occasion": occasion,

        # Pricing
        "Price": f"₹{p.price}" if p.price else "N/A",
        "Discount Price": f"₹{p.discount_price}" if p.discount_price else "N/A",

        # Inventory
        "Stock": p.stock if p.stock is not None else "Out of Stock",
    }
    return {
        "description": description.strip(),
        "highlights": highlights,
        "features": features,
        "specs": specs
    }

@product.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id).first()
    if not product:
        return "Product not found", 404
    details = build_product_details(product)
    return render_template(
        "product_detail.html",
        product=product,
        details=details
    )

def verify_api_key():
    api_key = request.headers.get("X-API-KEY")
    if not api_key:
        return False
    key = APIKey.query.filter_by(api_key=api_key).first()
    return key is not None

@product.route("/api/products")
@limiter.limit("10 per minute")
def get_products():
    # Verify API Key
    if not verify_api_key():
        return {"error": "Invalid API Key"}, 401
    # Pagination
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    if page < 1:
        page = 1
    if limit < 1:
        limit = 20
    if limit > 100:
        limit = 100

    # Filters
    search = request.args.get("search")
    if search:
        search = search.strip()
    category = request.args.get("category")
    gender = request.args.get("gender")
    color = request.args.get("color")
    year = request.args.get("year", type=int)
    query = Product.query

    # search filter
    if search:
        query = query.filter(Product.product_display_name.ilike(f"%{search}%"))

    # category filter
    if category:
        query = query.filter(Product.master_category == category)

    # gender filter
    if gender:
        query = query.filter(Product.gender == gender)

    # color filter
    if color:
        query = query.filter(Product.base_colour == color)

    # year filter
    if year:
        query = query.filter(Product.year == year)

    # Pagination query
    products = query.paginate(page=page, per_page=limit)
    result = []
    for p in products.items:
        result.append({
            "id": p.id,
            "name": p.product_display_name,
            "price": float(p.price) if p.price else None,
            "discount_price": float(p.discount_price) if p.discount_price else None,
            "category": p.master_category,
            "sub_category": p.sub_category,
            "article_type": p.article_type,
            "gender": p.gender,
            "color": p.base_colour,
            "season": p.season,
            "year": p.year,
            "usage": p.usage_type,
            "image_url": url_for("static", filename=p.image_path, _external=True)
        })
    return {
        "page": page,
        "limit": limit,
        "total_products": products.total,
        "total_pages": products.pages,
        "products": result
    }

@product.route("/api/products/<int:product_id>")
@limiter.limit("10 per minute")
def get_product(product_id):
    # verify api key
    if not verify_api_key():
        return {"error": "Invalid API Key"}, 401
    product_data = Product.query.filter_by(id=product_id).first()
    if not product_data:
        return {"error": "Product not found"}, 404
    return {
        "id": product_data.id,
        "name": product_data.product_display_name,
        "category": product_data.master_category,
        "sub_category": product_data.sub_category,
        "article_type": product_data.article_type,
        "gender": product_data.gender,
        "color": product_data.base_colour,
        "season": product_data.season,
        "year": product_data.year,
        "usage": product_data.usage_type,
        "image_url": url_for("static", filename=product_data.image_path, _external=True)
    }

@product.route("/products")
def products_page():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search")
    if search:
        search = search.strip()
    gender = request.args.get("gender")
    category = request.args.get("category")

    # PRICE VALIDATION
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    if min_price is not None and min_price < 0:
        min_price = None
    if max_price is not None and max_price < 0:
        max_price = None
    if min_price == 0:
        min_price = None
    if max_price == 0:
        max_price = None
    if min_price and max_price and min_price > max_price:
        min_price, max_price = max_price, min_price
    sort = request.args.get("sort")
    materials = request.args.getlist("material")
    fits = request.args.getlist("fit")
    occasions = request.args.getlist("occasion")
    query = Product.query

    # SEARCH
    if search:
        query = query.filter(
            or_(
                Product.product_display_name.ilike(f"%{search}%"),
                Product.brand.ilike(f"%{search}%"),
                Product.master_category.ilike(f"%{search}%"),
                Product.sub_category.ilike(f"%{search}%"),
                Product.article_type.ilike(f"%{search}%")
            )
        )

    if gender:
        query = query.filter(
            Product.gender == gender,
            Product.master_category == "Apparel"   # ONLY CLOTHES
        )

    if category:
        query = query.filter(Product.master_category == category)

    # PRICE FILTER
    price_field = func.coalesce(Product.discount_price, Product.price, 0)
    if min_price is not None:
        query = query.filter(price_field >= min_price)
    if max_price is not None:
        query = query.filter(price_field <= max_price)

    # ADVANCED FILTERS
    if materials:
        query = query.filter(
            or_(*[
                Product.product_display_name.ilike(f"%{m}%")
                for m in materials
            ])
        )

    if fits:
        query = query.filter(
            or_(*[
                Product.product_display_name.ilike(f"%{f}%")
                for f in fits
            ])
        )

    if occasions:
        query = query.filter(
            or_(*[
                Product.usage_type.ilike(f"%{o}%")
                for o in occasions
            ])
        )

    # SORTING
    if sort == "price_asc":
        query = query.order_by(func.coalesce(Product.discount_price, Product.price).asc())
    elif sort == "price_desc":
        query = query.order_by(func.coalesce(Product.discount_price, Product.price).desc())
    elif sort == "newest":
        query = query.order_by(Product.created_at.desc())
    elif sort == "stock":
        query = query.order_by(Product.stock.desc())

    # PAGINATION
    products = query.paginate(page=page, per_page=20)
    if page > products.pages and products.pages != 0:
        return redirect(url_for("product.products_page", page=products.pages))
    user = get_current_user()
    return render_template(
        "products.html",
        products=products,
        user=user
    )

@product.route("/category/<gender>")
def category_page(gender):
    page = request.args.get("page", 1, type=int)
    selected_sub = request.args.get("sub_category")
    sort = request.args.get("sort")

    # DETECT ACCESSORIES
    is_accessories = gender.lower() == "accessories"

    # BASE QUERY
    if is_accessories:
        # Accessories → filter by master_category ONLY
        query = Product.query.filter(func.lower(Product.master_category) == "accessories")
    else:
        # Men/Women/etc --> filter by gender and exclude accessories
        query = Product.query.filter(
            Product.gender == gender,
            func.lower(Product.master_category) != "accessories"
        )

    # SUBCATEGORY FILTER
    if selected_sub:
        query = query.filter(Product.sub_category == selected_sub)

    # SORTING
    if sort == "price_asc":
        query = query.order_by(func.coalesce(Product.discount_price, Product.price).asc())
    elif sort == "price_desc":
        query = query.order_by(func.coalesce(Product.discount_price, Product.price).desc())
    elif sort == "newest":
        query = query.order_by(Product.id.desc())

    # PAGINATION
    products = query.paginate(page=page, per_page=12)

    # SUBCATEGORIES
    sub_query = Product.query.with_entities(Product.sub_category)
    if is_accessories:
        sub_query = sub_query.filter(func.lower(Product.master_category) == "accessories")
    else:
        sub_query = sub_query.filter(Product.gender == gender,
            func.lower(Product.master_category) != "accessories"
        )
    subcategories = sub_query.distinct().all()

    # Clean list
    subcategories = [s[0] for s in subcategories if s[0]]
    subcategories = list(set(subcategories))
    subcategories.sort()

    # USER
    user = get_current_user()

    # RENDER
    return render_template(
        "category.html",
        products=products,
        gender=gender,
        subcategories=subcategories,
        selected_sub=selected_sub,
        user=user
    )

@product.route("/api/categories")
def get_categories():
    if not verify_api_key():
        return {"error": "Invalid API Key"}, 401
    rows = Product.query.with_entities(
        Product.gender,
        Product.master_category,
        Product.sub_category
    ).group_by(
        Product.gender,
        Product.master_category,
        Product.sub_category
    ).all()
    categories = {}
    for gender, master, sub in rows:
        if gender not in categories:
            categories[gender] = {}
        if master not in categories[gender]:
            categories[gender][master] = []
        if sub not in categories[gender][master]:
            categories[gender][master].append(sub)
    return {"categories": categories}