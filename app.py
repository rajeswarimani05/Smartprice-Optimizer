import os,re
import secrets

from datetime import datetime
from flask import Flask,jsonify, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_login import (
    LoginManager, login_user, login_required, logout_user,
    current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
import joblib
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-in-production-1234'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'rajemalini2005@gmail.com'      
app.config['MAIL_PASSWORD'] = 'mvns rgpq tmaf kopg'          
app.config['MAIL_DEFAULT_SENDER'] = 'your_email@gmail.com'
app.config["GOOGLE_API_KEY"] = "AIzaSyBXZ4SwuhP08xmPuEw-ZGW8kZ-iCuakdH0"

mail = Mail(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# --- Load ML Model (Optional) ---
MODEL_PATH = os.path.join(BASE_DIR, 'model.pkl')
model = None
if os.path.exists(MODEL_PATH):
    try:
        import joblib
        model = joblib.load(MODEL_PATH)
        print("✅ Loaded model.pkl successfully")
    except Exception as e:
        print("⚠️ Failed loading model:", e)
else:
    print("⚠️ model.pkl not found")

# --- MODELS ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    cashback_balance = db.Column(db.Float, default=0.0)
    total_spent = db.Column(db.Float, default=0.0)
    orders_count = db.Column(db.Integer, default=0)
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    pincode = db.Column(db.String(20))
    phone = db.Column(db.String(20))

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    description = db.Column(db.Text)
    base_price = db.Column(db.Float)
    competitor_price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0)
    demand = db.Column(db.Integer, default=50)
    image = db.Column(db.String(300), default='images/default.jpg')
    category = db.Column(db.String(100), default='General')
    service_center = db.Column(db.Text, default="")


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    qty = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    total_amount = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer)
    qty = db.Column(db.Integer)
    unit_price = db.Column(db.Float)
    final_unit_price = db.Column(db.Float)
    discount_pct = db.Column(db.Float, default=0.0)
    cashback_pct = db.Column(db.Float, default=0.0)

# --- LOGIN MANAGER ---
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User,int(user_id))

SERVICE_KEYWORDS = {
    "laptop": "laptop repair center",
    "computer": "computer repair shop",
    "ac": "air conditioner service center",
    "air conditioner": "air conditioner service center",
    "headphones": "gadget repair service",
    "earphones": "gadget repair service",
    "mobile": "mobile repair shop",
    "phone": "mobile repair shop",
    "refrigerator": "refrigerator repair",
    "fridge": "refrigerator repair",
    "tv": "tv repair service",
}


# --- HELPERS ---
ENFORCE_LOWER_THAN_BASE = True

def get_lat_lng_from_pincode(pincode):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={pincode}&key={app.config['GOOGLE_API_KEY']}"
    response = requests.get(url).json()

    if response["status"] == "OK":
        location = response["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    return None, None

def find_nearby_service_centers(lat, lng, keyword):
    url = (
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        f"?location={lat},{lng}&radius=5000&keyword={keyword}&key={app.config['GOOGLE_API_KEY']}"
    )
    response = requests.get(url).json()

    centers = []
    for place in response.get("results", [])[:5]:  # top 5
        centers.append({
            "name": place.get("name"),
            "address": place.get("vicinity"),
            "lat": place["geometry"]["location"]["lat"],
            "lng": place["geometry"]["location"]["lng"]
        })

    return centers


def optimize_price(product: Product):
    base = float(product.base_price)
    comp = float(product.competitor_price or base)
    demand = float(product.demand or 50)
    stock = float(product.stock or 0)
    if model:
        try:
            pred = float(model.predict([[base, comp, demand, stock]])[0])
        except Exception:
            pred = base * 0.95
    else:
        pred = base * 0.95
    if ENFORCE_LOWER_THAN_BASE and pred >= base:
        pred = base * 0.95
    return round(max(pred, 1.0), 2)

def get_user_type(user: User):
    if not user:
        return "guest"
    if user.orders_count == 0:
        return "new"
    if user.orders_count >= 3:
        return "loyal"
    return "regular"

def apply_offers(user: User, optimized_price: float):
    user_type = get_user_type(user)
    discount_pct, cashback_pct = 0, 0
    if user_type == "new":
        discount_pct = 10
    elif user_type == "loyal":
        discount_pct, cashback_pct = 7, 5
    final_price = optimized_price * (1 - discount_pct / 100.0)
    return {
        "final_price": round(final_price, 2),
        "discount_pct": discount_pct,
        "cashback_pct": cashback_pct
    }
# --- INITIAL SETUP (Flask 3+ compatible) ---
def setup():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email="admin@example.com").first():
            admin = User(
                name="Admin", 
                email="admin@example.com",
                password_hash=generate_password_hash("admin123"),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin user created: admin@example.com / admin123")
        else:
            print("ℹ️ Admin user already exists.")

# Call setup() when the app starts
setup()


# --- ROUTES ---
@app.route("/")
def home():
    products_query = Product.query  

    products = []
    for p in products_query.all():
        optimized = optimize_price(p)
        offer = apply_offers(current_user if current_user.is_authenticated else None, optimized)
        products.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "image": p.image,
            "base_price": p.base_price,
            "optimized_price": optimized,
            "final_price": offer["final_price"],
            "discount_pct": offer["discount_pct"],
            "cashback_pct": offer["cashback_pct"],
            "stock": p.stock
            # category removed completely
        })

    return render_template("products.html", products=products)


# --- REGISTER ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        if not re.match("^[A-Za-z ]+$", name):
          flash("Name must contain only alphabets!", "danger")
          return redirect(url_for('register'))
        email = request.form.get("email")
        password = request.form.get("password")
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))
        u = User(
    name=name,
    email=email,
    password_hash=generate_password_hash(password),
    phone=request.form["phone"],
    address=request.form["address"],
    city=request.form["city"],
    pincode=request.form["pincode"]
)

        db.session.add(u)
        db.session.commit()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# --- LOGIN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        pw = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(pw):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        login_user(user, remember=True)
        flash("Login successful!", "success")
        return redirect(url_for("home"))
    return render_template("login.html")

# --- LOGOUT ---
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        user = User.query.filter_by(email=email).first()

        if user:
            # Create a password reset link
            token = secrets.token_urlsafe(16)
            reset_link = url_for('reset_password', token=token, _external=True)

            # Send email
            msg = Message("Password Reset Request - SmartShop",
                          recipients=[email])
            msg.body = f"Hello {user.name},\n\nClick the link below to reset your password:\n{reset_link}\n\nIf you didn’t request this, ignore this email."
            mail.send(msg)

            flash("A password reset link has been sent to your email.", "info")
        else:
            flash("Email not found!", "danger")

    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if request.method == "POST":
        email = request.form.get("email")
        new_pw = request.form.get("new_password")

        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(new_pw)
            db.session.commit()
            flash("✅ Password reset successful! You can now log in.", "success")
            return redirect(url_for("login"))
        else:
            flash("❌ Invalid email address.", "danger")

    return render_template("reset_password.html", token=token)

def get_service_keyword(category):
    category = category.lower()
    for key, value in SERVICE_KEYWORDS.items():
        if key in category:
            return value
    return "electronics service center"   # fallback

# --- PRODUCT DETAILS ---
@app.route("/product/<int:pid>")
def product(pid):
    p = Product.query.get_or_404(pid)
    user = current_user if current_user.is_authenticated else None
    optimized = optimize_price(p)
    offer = apply_offers(user, optimized)

    # Get keyword based on product category
    keyword = get_service_keyword(p.category.lower())
    user_lat, user_lng = None, None
    centers = []

    if user and user.pincode:
        user_lat, user_lng = get_lat_lng_from_pincode(user.pincode)

        if user_lat and user_lng:
            centers = find_nearby_service_centers(user_lat, user_lng, keyword)


    return render_template(
        "product.html",
        product=p,
        offer=offer,
        centers=centers,
        user_lat=user_lat,
        user_lng=user_lng,
        GOOGLE_API_KEY=app.config["GOOGLE_API_KEY"]
    )

# --- ADD TO CART ---
@app.route("/add_to_cart/<int:pid>", methods=["POST"])
@login_required
def add_to_cart(pid):
    qty = int(request.form.get("qty", 1))
    existing = CartItem.query.filter_by(user_id=current_user.id, product_id=pid).first()
    if existing:
        existing.qty += qty
    else:
        db.session.add(CartItem(user_id=current_user.id, product_id=pid, qty=qty))
    db.session.commit()
    flash("Added to cart!", "success")
    return redirect(url_for("cart"))

@app.route("/remove_from_cart/<int:cart_id>", methods=["POST"])
@login_required
def remove_from_cart(cart_id):
    item = CartItem.query.get(cart_id)
    if item and item.user_id == current_user.id:
        db.session.delete(item)
        db.session.commit()
        flash("Item removed from cart!", "success")
    else:
        flash("Unable to remove item.", "danger")
    return redirect(url_for("cart"))

# --- CART ---
@app.route("/cart")
@login_required
def cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    display, total = [], 0
    for it in items:
        p = Product.query.get(it.product_id)
        optimized = optimize_price(p)
        offer = apply_offers(current_user, optimized)
        final = offer["final_price"]
        display.append({
            "cart_id": it.id,
            "product": p,
            "qty": it.qty,
            "final_price": final
        })
        total += final * it.qty

    cashback_balance = 0  # or your real cashback logic
    return render_template("cart.html", items=display, total=round(total, 2), cashback_balance=cashback_balance)

@app.route("/auto_negotiate/<int:pid>")
@login_required
def auto_negotiate(pid):
    product = Product.query.get_or_404(pid)
    base_price = float(product.base_price)
    demand = float(product.demand or 50)
    stock = float(product.stock or 10)

    # Get optimized base prediction (using your ML model)
    optimized = optimize_price(product)

    # Adjust based on stock and user loyalty
    user_type = get_user_type(current_user)
    extra_discount = 0

    if user_type == "loyal":
        extra_discount = 5
    elif user_type == "regular":
        extra_discount = 2
    elif stock > 30:
        extra_discount += 3  # negotiate more if high stock
    elif demand < 40:
        extra_discount += 2  # low demand, reduce more

    final_offer = optimized * (1 - extra_discount / 100.0)
    discount = base_price - final_offer

    return jsonify({
        "final_price": round(final_offer, 2),
        "discount": round(discount, 2),
        "extra_discount": extra_discount,
        "user_type": user_type
    })

# --- CHECKOUT / PAYMENT ---
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        flash("Your cart is empty!", "warning")
        return redirect(url_for("home"))

    total = 0
    for it in items:
        p = Product.query.get(it.product_id)
        offer = apply_offers(current_user, optimize_price(p))
        total += offer["final_price"] * it.qty

    if request.method == "POST":
        payment_method = request.form.get("payment_method")

        order = Order(user_id=current_user.id, total_amount=total)
        db.session.add(order)
        db.session.commit()

        for it in items:
            p = Product.query.get(it.product_id)
            offer = apply_offers(current_user, optimize_price(p))
            order_item = OrderItem(
                order_id=order.id,
                product_id=p.id,
                qty=it.qty,
                unit_price=p.base_price,
                final_unit_price=offer["final_price"],
                discount_pct=offer["discount_pct"],
                cashback_pct=offer["cashback_pct"]
            )
            db.session.add(order_item)
            p.stock = max(p.stock - it.qty, 0)
        CartItem.query.filter_by(user_id=current_user.id).delete()
        current_user.orders_count += 1
        current_user.total_spent += total
        current_user.cashback_balance += total * (offer["cashback_pct"] / 100.0)
        db.session.commit()

        flash(f"Payment successful via {payment_method}! Thank you for your order.", "success")
        return redirect(url_for("home"))

    return render_template("checkout.html", total=round(total, 2))

# --- ADMIN ADD PRODUCTS ---
@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if not current_user.is_admin:
        flash("Access denied", "danger")
        return redirect(url_for("home"))
    if request.method == "POST":
        data = request.form
        p = Product(   
            name=data["name"],
            description=data["description"],
            base_price=float(data["base_price"]),
            competitor_price=float(data.get("competitor_price", data["base_price"])),
            stock=int(data.get("stock", 0)),
            demand=int(data.get("demand", 50)),
            image=data.get("image", "images/default.jpg"),
            category=data.get("category", "General")
        )
        db.session.add(p)
        db.session.commit()
        flash("Product added successfully!", "success")
        return redirect(url_for("admin"))
    prods = Product.query.all()
    return render_template("admin.html", products=prods)

# --- RUN APP ---
if __name__ == "__main__":
    app.run(debug=True)
