import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import json
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import unquote, quote


import requests
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer

import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)


# ============================================================
# APP CONFIG
# ============================================================

app = Flask(__name__)
app.jinja_env.globals['session'] = session
app.jinja_env.add_extension('jinja2.ext.do')
app.secret_key = os.getenv('SECRET_KEY', 'fallback-dev-key')
app.config['UPLOAD_FOLDER'] = 'static/shoes'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

database_url = os.getenv('DATABASE_URL', 'sqlite:///shopluxe.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
}

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False') == 'True'  # ← ADD THIS
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)


ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'fallback-admin-pass')
MAX_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=5)
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")

# ============================================================
# DATABASE MODELS
# ============================================================

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid4()))
    name = db.Column(db.String, nullable=False)
    price = db.Column(db.String, nullable=False)
    sale_price = db.Column(db.String, nullable=True)
    on_sale = db.Column(db.Boolean, default=False)
    featured = db.Column(db.Boolean, default=False)
    category = db.Column(db.String, default='')
    description = db.Column(db.Text, default='')
    stock = db.Column(db.Integer, default=0)
    colors = db.Column(db.Text, default='[]')
    sizes = db.Column(db.Text, default='[]')
    images = db.Column(db.Text, default='[]')
    popularity = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.String, default='')
    brand = db.Column(db.String(100), default='')
    sku = db.Column(db.String(100), default='')
    tags = db.Column(db.Text, default='[]')
    delivery_info = db.Column(db.String(200), default='Delivery in 2-4 working days')
    new_arrival = db.Column(db.Boolean, default=False)
    vendor_id = db.Column(db.String, db.ForeignKey('vendors.id'), nullable=True)
    product_type = db.Column(db.String, default='standard')  # ✅ NEW
    slot_length = db.Column(db.String, default='')           # ✅ NEW
    slot_width = db.Column(db.String, default='')            # ✅ NEW
    slot_depth = db.Column(db.String, default='')            # ✅ NEW
    new_arrival_until = db.Column(db.String, default='')  # ✅ NEW

    def to_dict(self):
        images = json.loads(self.images or '[]')

        vendor_name = None
        if self.vendor_id:
            vendor = Vendor.query.get(self.vendor_id)
            vendor_name = vendor.shop_name if vendor else None

        return {
            'id': self.id,
            'name': self.name,
            'price': self.price,
            'sale_price': self.sale_price,
            'on_sale': self.on_sale,
            'featured': self.featured,
            'category': self.category,
            'description': self.description,
            'stock': self.stock,
            'colors': json.loads(self.colors or '[]'),
            'sizes': json.loads(self.sizes or '[]'),
            'images': images,
            'image': images[0] if images else None,
            'popularity': self.popularity,
            'timestamp': self.timestamp,
            'brand': self.brand or '',
            'sku': self.sku or '',
            'tags': json.loads(self.tags or '[]'),
            'delivery_info': self.delivery_info or 'Delivery in 2-4 working days',
            'new_arrival': self.new_arrival if self.new_arrival is not None else False,
            'vendor_id': self.vendor_id or None,
            'vendor_name': vendor_name,
            'product_type': self.product_type or 'standard',  # ✅ NEW
            'slot_length': self.slot_length or '',             # ✅ NEW
            'slot_width': self.slot_width or '',               # ✅ NEW
            'slot_depth': self.slot_depth or '',               # ✅ NEW
            'new_arrival_until': self.new_arrival_until or '',  # ✅ NEW
        }
class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, default='')
    email = db.Column(db.String, default='')
    phone = db.Column(db.String, default='')
    address = db.Column(db.String, default='')
    delivery_note = db.Column(db.String, default='')
    amount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    products = db.Column(db.Text, default='[]')
    status = db.Column(db.String, default='Pending')
    payment_status = db.Column(db.String, default='Unpaid')
    timestamp = db.Column(db.String, default='')
    order_time = db.Column(db.String, default='')
    local_time = db.Column(db.String, default='')
    delivered_time = db.Column(db.String, default='')
    cancelled_time = db.Column(db.String, default='')
    completed_time = db.Column(db.String, default='')
    timezone = db.Column(db.String, default='UTC')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'address': self.address or '',
            'delivery_note': self.delivery_note or '',
            'amount': self.amount,
            'total': self.total,
            'products': json.loads(self.products or '[]'),
            'status': self.status,
            'payment_status': self.payment_status,
            'timestamp': self.timestamp,
            'order_time': self.order_time,
            'local_time': self.local_time,
            'delivered_time': self.delivered_time,
            'cancelled_time': self.cancelled_time,
            'completed_time': self.completed_time,
            'timezone': self.timezone
        }


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid4()))
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    reset_token = db.Column(db.String, nullable=True)
    reset_token_expiry = db.Column(db.String, nullable=True)
    address = db.Column(db.String, default='')
    city = db.Column(db.String, default='')
    region = db.Column(db.String, default='')
    delivery_note = db.Column(db.String, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'password': self.password,
            'is_admin': self.is_admin,
            'address': self.address or '',
            'city': self.city or '',
            'region': self.region or '',
            'delivery_note': self.delivery_note or '',
        }
class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.String, default='')
    product_index = db.Column(db.Integer, default=0)
    name = db.Column(db.String, default='')
    comment = db.Column(db.Text, default='')
    rating = db.Column(db.Integer, default=5)
    user_id = db.Column(db.String, default='')
    user_email = db.Column(db.String, default='')
    timestamp = db.Column(db.String, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_index': self.product_index,
            'name': self.name,
            'comment': self.comment,
            'rating': self.rating,
            'user_id': self.user_id,
            'user_email': self.user_email,
            'timestamp': self.timestamp
        }

class RestockRequest(db.Model):
    __tablename__ = 'restock_requests'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String, default='')
    product_name = db.Column(db.String, default='')
    product_id = db.Column(db.String, default='')
    timestamp = db.Column(db.String, default='')

class Vendor(db.Model):
    __tablename__ = 'vendors'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid4()))
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    shop_name = db.Column(db.String, nullable=False)
    shop_description = db.Column(db.Text, default='')
    logo = db.Column(db.String, default='')
    is_approved = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    bank_name = db.Column(db.String, default='')
    bank_account = db.Column(db.String, default='')
    phone = db.Column(db.String, default='')
    timestamp = db.Column(db.String, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'shop_name': self.shop_name,
            'shop_description': self.shop_description,
            'logo': self.logo,
            'is_approved': self.is_approved,
            'is_banned': self.is_banned,
            'bank_name': self.bank_name,
            'bank_account': self.bank_account,
            'phone': self.phone,
            'timestamp': self.timestamp,
        }

class Payout(db.Model):
    __tablename__ = 'payouts'
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid4()))
    vendor_id = db.Column(db.String, db.ForeignKey('vendors.id'), nullable=False)
    order_id = db.Column(db.String, default='')
    amount = db.Column(db.Float, default=0)
    platform_fee = db.Column(db.Float, default=0)
    status = db.Column(db.String, default='Pending')  # Pending, Paid
    timestamp = db.Column(db.String, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'vendor_id': self.vendor_id,
            'order_id': self.order_id,
            'amount': self.amount,
            'platform_fee': self.platform_fee,
            'status': self.status,
            'timestamp': self.timestamp,
        }
        
class Promo(db.Model):
    __tablename__ = 'promos'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(200), nullable=False)
    discount = db.Column(db.Float, default=0)   # e.g. 0.10 for 10%
    flat = db.Column(db.Float, default=0)        # e.g. 50 for GH₵50
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())        

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_data():
    return [p.to_dict() for p in Product.query.all()]

def load_orders():
    now = datetime.now(timezone.utc)
    result = []
    for o in Order.query.all():
        d = o.to_dict()
        if d.get('payment_status') == 'Unpaid' and d.get('timestamp'):
            try:
                order_time = datetime.fromisoformat(d['timestamp'])
                if order_time.tzinfo is None:
                    order_time = order_time.replace(tzinfo=timezone.utc)
                if now - order_time > timedelta(minutes=15):
                    o.status = 'Expired'
                    d['status'] = 'Expired'
                    db.session.commit()
            except Exception:
                pass
        result.append(d)
    return result

def load_reviews():
    return [r.to_dict() for r in Review.query.all()]

def get_all_products():
    return load_data()

def get_products_by_category(category):
    return [p for p in load_data() if p.get('category', '').lower() == category.lower()]

def get_featured_products():
    return [p.to_dict() for p in Product.query.filter_by(featured=True).limit(4).all()]

def get_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']

def get_wishlist():
    if 'wishlist' not in session:
        session['wishlist'] = []
    return session['wishlist']

def get_product_by_id(product_id):
    product = Product.query.get(product_id)
    return product.to_dict() if product else None

def normalize_timestamps(products):
    current_time = datetime.now(timezone.utc)
    for p in products:
        if isinstance(p.get('timestamp'), str):
            try:
                dt = datetime.fromisoformat(p['timestamp'])
                p['timestamp'] = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                p['timestamp'] = current_time
        elif isinstance(p.get('timestamp'), datetime):
            if p['timestamp'].tzinfo is None:
                p['timestamp'] = p['timestamp'].replace(tzinfo=timezone.utc)
        else:
            p['timestamp'] = current_time
    return products

import threading

def send_email(to, subject, html):
    def _send():
        with app.app_context():
            try:
                msg = Message(
                    subject=subject,
                    recipients=[to],
                    html=html,
                    sender=("ShopLuxe", app.config['MAIL_USERNAME'])
                )
                mail.send(msg)
                print(f"✅ Email sent to {to}")
            except Exception as e:
                print(f"❌ Email failed to {to}: {e}")

    threading.Thread(target=_send, daemon=True).start()
    


# ============================================================
# TEMPLATE FILTER
# ============================================================

@app.template_filter('todatetime')
def todatetime_filter(s):
    if isinstance(s, datetime):
        return s.astimezone(timezone.utc)
    if isinstance(s, str):
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None

@app.template_filter('imgurl')
def imgurl_filter(img):
    if not img:
        return url_for('static', filename='shoes/placeholder.jpg')
    if img.startswith('http'):
        return img
    return url_for('static', filename='shoes/' + img)


# ============================================================
# MAIN ROUTES
# ============================================================

@app.route('/')
def home():
    now = datetime.now(timezone.utc)

    # ✅ Auto-expire new_arrival when date passes
    all_products_raw = Product.query.all()
    for p in all_products_raw:
        if p.new_arrival and p.new_arrival_until:
            try:
                until = datetime.fromisoformat(p.new_arrival_until)
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
                if now > until:
                    p.new_arrival = False
                    p.new_arrival_until = ''
            except Exception:
                pass
    db.session.commit()

    all_products = [p.to_dict() for p in all_products_raw]

    # ✅ Most Popular — only products purchased at least once
    popular_products = sorted(
        [p for p in all_products if p.get('popularity', 0) > 0],
        key=lambda p: p.get('popularity', 0), reverse=True
    )[:6]

    # ✅ New Arrivals — only if new_arrival is checked and not expired
    new_products = [p for p in all_products if p.get('new_arrival')][:6]

    # ✅ Featured — only if featured is checked
    featured_products = [p for p in all_products if p.get('featured')][:6]

    # ✅ Sale — only if on_sale is checked
    sale_products = [p for p in all_products if p.get('on_sale')][:6]

    return render_template('index.html',
        popular_products=popular_products,
        new_products=new_products,
        featured_products=featured_products,
        sale_products=sale_products,
        active_page='home'
    )


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('home'))

    products = [p.to_dict() for p in
                Product.query.filter(Product.name.ilike(f'%{q}%')).all()]

    # Still pass the section lists so the carousel still shows
    all_products = [p.to_dict() for p in Product.query.all()]
    popular_products = sorted(all_products, key=lambda p: p.get('popularity', 0), reverse=True)[:10]
    new_products = [p for p in all_products if p.get('new_arrival')][:8]
    featured_products = [p for p in all_products if p.get('featured')][:10]
    sale_products = [p for p in all_products if p.get('on_sale')][:8]

    return render_template('index.html',
        products=products,
        query=q,
        popular_products=popular_products,
        new_products=new_products,
        featured_products=featured_products,
        sale_products=sale_products,
        active_page='home'
    )



@app.route('/live_search')
def live_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    results = Product.query.filter(Product.name.ilike(f'%{q}%')).limit(8).all()
    out = []
    for p in results:
        images = json.loads(p.images) if isinstance(p.images, str) else (p.images or [])
        image_url = images[0] if images else ''
        if image_url and not image_url.startswith('http'):
            image_url = f"/static/shoes/{image_url}"
        out.append({
            'id': p.id,
            'name': p.name,
            'price': p.sale_price if p.on_sale and p.sale_price else p.price,
            'image_url': image_url
        })
    return jsonify(out)

@app.route('/filtered/<category>')
def filtered(category):
    if category == 'Sale':
        products = [p.to_dict() for p in Product.query.filter_by(on_sale=True).all()]
    elif category in ('New Arrivals', 'new'):
        products = [p.to_dict() for p in Product.query.filter_by(new_arrival=True).all()]
    else:
        products = [p.to_dict() for p in Product.query.filter(
            Product.category.ilike(category)).all()]

    return render_template('filtered.html', products=products,
                           category=category, active_page='categories')

@app.route('/shop')
def shop():
    category = request.args.get('category', 'all')
    products = get_all_products() if category.lower() == 'all' else get_products_by_category(category)
    return render_template(
        'shop.html',
        products=products,
        featured_products=get_featured_products(),
        selected_category=category,
        current_time=datetime.now(timezone.utc)
    )

@app.route('/categories')
def categories():
    return render_template('categories.html', active_page='categories')

@app.route('/product/<product_id>')
def product_detail(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("⚠️ Product not found.")
        return redirect(url_for('home'))

    product_dict = product.to_dict()
    products = load_data()
    product_dict['category'] = product_dict.get('category') or 'All'

    related = [
        p for p in products
        if p.get('category', '').lower() == product_dict['category'].lower()
        and p.get('id') != product_id
    ][:4]

    product_reviews = [r.to_dict() for r in Review.query.filter_by(product_id=product_id).all()]

    # ✅ User's rating
    user_rating = None
    if session.get('user_id'):
        existing = Review.query.filter_by(
            product_id=product_id,
            user_id=session['user_id']
        ).first()
        if existing:
            user_rating = existing.rating

    # ✅ Average rating and review count
    all_ratings = [r['rating'] for r in product_reviews if r.get('rating')]
    product_dict['rating'] = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else 0
    product_dict['review_count'] = len(product_reviews)

    # ✅ Stock percentage (max 100)
    product_dict['stock_percentage'] = min(int((product_dict['stock'] / 100) * 100), 100)

    # ✅ RECENTLY VIEWED
    viewed = session.get('recently_viewed', [])
    if product_id in viewed:
        viewed.remove(product_id)
    viewed.insert(0, product_id)
    session['recently_viewed'] = viewed[:10]
    session.modified = True

    return render_template(
        'product_detail.html',
        product=product_dict,
        related=related,
        reviews=product_reviews,
        product_images=product_dict.get('images') or [],
        user_rating=user_rating
    )

@app.route('/settings')
def settings():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    return render_template('settings.html', user=user.to_dict() if user else {})


@app.route('/update_profile', methods=['POST'])
def update_profile():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    action = request.form.get('action')

    if action == 'update_profile':
        user.name = request.form.get('name', '').strip()
        db.session.commit()
        session['user_name'] = user.name
        flash("✅ Profile updated successfully.")

    elif action == 'change_password':
        current = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm = request.form.get('confirm_password')
        if not check_password_hash(user.password, current):
            flash("❌ Current password is incorrect.")
        elif new_pw != confirm:
            flash("❌ New passwords do not match.")
        elif len(new_pw) < 6:
            flash("❌ Password must be at least 6 characters.")
        else:
            user.password = generate_password_hash(new_pw)
            db.session.commit()
            flash("✅ Password updated successfully.")

    # ✅ NEW: Save delivery address
    elif action == 'update_address':
        user.address = request.form.get('address', '').strip()
        user.city = request.form.get('city', '').strip()
        user.region = request.form.get('region', '').strip()
        user.delivery_note = request.form.get('delivery_note', '').strip()
        db.session.commit()
        flash("✅ Delivery address saved.")

    return redirect(url_for('settings'))

@app.route('/delete_account')
def delete_account():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    db.session.delete(user)
    db.session.commit()
    session.clear()
    flash("Your account has been deleted.")
    return redirect(url_for('home'))


@app.route('/support')
def support():
    return render_template('support.html')


@app.route("/healthz")
def health_check():
    return "OK", 200



# ============================================================
# PAYMENT ROUTES
# ============================================================

@app.route('/initialize_payment', methods=['POST'])
def initialize_payment():
    data = request.get_json()
    email = data.get('email')
    reference = str(uuid4())

    pending_order = Order(
        id=str(uuid4()),
        name=data.get("name"),
        email=email,
        phone=data.get("phone"),
        products=json.dumps(data.get("items", [])),
        total=data.get("amount"),
        status="Pending",
        payment_status="Unpaid",
        timestamp=datetime.now(timezone.utc).isoformat(),
        local_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(pending_order)
    db.session.commit()

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "email": email,
        "amount": int(data.get('amount')) * 100,
        "reference": reference,
        "callback_url": url_for('verify_payment', _external=True)
    }
    response = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    return jsonify(response.json())

@app.route('/verify_payment')
def verify_payment():
    reference = request.args.get('reference')
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    result = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers).json()
    payment_data = result.get("data", {})

    if payment_data.get("status") != "success":
        return render_template("failure.html", payment=payment_data)

    customer = payment_data.get("customer", {})
    metadata = payment_data.get("metadata", {})
    name = metadata.get("name") or customer.get("first_name") or "Customer"
    email = metadata.get("email") or customer.get("email")
    phone = metadata.get("phone") or "-"
    amount = payment_data.get("amount", 0) / 100
    items = metadata.get("items", [])
    order_id = reference

    # ✅ Duplicate check first
    if Order.query.get(order_id):
        return redirect(url_for("order_confirmation", reference=order_id))

    # ✅ Stock deduction + admin out-of-stock alert
    for item in items:
        product = Product.query.filter_by(name=item.get("name")).first()
        if product:
            product.stock = max(0, product.stock - int(item.get("quantity", 1)))

            if product.stock == 0:
                try:
                    send_email(
                        "shopluxe374@gmail.com",
                        f"⚠️ Out of Stock Alert — {product.name}",
                        f"""
                        <div style="font-family:sans-serif; padding:20px;">
                            <h2 style="color:#dc3545;">⚠️ Product Out of Stock</h2>
                            <p><strong>{product.name}</strong> is now out of stock.</p>
                            <p>Last order: <strong>{name}</strong> ({email})</p>
                            <p>Please restock as soon as possible.</p>
                            <a href="https://www.shopluxe.online/admin"
                               style="background:#198754;color:#fff;padding:10px 20px;
                               border-radius:8px;text-decoration:none;">
                               Go to Admin Panel
                            </a>
                        </div>
                        """
                    )
                except Exception as e:
                    print("⚠️ Out of stock email failed:", e)

    db.session.commit()

    # ✅ Store effective_price and vendor_id in order items
    enriched_items = []
    for item in items:
        # Pull vendor_id from the product in DB to ensure accuracy
        product = Product.query.filter_by(name=item.get("name")).first()
        enriched_items.append({
            **item,
            'price': item.get('effective_price') or item.get('price', 0),
            'vendor_id': product.vendor_id if product else None,  # ✅ NEW
            'product_id': product.id if product else None,  # ✅ NEW
        })

    address = metadata.get("address", "")
    delivery_note = metadata.get("delivery_note", "")
    new_order = Order(
        id=order_id, name=name, email=email, phone=phone,
        address=address,           # ✅ NEW
        delivery_note=delivery_note,  # ✅ NEW
        amount=amount, total=amount, products=json.dumps(enriched_items),
        status="Paid", payment_status="Paid",
        timestamp=datetime.now(timezone.utc).isoformat(),
        order_time=datetime.now().strftime("%b %d, %Y, %I:%M %p"),
        local_time=datetime.now().strftime("%b %d, %Y, %I:%M %p")
    )
    db.session.add(new_order)
    db.session.commit()

    # ✅ Create payout records per vendor
    vendor_totals = {}
    for item in enriched_items:
        vid = item.get('vendor_id')
        if vid:
            subtotal = float(item.get('price', 0)) * int(item.get('quantity', 1))
            vendor_totals[vid] = vendor_totals.get(vid, 0) + subtotal

    for vid, subtotal in vendor_totals.items():
        fee = round(subtotal * PLATFORM_FEE_PERCENT / 100, 2)
        db.session.add(Payout(
            id=str(uuid4()),
            vendor_id=vid,
            order_id=order_id,
            amount=round(subtotal - fee, 2),
            platform_fee=fee,
            status='Pending',
            timestamp=datetime.now(timezone.utc).isoformat()
        ))
    db.session.commit()
    
    # ✅ Save address to user profile for autofill next time
    if email:
        user = User.query.filter_by(email=email).first()
        if user and address:
            user.address = address
            user.delivery_note = delivery_note
            db.session.commit()

    session.pop('cart', None)

    track_order_url = url_for("track_order", order_id=order_id, _external=True)
    product_list = "".join(
        f"<p>{i['name']} ({i.get('quantity', 1)}x) — GH₵ {i.get('price', 0)}</p>"
        for i in enriched_items
    )
    order_time_str = datetime.now().strftime("%b %d, %Y, %I:%M %p")

    try:
        send_email("shopluxe374@gmail.com", "📦 New Paid Order - ShopLuxe",
                   render_template("emails/admin_order_email.html", name=name, email=email,
                                   phone=phone, product_name=product_list, total=amount,
                                   order_time=order_time_str, track_order_url=track_order_url))
        send_email(email, "✅ Payment Received - ShopLuxe",
                   render_template("emails/user_order_email.html", name=name,
                                   product_name=product_list, total=amount,
                                   order_time=order_time_str, track_order_url=track_order_url))
    except Exception as e:
        print("⚠️ Email sending failed:", e)

    return redirect(url_for("order_confirmation", reference=order_id))

@app.route('/order_confirmation')
def order_confirmation():
    order = Order.query.get(request.args.get("reference"))
    if not order:
        flash("⚠️ Order not found.")
        return redirect(url_for('cart'))
    return render_template("order_confirmation.html", order=order.to_dict())


@app.route('/track-order/<order_id>')
def track_order(order_id):
    order = Order.query.get(unquote(order_id))
    if not order:
        flash("⚠️ Order not found.")
        return redirect(url_for('home'))

    all_products = {p.name.lower(): p.to_dict() for p in Product.query.all()}

    return render_template("track_order.html", order=order.to_dict(), all_products=all_products)
@app.route('/orders')
def orders():
    if not session.get('user_email'):
        flash("❌ Please login first.")
        return redirect(url_for('login'))

    user_orders = [o.to_dict() for o in Order.query.filter_by(email=session['user_email']).all()]
    for order in user_orders:
        order['local_time'] = order.get('local_time') or order.get('order_time', 'N/A')
        if not order.get('products'):
            order['products'] = [{'name': 'Unknown Product', 'price': order.get('total', 0),
                                   'quantity': 1, 'color': '-', 'size': '-'}]
    return render_template("orders.html", orders=user_orders)


# ============================================================
# ADMIN ROUTES
# ============================================================

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    now = datetime.now(timezone.utc)
    attempts = session.get('admin_attempts', 0)
    locked_until = session.get('admin_locked_until')

    if locked_until:
        locked_time = datetime.fromisoformat(locked_until)
        if now < locked_time:
            minutes_left = int((locked_time - now).total_seconds() // 60 + 1)
            flash(f"⛔ Too many failed attempts. Try again in {minutes_left} minute(s).")
            return render_template('admin_login.html')
        session.pop('admin_locked_until', None)
        session['admin_attempts'] = 0

    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session['admin_attempts'] = 0
            session.pop('admin_locked_until', None)
            return redirect(url_for('admin'))
        else:
            session['admin_attempts'] = attempts + 1
            if session['admin_attempts'] >= MAX_ATTEMPTS:
                session['admin_locked_until'] = (now + LOCKOUT_DURATION).isoformat()
                flash("🚫 Too many failed attempts. You're locked out for 5 minutes.")
            else:
                flash(f"❌ Incorrect password. {MAX_ATTEMPTS - session['admin_attempts']} attempt(s) remaining.")

    return render_template('admin_login.html')


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip().title()
        price = request.form.get('price', '0').strip()
        on_sale = 'on_sale' in request.form
        sale_price = request.form.get('sale_price', '').strip() or None
        featured = 'featured' in request.form
        new_arrival = 'new_arrival' in request.form

        category = request.form.get('category', '')
        if category == 'custom':
            category = request.form.get('category_custom', '').strip().title()

        description = request.form.get('description', '').strip()
        stock = int(request.form.get('stock', 0))
        brand = request.form.get('brand', '').strip()
        sku = request.form.get('sku', '').strip()
        delivery_info = request.form.get('delivery_info', 'Delivery in 2-4 working days').strip()
        tags = json.dumps([t.strip() for t in request.form.get('tags', '').split(',') if t.strip()])

        product_type = request.form.get('product_type', 'standard')
        slot_length = request.form.get('slot_length', '').strip()
        slot_width = request.form.get('slot_width', '').strip()
        slot_depth = request.form.get('slot_depth', '').strip()

        if product_type == 'standard':
            sizes = json.dumps([s.strip() for s in request.form.get('sizes', '').split(',') if s.strip()])
        else:
            sizes = json.dumps([])

        colors = json.dumps([c.strip() for c in request.form.get('colors', '').split(',') if c.strip()])

        images = request.files.getlist('images')
        image_filenames = []
        for img in images:
            if img and img.filename:
                upload_result = cloudinary.uploader.upload(img)
                image_filenames.append(upload_result['secure_url'])

        new_arrival_until = ''
        if new_arrival:
            new_arrival_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        new_product = Product(
            name=name, price=price, on_sale=on_sale, sale_price=sale_price,
            featured=featured, category=category, description=description,
            stock=stock, sizes=sizes, colors=colors,
            images=json.dumps(image_filenames),
            brand=brand, sku=sku, tags=tags,
            delivery_info=delivery_info, new_arrival=new_arrival,
            new_arrival_until=new_arrival_until,
            product_type=product_type,
            slot_length=slot_length,
            slot_width=slot_width,
            slot_depth=slot_depth,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        db.session.add(new_product)
        db.session.commit()
        flash("✅ Product added successfully!")
        return redirect(url_for('admin'))

    products = [p.to_dict() for p in Product.query.order_by(Product.timestamp.desc()).all()]
    orders = [o.to_dict() for o in Order.query.order_by(Order.timestamp.desc()).all()]
    promos = {p.code: {'label': p.label, 'discount': p.discount, 'flat': p.flat, 'active': p.active}
              for p in Promo.query.order_by(Promo.created_at.desc()).all()}
    return render_template('admin.html', products=products, orders=orders, promos=promos, active_page='admin')
  
@app.route('/delete/<product_id>', methods=['POST'])
def delete(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    product = Product.query.get(product_id)
    if not product:
        flash("❌ Product not found.")
        return redirect(url_for('admin'))

    for img in json.loads(product.images or '[]'):
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(product)
    db.session.commit()
    flash("🗑️ Product deleted.")
    return redirect(url_for('admin'))


@app.route('/edit/<product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    product = Product.query.get(product_id)
    if not product:
        flash("❌ Product not found.")
        return redirect(url_for('admin'))

    if request.method == 'POST':
        old_stock = product.stock

        product.name = request.form.get('name', '').strip().title()
        product.brand = request.form.get('brand', '').strip()
        product.sku = request.form.get('sku', '').strip()
        product.description = request.form.get('description', '').strip()
        product.delivery_info = request.form.get('delivery_info', 'Delivery in 2-4 working days').strip()

        category = request.form.get('category')
        if category == 'custom':
            category = request.form.get('category_custom', '').strip().title()
        product.category = category

        product.price = request.form.get('price', '').strip()
        product.sale_price = request.form.get('sale_price', '').strip() or None
        product.on_sale = 'on_sale' in request.form
        product.featured = 'featured' in request.form
        product.new_arrival = 'new_arrival' in request.form

        product.stock = int(request.form.get('stock', 0))
        
        product.new_arrival = 'new_arrival' in request.form
        if product.new_arrival:
            product.new_arrival_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        else:
            product.new_arrival_until = ''

        # ✅ Dimension / size type fields
        product_type = request.form.get('product_type', 'standard')
        product.product_type = product_type
        if product_type == 'standard':
            sizes_raw = request.form.get('sizes', '')
            product.sizes = json.dumps([s.strip() for s in sizes_raw.split(',') if s.strip()])
        else:
            product.sizes = json.dumps([])
            product.slot_length = request.form.get('slot_length', '').strip()
            product.slot_width = request.form.get('slot_width', '').strip()
            product.slot_depth = request.form.get('slot_depth', '').strip()

        colors_raw = request.form.get('colors', '')
        product.colors = json.dumps([c.strip() for c in colors_raw.split(',') if c.strip()])

        tags_raw = request.form.get('tags', '')
        product.tags = json.dumps([t.strip() for t in tags_raw.split(',') if t.strip()])

        remove_images = request.form.getlist('remove_images')
        existing_images = json.loads(product.images or '[]')
        kept_images = [img for img in existing_images if img not in remove_images]

        new_images = request.files.getlist('new_images')
        for file in new_images:
           if file and file.filename:
               upload_result = cloudinary.uploader.upload(file)   # ← fix: use 'file'
               kept_images.append(upload_result['secure_url'])    # ← fix: append to kept_images
        product.images = json.dumps(kept_images)
        product.timestamp = datetime.now(timezone.utc).isoformat()
        db.session.commit()

        if old_stock == 0 and product.stock > 0:
            waitlist = RestockRequest.query.filter_by(product_id=product.id).all()
            for req in waitlist:
                try:
                    send_email(req.email, f"✅ Back in Stock — {product.name}",
                        f"""<div style="font-family:sans-serif;padding:20px;">
                        <h2 style="color:#198754;">Good news! 🎉</h2>
                        <p><strong>{product.name}</strong> is back in stock.</p>
                        <a href="https://www.shopluxe.online/product/{product.id}"
                        style="background:#198754;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;">
                        Shop Now</a></div>""")
                except Exception as e:
                    print("⚠️ Restock alert failed:", e)
            RestockRequest.query.filter_by(product_id=product.id).delete()
            db.session.commit()

        flash("✅ Product updated successfully!")
        return redirect(url_for('admin'))

    return render_template('edit_product.html', product=product.to_dict())

@app.route('/mark_delivered/<order_id>', methods=['POST'])
def mark_delivered(order_id):
    order = Order.query.get(order_id)
    if not order:
        flash("⚠️ Order not found.")
        return redirect(url_for('admin'))

    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order.status = 'Delivered'
    order.delivered_time = local_time
    order.completed_time = local_time
    db.session.commit()

    try:
        items = json.loads(order.products or '[]')
        send_email(order.email, "✅ Your Order Has Been Delivered - ShopLuxe",
                   render_template('emails/user_delivered_email.html',
                                   name=order.name,
                                   items=items,           # ✅ pass as list not HTML string
                                   total=order.total,
                                   order_time=order.local_time))
        flash("✅ Order marked delivered and email sent to user.")
    except Exception as e:
        print("❌ Email sending failed:", e)
        flash("⚠️ Order marked delivered but email could not be sent.")

    return redirect(url_for('admin'))


@app.route('/cancel_order/<order_id>', methods=['POST'])
def cancel_order(order_id):
    order = Order.query.get(order_id)
    if not order:
        flash("❌ Order not found.")
        return redirect(url_for('admin'))

    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order.status = 'Cancelled'
    order.cancelled_time = local_time
    order.completed_time = local_time
    db.session.commit()

    try:
        send_email(order.email, "❌ Your ShopLuxe Order Has Been Cancelled",
                   render_template('emails/order_cancelled_email.html', name=order.name,
                                   order_id=order_id,
                                   track_order_url=url_for('track_order', order_id=quote(order_id), _external=True)))
        flash("✅ Order cancelled and email sent to user.")
    except Exception as e:
        print("❌ Order cancelled but email could not be sent:", e)
        flash("⚠️ Order cancelled but email could not be sent.")

    return redirect(url_for('admin'))


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not name or not email or not password:
            flash("❌ All fields are required.")
            return redirect(url_for('signup'))
        if User.query.filter_by(email=email).first():
            flash("❌ Email already registered.")
            return redirect(url_for('signup'))

        db.session.add(User(id=str(uuid4()), name=name, email=email,
                            password=generate_password_hash(password)))
        db.session.commit()

        try:
            send_email(
                email,
                "🎉 Welcome to ShopLuxe!",
                f"""
                <div style="font-family:sans-serif; padding:20px; max-width:500px;">
                    <h2 style="color:#198754;">Welcome to ShopLuxe, {name}! 🛍️</h2>
                    <p>Thanks for creating an account. You can now track orders, save wishlists, and check out faster.</p>
                    <a href="https://www.shopluxe.online/shop"
                       style="background:#198754;color:#fff;padding:12px 24px;
                       border-radius:8px;text-decoration:none;display:inline-block;font-weight:bold;">
                       Start Shopping
                    </a>
                    <p style="color:#999;font-size:12px;margin-top:20px;">ShopLuxe Team</p>
                </div>
                """
            )
        except Exception as e:
            print("Welcome email failed:", e)

        flash("✅ Account created. Please log in.")
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session.clear()
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_email'] = user.email
            session['is_admin'] = user.is_admin

            # ✅ Set vendor session if approved
            vendor = Vendor.query.filter_by(user_id=user.id).first()
            if vendor and vendor.is_approved and not vendor.is_banned:
                session['vendor_id'] = vendor.id
                session['shop_name'] = vendor.shop_name

            flash("✅ Logged in successfully.")
            return redirect(url_for('profile'))

        flash("❌ Invalid credentials.")
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("👋 Logged out.")
    return redirect(url_for('home'))  # ✅ changed 'index' to 'home'



@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()

        if user:
            # Generate token
            token = str(uuid4())
            user.reset_token = token
            user.reset_token_expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            db.session.commit()

            reset_url = url_for('reset_password', token=token, _external=True)

            try:
                send_email(
                    email,
                    "🔑 Reset Your ShopLuxe Password",
                    f"""
                    <div style="font-family:sans-serif; padding:20px; max-width:500px;">
                        <h2 style="color:#198754;">Reset Your Password</h2>
                        <p>Hi {user.name}, click the button below to reset your password.</p>
                        <a href="{reset_url}"
                           style="background:#198754;color:#fff;padding:12px 24px;
                           border-radius:8px;text-decoration:none;display:inline-block;
                           font-weight:bold;">
                           Reset Password
                        </a>
                        <p style="color:#999;font-size:12px;margin-top:20px;">
                           This link expires in 30 minutes. If you didn't request this, ignore this email.
                        </p>
                    </div>
                    """
                )
            except Exception as e:
                print("⚠️ Reset email failed:", e)

        # ✅ Always flash success even if email not found (security best practice)
        flash("If that email exists, a reset link has been sent.")
        return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()

    # ✅ Check token exists and not expired
    if not user or not user.reset_token_expiry:
        flash("❌ Invalid or expired reset link.")
        return redirect(url_for('forgot_password'))

    expiry = datetime.fromisoformat(user.reset_token_expiry)
    if datetime.now(timezone.utc) > expiry:
        flash("❌ Reset link has expired. Please request a new one.")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if password != confirm:
            flash("❌ Passwords do not match.")
            return redirect(url_for('reset_password', token=token))

        if len(password) < 6:
            flash("❌ Password must be at least 6 characters.")
            return redirect(url_for('reset_password', token=token))

        # ✅ Update password and clear token
        user.password = generate_password_hash(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()

        flash("✅ Password reset successfully. Please log in.")
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)  
  


@app.route('/reset_with_token/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    try:
        email = serializer.loads(token, salt='reset-password', max_age=1800)
    except Exception:
        flash("❌ Reset link expired or invalid.")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password')
        if not new_password:
            flash("❌ Please enter a new password.")
            return redirect(url_for('reset_with_token', token=token))

        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash("✅ Password reset successful. Please log in.")
            return redirect(url_for('login'))

        flash("❌ User not found.")
        return redirect(url_for('login'))

    return render_template('reset_with_token.html')


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        flash("⚠️ Please log in first.")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        flash("⚠️ User not found.")
        return redirect(url_for('login'))

    user_orders = Order.query.filter_by(email=user.email).all()
    user_reviews = Review.query.filter_by(user_email=user.email).all()
    user_stats = {
        "orders": len(user_orders),
        "reviews": len(user_reviews),
        "spent": sum(o.total or 0 for o in user_orders)
    }

    if request.method == 'POST':
        if not check_password_hash(user.password, request.form.get('current_password')):
            flash("❌ Incorrect current password.")
            return redirect(url_for('profile'))

        user.name = request.form.get('name') or user.name
        new_password = request.form.get('password')
        if new_password:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        session['user_name'] = user.name
        flash("✅ Profile updated successfully.")
        return redirect(url_for('profile'))

    return render_template('profile.html', user=user.to_dict(), stats=user_stats)

# ============================================================
# CART ROUTES
# ============================================================

@app.route('/add_to_cart/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("❌ Product not found.")
        return redirect(request.referrer or url_for('home'))

    # ✅ Block out-of-stock
    if product.stock <= 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '❌ This product is out of stock.'})
        flash("❌ This product is out of stock.")
        return redirect(request.referrer or url_for('home'))

    quantity = int(request.form.get("quantity", 1))
    color = request.form.get("color", "-")
    size = request.form.get("size", "-")
    cart = get_cart()

    for item in cart:
        if item['product_id'] == product_id and item.get('color') == color and item.get('size') == size:
            item['quantity'] += quantity
            break
    else:
        cart.append({'product_id': product_id, 'quantity': quantity, 'color': color, 'size': size})

    session['cart'] = cart

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': '🛒 Added to cart!', 'count': len(cart)})

    flash("🛒 Product added to cart!")
    return redirect(request.referrer or url_for('home'))


@app.route('/add_to_cart_ajax/<product_id>', methods=['POST'])
def add_to_cart_ajax(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': '❌ Product not found.'})

    # ✅ Block out-of-stock
    if product.stock <= 0:
        return jsonify({'success': False, 'message': '❌ This product is out of stock.'})

    color = request.form.get("color", "-")
    size = request.form.get("size", "-")
    cart = session.get('cart', [])

    found = next((i for i in cart if i['product_id'] == product_id
                  and i.get('color') == color and i.get('size') == size), None)
    if found:
        found['quantity'] += 1
        message = "➕ Increased quantity in cart!"
    else:
        cart.append({'product_id': product_id, 'quantity': 1, 'color': color, 'size': size})
        message = "🛒 Added to cart!"

    session['cart'] = cart
    return jsonify({'success': True, 'message': message, 'count': len(cart)})


@app.route('/cart')
def cart():
    cart_items = []
    for item in get_cart():
        product = Product.query.get(item.get("product_id"))
        if not product:
            continue
        p = product.to_dict()
        p['quantity'] = item.get('quantity', 1)
        p['color'] = item.get('color', '-')
        p['size'] = item.get('size', '-')
        p['effective_price'] = float(p['sale_price']) if p.get('on_sale') and p.get('sale_price') else float(p['price'])
        cart_items.append(p)

    subtotal = sum(p['effective_price'] * p['quantity'] for p in cart_items)
    payout_fee = round(min((subtotal * 0.0195) + 0.50, 500), 2)
    total = round(subtotal + payout_fee, 2)

    promo = session.get('promo')
    discount = 0
    if promo:
        if promo.get('flat') and promo['flat'] > 0:
            discount = promo['flat']
        elif promo.get('discount') and promo['discount'] > 0:
            discount = round(subtotal * promo['discount'], 2)

    discounted_total = round(max(0, subtotal + payout_fee - discount), 2)

    return render_template('cart.html',
        cart_items=cart_items,
        subtotal=subtotal,
        payout_fee=payout_fee,
        total=total,
        discount=discount,
        discounted_total=discounted_total,
        promo=promo,
        active_page='cart'
    )

@app.route('/clear-cart')
def clear_cart():
    session['cart'] = []
    return redirect(url_for('cart'))


@app.route('/cart/increase/<product_id>')
def increase_quantity(product_id):
    cart = get_cart()
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += 1
            break
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/cart/decrease/<product_id>')
def decrease_quantity(product_id):
    cart = get_cart()
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] -= 1
            if item['quantity'] < 1:
                cart.remove(item)
            break
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/cart/remove/<product_id>')
def remove_from_cart(product_id):
    cart = [i for i in get_cart() if i['product_id'] != product_id]
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/cart_count')
def cart_count():
    return jsonify({'count': len(session.get('cart', []))})


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = []
    for item in get_cart():
        product = Product.query.get(item.get("product_id"))
        if not product:
            continue
        p = product.to_dict()
        p['quantity'] = item.get('quantity', 1)
        p['color'] = item.get('color', '-')
        p['size'] = item.get('size', '-')
        p['effective_price'] = float(p['sale_price']) if p.get('on_sale') and p.get('sale_price') else float(p['price'])
        cart_items.append(p)

    if not cart_items:
        flash("⚠️ Your cart is empty.")
        return redirect(url_for("cart"))

    # ✅ Validate stock before checkout
    for item in cart_items:
        product = Product.query.get(item.get('id'))
        if product and product.stock <= 0:
            flash(f"❌ '{product.name}' is out of stock. Please remove it from your cart.")
            return redirect(url_for('cart'))

    subtotal = sum(p['effective_price'] * p['quantity'] for p in cart_items)
    payout_fee = round(min((subtotal * 0.0195) + 0.50, 500), 2)
    total = round(subtotal + payout_fee, 2)

    # ✅ Load saved address for autofill
    saved_address = {}
    if session.get('user_id'):
        user = User.query.get(session['user_id'])
        if user:
            saved_address = {
                'address': user.address or '',
                'city': user.city or '',
                'region': user.region or '',
                'delivery_note': user.delivery_note or '',
            }

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        subtotal=subtotal,
        payout_fee=payout_fee,
        total=total,
        paystack_public_key=PAYSTACK_PUBLIC_KEY,
        saved_address=saved_address
    )
# ============================================================
# WISHLIST ROUTES
# ============================================================

def get_wishlist():
    """Returns full product dicts for wishlisted items."""
    raw = session.get('wishlist', [])
    result = []
    for item in raw:
        product = Product.query.get(item.get('id'))
        if product:
            result.append(product.to_dict())
    return result


@app.route('/add_to_wishlist/<product_id>')
def add_to_wishlist(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("❌ Product not found.")
        return redirect(request.referrer or url_for('home'))

    wishlist = session.get('wishlist', [])
    if any(p['id'] == product_id for p in wishlist):
        flash("❤️ Already in your wishlist.")
        return redirect(request.referrer or url_for('wishlist'))

    wishlist.append({'id': product_id})
    session['wishlist'] = wishlist
    flash("💖 Added to your wishlist!")
    return redirect(request.referrer or url_for('wishlist'))


@app.route('/toggle_wishlist_ajax/<product_id>', methods=['POST'])
def toggle_wishlist_ajax(product_id):
    wishlist = session.get('wishlist', [])
    in_wishlist = any(p['id'] == product_id for p in wishlist)

    if in_wishlist:
        wishlist = [p for p in wishlist if p['id'] != product_id]
        message = "💔 Removed from wishlist."
        in_wishlist = False
    else:
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'success': False, 'message': '❌ Product not found.'})
        wishlist.append({'id': product_id})
        message = "💖 Added to wishlist!"
        in_wishlist = True

    session['wishlist'] = wishlist
    return jsonify({'success': True, 'in_wishlist': in_wishlist,
                    'message': message, 'count': len(wishlist)})


@app.route('/wishlist')
def wishlist():
    return render_template('wishlist.html', wishlist=get_wishlist(), active_page='wishlist')


@app.route('/remove_from_wishlist/<product_id>')
def remove_from_wishlist(product_id):
    session['wishlist'] = [p for p in session.get('wishlist', [])
                           if p.get('id') != product_id]
    flash("❌ Removed from wishlist.")
    return redirect(url_for('wishlist'))


@app.route('/clear_wishlist')
def clear_wishlist():
    session['wishlist'] = []
    return redirect(url_for('wishlist'))


@app.route('/wishlist_count')
def wishlist_count():
    return jsonify({'count': len(session.get('wishlist', []))})


# ============================================================
# REVIEW & RATING ROUTES
# ============================================================

@app.route('/rate-product', methods=['POST'])
def rate_product():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"})

    data = request.get_json()
    product_id = data.get('product_id')
    rating = int(data.get('rating', 0))

    if not product_id or rating not in range(1, 6):
        return jsonify({"success": False, "message": "Invalid data"})

    # ✅ Always update existing, never create duplicate
    existing = Review.query.filter_by(
        product_id=product_id,
        user_id=session['user_id']
    ).first()

    if existing:
        existing.rating = rating
        existing.timestamp = datetime.now(timezone.utc).isoformat()
    else:
        db.session.add(Review(
            product_id=product_id,
            user_id=session['user_id'],
            user_email=session.get('user_email', ''),
            name=session.get('user_name', 'Anonymous'),
            rating=rating,
            timestamp=datetime.now(timezone.utc).isoformat()
        ))

    db.session.commit()
    return jsonify({"success": True})


@app.route('/submit_review/<product_id>', methods=['POST'])
def submit_review(product_id):
    if not session.get('user_id'):
        flash("❌ Please log in to submit a review.")
        return redirect(url_for('login'))

    comment = request.form.get('comment', '').strip()
    rating = int(request.form.get('rating', 0))

    if not comment or rating not in range(1, 6):
        flash("❌ Please select a rating and write a comment.")
        return redirect(url_for('product_detail', product_id=product_id))

    # ✅ Always update existing, never create duplicate
    existing = Review.query.filter_by(
        product_id=product_id,
        user_id=session['user_id']
    ).first()

    if existing:
        existing.rating = rating
        existing.comment = comment
        existing.name = session.get('user_name', existing.name)
        existing.timestamp = datetime.now(timezone.utc).isoformat()
    else:
        db.session.add(Review(
            product_id=product_id,
            name=session.get('user_name', 'Anonymous'),
            comment=comment,
            rating=rating,
            user_id=session['user_id'],
            user_email=session.get('user_email', ''),
            timestamp=datetime.now(timezone.utc).isoformat()
        ))

    db.session.commit()
    flash("✅ Review submitted!")
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/restock_notify/<product_id>', methods=['POST'])
def restock_notify(product_id):
    email = request.form.get('email', '').strip()
    product = Product.query.get(product_id)

    if not email or not product:
        flash("❌ Something went wrong.")
        return redirect(url_for('product_detail', product_id=product_id))

    # Save request to DB
    existing = RestockRequest.query.filter_by(
        product_id=product_id, email=email
    ).first()

    if not existing:
        db.session.add(RestockRequest(
            product_id=product_id,
            email=email,
            timestamp=datetime.now(timezone.utc).isoformat()
        ))
        db.session.commit()

    # Confirm email to user
    try:
        send_email(
            email,
            "🔔 You're on the waitlist — ShopLuxe",
            f"""
            <div style="font-family:sans-serif; padding:20px;">
                <h2 style="color:#198754;">You're on the list!</h2>
                <p>We'll notify you as soon as <strong>{product.name}</strong> is back in stock.</p>
                <p>Thanks for shopping with ShopLuxe 🛍️</p>
            </div>
            """
        )
    except Exception as e:
        print("⚠️ Restock notify email failed:", e)

    flash("✅ We'll notify you when it's back in stock!")
    return redirect(url_for('product_detail', product_id=product_id))


from authlib.integrations.flask_client import OAuth

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@app.route('/auth/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')

    if not user_info:
        flash("❌ Google login failed.")
        return redirect(url_for('login'))

    email = user_info['email']
    name = user_info.get('name', email.split('@')[0])

    # ✅ Find or create user
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            id=str(uuid4()),
            name=name,
            email=email,
            password=generate_password_hash(str(uuid4())),
            is_admin=False
        )
        db.session.add(user)
        db.session.commit()

    session.clear()
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['user_email'] = user.email
    session['is_admin'] = user.is_admin

    # ✅ Set vendor session if approved
    vendor = Vendor.query.filter_by(user_id=user.id).first()
    if vendor and vendor.is_approved and not vendor.is_banned:
        session['vendor_id'] = vendor.id
        session['shop_name'] = vendor.shop_name

    flash(f"✅ Welcome, {user.name}!")
    return redirect(url_for('profile'))

@app.route('/admin/vendors')
def admin_vendors():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    vendors = Vendor.query.order_by(Vendor.timestamp.desc()).all()
    vendor_list = []
    for v in vendors:
        user = User.query.get(v.user_id)
        product_count = Product.query.filter_by(vendor_id=v.id).count()
        vendor_list.append({
            **v.to_dict(),
            'user_name': user.name if user else 'Unknown',
            'user_email': user.email if user else 'Unknown',
            'product_count': product_count,
        })

    return render_template('admin_vendors.html', vendors=vendor_list)


@app.route('/admin/approve-vendor/<vendor_id>', methods=['POST'])
def approve_vendor(vendor_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    vendor = Vendor.query.get(vendor_id)
    if not vendor:
        flash("❌ Vendor not found.")
        return redirect(url_for('admin_vendors'))

    vendor.is_approved = True
    vendor.is_banned = False
    db.session.commit()

    # Notify vendor
    user = User.query.get(vendor.user_id)
    if user:
        try:
            send_email(
                user.email,
                "✅ Your ShopLuxe Vendor Account is Approved!",
                f"""
                <div style="font-family:sans-serif; padding:20px;">
                    <h2 style="color:#198754;">Congratulations! 🎉</h2>
                    <p>Hi {user.name}, your vendor account <strong>{vendor.shop_name}</strong>
                       has been approved.</p>
                    <p>You can now log in and start listing your products.</p>
                    <a href="https://www.shopluxe.online/become-vendor"
                       style="background:#198754;color:#fff;padding:10px 20px;
                       border-radius:8px;text-decoration:none;">
                       Go to Your Dashboard
                    </a>
                </div>
                """
            )
        except Exception as e:
            print("⚠️ Vendor approval email failed:", e)

    flash(f"✅ {vendor.shop_name} approved.")
    return redirect(url_for('admin_vendors'))


@app.route('/admin/ban-vendor/<vendor_id>', methods=['POST'])
def ban_vendor(vendor_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    vendor = Vendor.query.get(vendor_id)
    if not vendor:
        flash("❌ Vendor not found.")
        return redirect(url_for('admin_vendors'))

    vendor.is_banned = True
    vendor.is_approved = False
    db.session.commit()
    flash(f"⛔ {vendor.shop_name} has been banned.")
    return redirect(url_for('admin_vendors'))
  
@app.route('/become-vendor', methods=['GET', 'POST'])
def become_vendor():
    if not session.get('user_id'):
        flash("❌ Please log in first.")
        return redirect(url_for('login'))

    existing = Vendor.query.filter_by(user_id=session['user_id']).first()
    if existing:
        if existing.is_approved and not existing.is_banned:
            # ✅ Refresh session in case they were approved after login
            session['vendor_id'] = existing.id
            session['shop_name'] = existing.shop_name
            return redirect(url_for('vendor_dashboard'))
        elif existing.is_banned:
            flash("⛔ Your vendor account has been banned.")
            return redirect(url_for('home'))
        else:
            flash("⏳ Your vendor application is pending admin approval.")
            return render_template('vendor_pending.html')

    if request.method == 'POST':
        shop_name = request.form.get('shop_name', '').strip()
        shop_description = request.form.get('shop_description', '').strip()
        phone = request.form.get('phone', '').strip()
        bank_name = request.form.get('bank_name', '').strip()
        bank_account = request.form.get('bank_account', '').strip()

        if not shop_name:
            flash("❌ Shop name is required.")
            return redirect(url_for('become_vendor'))

        logo_filename = ''
        logo = request.files.get('logo')
        if logo and logo.filename:
            logo_filename = secure_filename(logo.filename)
            logo.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))

        new_vendor = Vendor(
            id=str(uuid4()),
            user_id=session['user_id'],
            shop_name=shop_name,
            shop_description=shop_description,
            phone=phone,
            bank_name=bank_name,
            bank_account=bank_account,
            logo=logo_filename,
            is_approved=False,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        db.session.add(new_vendor)
        db.session.commit()

        try:
            send_email(
                "shopluxe374@gmail.com",
                "🛍️ New Vendor Application — ShopLuxe",
                f"""
                <div style="font-family:sans-serif; padding:20px;">
                    <h2>New Vendor Application</h2>
                    <p><strong>Shop:</strong> {shop_name}</p>
                    <p><strong>User:</strong> {session.get('user_name')} ({session.get('user_email')})</p>
                    <p><strong>Phone:</strong> {phone}</p>
                    <a href="https://www.shopluxe.online/admin/vendors"
                       style="background:#198754;color:#fff;padding:10px 20px;
                       border-radius:8px;text-decoration:none;">
                       Review Application
                    </a>
                </div>
                """
            )
        except Exception as e:
            print("⚠️ Vendor application email failed:", e)

        flash("✅ Application submitted! We'll review and get back to you.")
        return render_template('vendor_pending.html')

    return render_template('become_vendor.html')

@app.route('/admin/payouts')
def admin_payouts():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    payouts = Payout.query.order_by(Payout.timestamp.desc()).all()
    payout_list = []
    for p in payouts:
        vendor = Vendor.query.get(p.vendor_id)
        payout_list.append({
            **p.to_dict(),
            'shop_name': vendor.shop_name if vendor else 'Unknown'
        })

    return render_template('admin_payouts.html', payouts=payout_list)


@app.route('/admin/mark-payout-paid/<payout_id>', methods=['POST'])
def mark_payout_paid(payout_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    payout = Payout.query.get(payout_id)
    if payout:
        payout.status = 'Paid'
        db.session.commit()
        flash("✅ Payout marked as paid.")
    return redirect(url_for('admin_payouts'))
  
  # ============================================================
# VENDOR ROUTES
# ============================================================

PLATFORM_FEE_PERCENT = 10

from functools import wraps

def vendor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash("❌ Please log in first.")
            return redirect(url_for('login'))

        # ✅ Always re-check DB, don't rely only on session
        vendor = Vendor.query.filter_by(user_id=session['user_id']).first()
        if not vendor:
            flash("❌ Vendor account not found.")
            return redirect(url_for('become_vendor'))
        if vendor.is_banned:
            flash("⛔ Your vendor account has been banned.")
            return redirect(url_for('home'))
        if not vendor.is_approved:
            flash("⏳ Your account is pending approval.")
            return render_template('vendor_pending.html')

        # ✅ Refresh session with latest vendor data
        session['vendor_id'] = vendor.id
        session['shop_name'] = vendor.shop_name

        return f(*args, **kwargs)
    return decorated


@app.route('/vendor/dashboard')
@vendor_required
def vendor_dashboard():
    vendor = Vendor.query.get(session['vendor_id'])
    products = Product.query.filter_by(vendor_id=vendor.id).all()
    products_dicts = [p.to_dict() for p in products]

    all_orders = Order.query.all()
    vendor_orders = []
    total_earnings = 0
    pending_payout = 0

    for order in all_orders:
        items = json.loads(order.products or '[]')
        vendor_items = [i for i in items if i.get('vendor_id') == vendor.id]
        if vendor_items:
            subtotal = sum(float(i.get('price', 0)) * int(i.get('quantity', 1)) for i in vendor_items)
            fee = round(subtotal * PLATFORM_FEE_PERCENT / 100, 2)
            earnings = round(subtotal - fee, 2)
            total_earnings += earnings

            payout = Payout.query.filter_by(vendor_id=vendor.id, order_id=order.id).first()
            if not payout or payout.status == 'Pending':
                pending_payout += earnings

            vendor_orders.append({
                **order.to_dict(),
                'vendor_items': vendor_items,
                'vendor_subtotal': subtotal,
                'vendor_earnings': earnings,
                'payout_status': payout.status if payout else 'Pending'
            })

    stats = {
        'total_products': len(products),
        'total_orders': len(vendor_orders),
        'total_earnings': round(total_earnings, 2),
        'pending_payout': round(pending_payout, 2),
    }

    return render_template('vendor_dashboard.html', vendor=vendor.to_dict(),
                           products=products_dicts, orders=vendor_orders, stats=stats)


@app.route('/vendor/add-product', methods=['GET', 'POST'])
@vendor_required
def vendor_add_product():
    vendor = Vendor.query.get(session['vendor_id'])

    if request.method == 'POST':
        name = request.form.get('name', '').strip().title()
        price = request.form.get('price', '0').strip()
        on_sale = 'on_sale' in request.form
        sale_price = request.form.get('sale_price', '').strip() or None
        featured = 'featured' in request.form
        new_arrival = 'new_arrival' in request.form
        category = request.form.get('category', '').strip()
        if category == 'custom':
            category = request.form.get('category_custom', '').strip().title()
        description = request.form.get('description', '').strip()
        stock = int(request.form.get('stock', 0))
        colors = json.dumps([c.strip() for c in request.form.get('colors', '').split(',') if c.strip()])
        brand = request.form.get('brand', '').strip()
        sku = request.form.get('sku', '').strip()
        tags = json.dumps([t.strip() for t in request.form.get('tags', '').split(',') if t.strip()])
        delivery_info = request.form.get('delivery_info', 'Delivery in 2-4 working days').strip()

        product_type = request.form.get('product_type', 'standard')
        slot_length = request.form.get('slot_length', '').strip()
        slot_width = request.form.get('slot_width', '').strip()
        slot_depth = request.form.get('slot_depth', '').strip()

        if product_type == 'standard':
            sizes = json.dumps([s.strip() for s in request.form.get('sizes', '').split(',') if s.strip()])
        else:
            sizes = json.dumps([])

        # ✅ Set 30-day new arrival expiry
        new_arrival_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat() if new_arrival else ''

        images = request.files.getlist('images')
        image_filenames = []
        for img in images:
            if img and img.filename:
                upload_result = cloudinary.uploader.upload(img)
                image_filenames.append(upload_result['secure_url'])

        # ✅ Set new_arrival_until to 30 days from now if new_arrival is ticked
        new_arrival_until = ''
        if new_arrival:
            new_arrival_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        new_product = Product(
            name=name, price=price, on_sale=on_sale, sale_price=sale_price,
            featured=featured, category=category, description=description,
            stock=stock, sizes=sizes, colors=colors,
            images=json.dumps(image_filenames),
            brand=brand, sku=sku, tags=tags,
            delivery_info=delivery_info, new_arrival=new_arrival,
            new_arrival_until=new_arrival_until,  # ✅ no leading space
            product_type=product_type,
            slot_length=slot_length,
            slot_width=slot_width,
            slot_depth=slot_depth,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        db.session.add(new_product)
        db.session.commit()
        flash("✅ Product listed successfully!")
        return redirect(url_for('vendor_dashboard'))

    return render_template('vendor_add_product.html', vendor=vendor.to_dict())


@app.route('/vendor/edit-product/<product_id>', methods=['GET', 'POST'])
@vendor_required
def vendor_edit_product(product_id):
    product = Product.query.get(product_id)

    if not product or product.vendor_id != session['vendor_id']:
        flash("❌ Product not found or access denied.")
        return redirect(url_for('vendor_dashboard'))

    if request.method == 'POST':
        product.name = request.form.get('name', '').strip().title()
        product.price = request.form.get('price', '').strip()
        product.sale_price = request.form.get('sale_price', '').strip() or None
        product.on_sale = 'on_sale' in request.form
        product.featured = 'featured' in request.form
        product.description = request.form.get('description', '').strip()
        product.stock = int(request.form.get('stock', 0))
        product.brand = request.form.get('brand', '').strip()
        product.delivery_info = request.form.get('delivery_info', '').strip()

        category = request.form.get('category', '')
        if category == 'custom':
            category = request.form.get('category_custom', '').strip().title()
        product.category = category

        # ✅ Reset 30-day clock if new_arrival is ticked
        product.new_arrival = 'new_arrival' in request.form
        if product.new_arrival:
            product.new_arrival_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        else:
            product.new_arrival_until = ''

        # ✅ Dimension / size type fields
        product_type = request.form.get('product_type', 'standard')
        product.product_type = product_type
        if product_type == 'standard':
            product.sizes = json.dumps([s.strip() for s in request.form.get('sizes', '').split(',') if s.strip()])
        else:
            product.sizes = json.dumps([])
            product.slot_length = request.form.get('slot_length', '').strip()
            product.slot_width = request.form.get('slot_width', '').strip()
            product.slot_depth = request.form.get('slot_depth', '').strip()

        product.colors = json.dumps([c.strip() for c in request.form.get('colors', '').split(',') if c.strip()])
        product.tags = json.dumps([t.strip() for t in request.form.get('tags', '').split(',') if t.strip()])

        remove_images = request.form.getlist('remove_images')
        existing_images = json.loads(product.images or '[]')
        kept_images = [img for img in existing_images if img not in remove_images]
        new_images = request.files.getlist('new_images')
        for file in new_images:
            if file and file.filename:
               upload_result = cloudinary.uploader.upload(file)   # ← fix: use 'file'
               kept_images.append(upload_result['secure_url'])    # ← fix: append to kept_images
        product.images = json.dumps(kept_images)
        product.timestamp = datetime.now(timezone.utc).isoformat()

        db.session.commit()
        flash("✅ Product updated!")
        return redirect(url_for('vendor_dashboard'))

    return render_template('vendor_edit_product.html', product=product.to_dict())


@app.route('/vendor/delete-product/<product_id>', methods=['POST'])
@vendor_required
def vendor_delete_product(product_id):
    product = Product.query.get(product_id)
    if not product or product.vendor_id != session['vendor_id']:
        flash("❌ Access denied.")
        return redirect(url_for('vendor_dashboard'))

    for img in json.loads(product.images or '[]'):
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(product)
    db.session.commit()
    flash("🗑️ Product deleted.")
    return redirect(url_for('vendor_dashboard'))


@app.route('/vendor/logout')
def vendor_logout():
    session.pop('vendor_id', None)
    session.pop('shop_name', None)
    flash("👋 Vendor session ended.")
    return redirect(url_for('home'))


@app.route('/shop/vendor/<vendor_id>')
def vendor_storefront(vendor_id):
    vendor = Vendor.query.get(vendor_id)
    if not vendor or not vendor.is_approved:
        flash("❌ Store not found.")
        return redirect(url_for('home'))

    products = [p.to_dict() for p in Product.query.filter_by(vendor_id=vendor_id).all()]
    return render_template('vendor_storefront.html', vendor=vendor.to_dict(), products=products)

@app.route('/vendor/mark-shipped/<order_id>', methods=['POST'])
@vendor_required
def vendor_mark_shipped(order_id):
    order = Order.query.get(order_id)
    if not order:
        flash("❌ Order not found.")
        return redirect(url_for('vendor_dashboard'))

    order.status = 'Shipped'
    db.session.commit()

    track_url = url_for('track_order', order_id=order_id, _external=True)

    # ✅ Notify admin
    try:
        send_email(
            "shopluxe374@gmail.com",
            f"📦 Order Shipped — {order.name}",
            f"""
            <div style="font-family:sans-serif; padding:20px;">
                <h2>📦 Vendor Marked Order as Shipped</h2>
                <p><strong>Vendor:</strong> {session.get('shop_name')}</p>
                <p><strong>Customer:</strong> {order.name} ({order.email})</p>
                <p><strong>Order ID:</strong> {order_id}</p>
                <p><strong>Total:</strong> GH₵ {order.total}</p>
                <a href="https://www.shopluxe.online/admin"
                   style="background:#198754;color:#fff;padding:10px 20px;
                   border-radius:8px;text-decoration:none;">Go to Admin Panel</a>
            </div>
            """
        )
    except Exception as e:
        print("⚠️ Admin shipped email failed:", e)

    # ✅ NEW: Notify customer
    try:
        items = json.loads(order.products or '[]')
        item_lines = "".join(
            f"<div style='margin-bottom:8px;'><strong>{i.get('name')}</strong> "
            f"× {i.get('quantity',1)} — GH₵ {i.get('price',0)}</div>"
            for i in items
        )
        send_email(
            order.email,
            "📦 Your ShopLuxe Order Has Been Shipped!",
            f"""
            <div style="font-family:sans-serif;padding:20px;max-width:540px;">
                <h2 style="color:#198754;">Your order is on its way! 🚚</h2>
                <p>Hi <strong>{order.name}</strong>, great news — your order has been shipped
                   and is heading your way.</p>
                <div style="background:#f4f6f9;border-radius:12px;padding:16px;margin:18px 0;">
                    <p style="margin:0 0 10px;font-weight:700;color:#1a1a2e;">Order Summary</p>
                    {item_lines}
                    <hr style="border:none;border-top:1px solid #e0e0e0;margin:12px 0;">
                    <p style="margin:0;font-weight:700;color:#198754;">Total: GH₵ {order.total}</p>
                </div>
                <p style="color:#666;font-size:.88rem;">
                    You can track your order status using the button below.
                </p>
                <a href="{track_url}"
                   style="display:inline-block;background:#198754;color:#fff;
                   padding:12px 24px;border-radius:10px;text-decoration:none;
                   font-weight:700;margin-top:8px;">
                   📦 Track My Order
                </a>
                <p style="color:#aaa;font-size:.75rem;margin-top:20px;">
                    Thank you for shopping with ShopLuxe 🛍️
                </p>
            </div>
            """
        )
    except Exception as e:
        print("⚠️ Customer shipped email failed:", e)

    flash("✅ Order marked as shipped. Admin and customer have been notified.")
    return redirect(url_for('vendor_dashboard'))
# ============================================================
# DB INIT & RUN
# ============================================================

with app.app_context():
    db.create_all()

    with db.engine.connect() as conn:
        # ✅ Products table
        for col, definition in [
            ("brand", "VARCHAR(100) DEFAULT ''"),
            ("sku", "VARCHAR(100) DEFAULT ''"),
            ("tags", "TEXT DEFAULT '[]'"),
            ("delivery_info", "VARCHAR(200) DEFAULT 'Delivery in 2-4 working days'"),
            ("new_arrival", "BOOLEAN DEFAULT 0"),
            ("vendor_id", "VARCHAR DEFAULT NULL"),
            ("product_type", "VARCHAR DEFAULT 'standard'"),
            ("slot_length", "VARCHAR DEFAULT ''"),
            ("slot_width", "VARCHAR DEFAULT ''"),
            ("slot_depth", "VARCHAR DEFAULT ''"),
            ("new_arrival_until", "VARCHAR DEFAULT ''"),  # ✅ NEW
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE products ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass

        # ✅ Orders table — address fields
        for col, definition in [
            ("address", "VARCHAR DEFAULT ''"),        # ✅ NEW
            ("delivery_note", "VARCHAR DEFAULT ''"),   # ✅ NEW
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE orders ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass

        # ✅ Users table — reset password columns
        for col, definition in [
            ("reset_token", "VARCHAR DEFAULT NULL"),
            ("reset_token_expiry", "VARCHAR DEFAULT NULL"),
            ("address", "VARCHAR DEFAULT ''"),        # ✅ NEW
            ("city", "VARCHAR DEFAULT ''"),           # ✅ NEW
            ("region", "VARCHAR DEFAULT ''"),         # ✅ NEW
            ("delivery_note", "VARCHAR DEFAULT ''"),  # ✅ NEW
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE users ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass

        # ✅ Vendors table — safety net for new columns
        for col, definition in [
            ("phone", "VARCHAR DEFAULT ''"),
            ("bank_name", "VARCHAR DEFAULT ''"),
            ("bank_account", "VARCHAR DEFAULT ''"),
            ("logo", "VARCHAR DEFAULT ''"),
            ("is_approved", "BOOLEAN DEFAULT 0"),
            ("is_banned", "BOOLEAN DEFAULT 0"),
            ("shop_description", "TEXT DEFAULT ''"),
            ("timestamp", "VARCHAR DEFAULT ''"),
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE vendors ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass

        # ✅ Payouts table — safety net
        for col, definition in [
            ("order_id", "VARCHAR DEFAULT ''"),
            ("amount", "FLOAT DEFAULT 0"),
            ("platform_fee", "FLOAT DEFAULT 0"),
            ("status", "VARCHAR DEFAULT 'Pending'"),
            ("timestamp", "VARCHAR DEFAULT ''"),
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE payouts ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass

        # ✅ SQLite doesn't support DROP COLUMN in older versions, so the Review model
        # must NOT have removed columns defined — just ignore them here
# ── PROMO CODES ──
PROMO_FILE = 'promos.json'

def load_promos():
    if os.path.exists(PROMO_FILE):
        with open(PROMO_FILE) as f:
            return json.load(f)
    return {}

def save_promos(promos):
    with open(PROMO_FILE, 'w') as f:
        json.dump(promos, f, indent=2)

# DELETE the old load_promos() and save_promos() functions entirely
# Then update all 4 routes:

@app.route('/apply_promo', methods=['POST'])
def apply_promo():
    code = request.json.get('code', '').upper().strip()
    promo = Promo.query.filter_by(code=code, active=True).first()
    if promo:
        session['promo'] = {
            'code': promo.code,
            'discount': promo.discount,
            'flat': promo.flat,
            'label': promo.label
        }
        return jsonify(success=True, code=promo.code, label=promo.label)
    return jsonify(success=False, message='Invalid or inactive promo code')

@app.route('/remove_promo', methods=['POST'])
def remove_promo():
    session.pop('promo', None)
    return jsonify(success=True)

@app.route('/admin/promo/add', methods=['POST'])
def admin_add_promo():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    code = request.form.get('code', '').upper().strip()
    label = request.form.get('label', '').strip()
    discount_type = request.form.get('discount_type')
    value = float(request.form.get('value', 0))

    existing = Promo.query.filter_by(code=code).first()
    if existing:
        existing.label = label
        existing.discount = value / 100 if discount_type == 'percent' else 0
        existing.flat = value if discount_type == 'flat' else 0
        existing.active = True
    else:
        new_promo = Promo(
            code=code,
            label=label,
            discount=value / 100 if discount_type == 'percent' else 0,
            flat=value if discount_type == 'flat' else 0
        )
        db.session.add(new_promo)

    db.session.commit()
    flash(f'✅ Promo code {code} saved!')
    return redirect(url_for('admin') + '#promos')

@app.route('/admin/promo/toggle/<code>', methods=['POST'])
def admin_toggle_promo(code):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    promo = Promo.query.filter_by(code=code).first()
    if promo:
        promo.active = not promo.active
        db.session.commit()
    return redirect(url_for('admin') + '#promos')

@app.route('/admin/promo/delete/<code>', methods=['POST'])
def admin_delete_promo(code):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    promo = Promo.query.filter_by(code=code).first()
    if promo:
        db.session.delete(promo)
        db.session.commit()
    return redirect(url_for('admin') + '#promos')
  
@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    subject = request.form.get('subject', 'General Enquiry')
    message = request.form.get('message', '').strip()

    try:
        send_email(
            "shopluxe374@gmail.com",
            f"📩 Support Message: {subject}",
            f"""
            <div style="font-family:sans-serif; padding:20px; max-width:500px;">
                <h2 style="color:#198754;">New Support Message</h2>
                <p><strong>From:</strong> {name} ({email})</p>
                <p><strong>Subject:</strong> {subject}</p>
                <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
                <p style="line-height:1.7;">{message}</p>
            </div>
            """
        )
        flash("✅ Message sent! We'll get back to you soon.")
    except Exception as e:
        print("Contact form email failed:", e)
        flash("❌ Something went wrong. Please try WhatsApp instead.")

    return redirect(url_for('support'))
    


if __name__ == "__main__":
    app.run()
