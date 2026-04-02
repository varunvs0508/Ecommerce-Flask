from flask import Blueprint,render_template

main = Blueprint("main", __name__)

from models.models import Product
from sqlalchemy import desc

@main.route("/")
def home():
    featured_products = (
    Product.query
    .filter(Product.master_category == "Apparel")  
    .limit(8)
    .all()
    )
    return render_template("home.html", featured_products=featured_products)