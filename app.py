from flask import Flask, redirect, url_for
from config import Config
from extensions import db, mail, jwt, limiter
from flask_jwt_extended import JWTManager

app = Flask(__name__)
app.config.from_object(Config)
from routes.auth_routes import get_current_user
@app.context_processor
def inject_user():
    user = get_current_user()
    return {
        "user": user,
        "is_logged_in": True if user else False,
        "is_admin": True if user and user.role == "admin" else False
    }

jwt = JWTManager(app)

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return redirect(url_for('auth.login'))

@jwt.unauthorized_loader
def missing_token_callback(error):
    return redirect(url_for('auth.login'))

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return redirect(url_for('auth.login'))

db.init_app(app)    
mail.init_app(app)
jwt.init_app(app)   
limiter.init_app(app)


from routes.product_routes import product
from routes.auth_routes import auth
from routes.cart_routes import cart
from routes.wishlist_routes import wishlist_bp
from routes.admin_routes import admin
from routes.main_routes import main
app.register_blueprint(admin)
app.register_blueprint(wishlist_bp)
app.register_blueprint(auth)
app.register_blueprint(product)
app.register_blueprint(cart)
app.register_blueprint(main)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=False)

