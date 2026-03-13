import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import json
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import unquote, quote

import resend
import requests
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer

load_dotenv()

# ============================================================
# APP CONFIG
# ============================================================

app = Flask(__name__)
app.jinja_env.globals['session'] = session
app.jinja_env.add_extension('jinja2.ext.do')
app.secret_key = 'secret123'
app.config['UPLOAD_FOLDER'] = 'static/shoes'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shopluxe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)
resend.api_key = os.getenv("RESEND_API_KEY")

ADMIN_PASSWORD = 'Mohammed_@3'
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
    new_arrival = db.Column(db.Boolean, default=True)

    def to_dict(self):
        images = json.loads(self.images or '[]')
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
            'new_arrival': self.new_arrival if self.new_arrival is not None else True,
        }


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, default='')
    email = db.Column(db.String, default='')
    phone = db.Column(db.String, default='')
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

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'password': self.password,
            'is_admin': self.is_admin
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
    return sorted(load_data(), key=lambda x: x.get('timestamp', ''), reverse=True)[:4]

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

def send_email(to, subject, html):
    resend.Emails.send({
        "from": "Shopluxe <onboarding@resend.dev>",
        "to": [to],
        "subject": subject,
        "html": html
    })


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



# ============================================================
# MAIN ROUTES
# ============================================================

@app.route('/', endpoint='home')
def index():
    query = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '').strip().lower()
    current_time = datetime.now(timezone.utc)
    products = normalize_timestamps(load_data())

    featured_products = [p for p in products if p.get('featured')]
    popular_products = sorted(products, key=lambda x: x.get('popularity', 0), reverse=True)[:8]
    new_products = sorted(products, key=lambda x: x['timestamp'], reverse=True)[:8]
    sale_products = [p for p in products if p.get('on_sale')]

    if query:
        filtered_products = [p for p in products if query in p.get('name', '').lower()
                             or query in p.get('description', '').lower()
                             or query in p.get('category', '').lower()]
    elif category:
        filtered_products = [p for p in products if p.get('category', '').lower() == category]
    else:
        filtered_products = products

    return render_template(
        'index.html',
        products=filtered_products,
        featured_products=featured_products,
        popular_products=popular_products,
        new_products=new_products,
        sale_products=sale_products,
        query=query,
        current_time=current_time,
        selected_category=category or 'all',
        active_page='home',
        paystack_public_key=PAYSTACK_PUBLIC_KEY
    )


@app.route('/search')
def search():
    query = request.args.get('q', '').strip().lower()
    current_time = datetime.now(timezone.utc)
    products = normalize_timestamps(load_data())

    filtered = [p for p in products if query in p.get('name', '').lower()
                or query in p.get('category', '').lower()
                or query in p.get('description', '').lower()] if query else products

    featured_products = [p for p in filtered if (current_time - p['timestamp']).days <= 7]

    return render_template(
        'index.html',
        products=filtered,
        featured_products=featured_products,
        query=query,
        current_time=current_time,
        selected_category='all',
        active_page='search'
    )


@app.route('/live_search')
def live_search():
    query = request.args.get('q', '').strip().lower()
    if not query:
        return jsonify([])

    filtered = [p for p in load_data()
                if query in p.get('name', '').lower()
                or query in p.get('category', '').lower()
                or query in p.get('description', '').lower()]

    for p in filtered:
        p['image_url'] = url_for('static', filename='shoes/' + (p.get('images', ['placeholder.jpg'])[0]))
    return jsonify(filtered)


@app.route('/filtered/<category>')
def filtered(category):
    current_time = datetime.now(timezone.utc)
    all_products = normalize_timestamps(load_data())

    filtered_products = all_products if category.lower() == 'all' else [
        p for p in all_products if category.lower() in p['category'].lower()
    ]

    featured_products = [p for p in filtered_products if (current_time - p['timestamp']).days <= 7]

    return render_template(
        'filtered.html',
        products=filtered_products,
        featured_products=featured_products,
        current_time=current_time,
        selected_category=category,
        active_page='categories'
    )


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
    cats = [
        {'name': 'Shoes', 'image': 'shoes.jpg'},
        {'name': 'Tops', 'image': 'tops.jpg'},
        {'name': 'Bottoms', 'image': 'bottoms.jpg'},
        {'name': "Men's", 'image': 'men.jpg'},
        {'name': "Women's", 'image': 'women.jpg'},
        {'name': "Kid's", 'image': 'kids.jpg'},
        {'name': 'Accessories', 'image': 'accessories.jpg'}
    ]
    return render_template('categories.html', categories=cats, active_page='categories')

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
    return render_template('settings.html')


@app.route('/support')
def support():
    return render_template('support.html')


@app.route("/healthz")
def health_check():
    return "OK", 200


@app.route('/test_email')
def test_email():
    try:
        msg = Message("✅ Test Email from Flask App", recipients=[app.config['MAIL_USERNAME']])
        msg.body = "This is a test email to verify email sending from your Flask app."
        mail.send(msg)
        return "✅ Test email sent successfully!"
    except Exception as e:
        return f"❌ Email failed: {str(e)}"


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

    # ✅ Stock deduction + admin out-of-stock alert only
    for item in items:
        product = Product.query.filter_by(name=item.get("name")).first()
        if product:
            product.stock = max(0, product.stock - int(item.get("quantity", 1)))

            if product.stock == 0:
                try:
                    send_email(
                        "vybezkhid7@gmail.com",
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

    # ✅ Store effective_price in order items
    enriched_items = []
    for item in items:
        enriched_items.append({
            **item,
            'price': item.get('effective_price') or item.get('price', 0)
        })

    new_order = Order(
        id=order_id, name=name, email=email, phone=phone,
        amount=amount, total=amount, products=json.dumps(enriched_items),
        status="Paid", payment_status="Paid",
        timestamp=datetime.now(timezone.utc).isoformat(),
        order_time=datetime.now().strftime("%b %d, %Y, %I:%M %p"),
        local_time=datetime.now().strftime("%b %d, %Y, %I:%M %p")
    )
    db.session.add(new_order)
    db.session.commit()
    session.pop('cart', None)

    track_order_url = url_for("track_order", order_id=order_id, _external=True)
    product_list = "".join(
        f"<p>{i['name']} ({i.get('quantity', 1)}x) — GH₵ {i.get('price', 0)}</p>"
        for i in enriched_items
    )
    order_time_str = datetime.now().strftime("%b %d, %Y, %I:%M %p")

    try:
        send_email("vybezkhid7@gmail.com", "📦 New Paid Order - ShopLuxe",
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
        return "Order not found.", 404
    return render_template("track_order.html", order=order.to_dict())


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
        name = request.form.get('name')
        price = float(request.form.get('price', 0))
        on_sale = 'on_sale' in request.form
        sale_price = float(request.form.get('sale_price') or 0)
        featured = 'featured' in request.form
        new_arrival = 'new_arrival' in request.form

        # Category: custom overrides dropdown
        category = request.form.get('category_custom', '').strip() or request.form.get('category', '')

        description = request.form.get('description', '')
        stock = int(request.form.get('stock', 0))
        sizes = [s.strip() for s in request.form.get('sizes', '').split(',') if s.strip()]
        colors = [c.strip() for c in request.form.get('colors', '').split(',') if c.strip()]
        brand = request.form.get('brand', '')
        sku = request.form.get('sku', '')
        tags = [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()]
        delivery_info = request.form.get('delivery_info', 'Delivery in 2-4 working days')

        images = request.files.getlist('images')
        image_filenames = []
        for img in images:
            if img and img.filename:
                filename = secure_filename(img.filename)
                img.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filenames.append(filename)

        new_product = Product(
            name=name, price=price, on_sale=on_sale, sale_price=sale_price,
            featured=featured, category=category, description=description,
            stock=stock, sizes=json.dumps(sizes), colors=json.dumps(colors),
            images=json.dumps(image_filenames),
            brand=brand, sku=sku, tags=json.dumps(tags),
            delivery_info=delivery_info, new_arrival=new_arrival,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(new_product)
        db.session.commit()
        flash("✅ Product added successfully!")
        return redirect(url_for('admin'))

    products = load_data()
    orders = [o.to_dict() for o in Order.query.order_by(Order.timestamp.desc()).all()]
    return render_template('admin.html', products=products, orders=orders)
  

  
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
        old_stock = product.stock  # ✅ Save before update for restock notification

        # ── Basic Info ──
        product.name = request.form.get('name', '').strip().title()
        product.brand = request.form.get('brand', '').strip()
        product.sku = request.form.get('sku', '').strip()
        product.description = request.form.get('description', '').strip()
        product.delivery_info = request.form.get('delivery_info', 'Delivery in 2-4 working days').strip()

        # ── Category ──
        category = request.form.get('category')
        if category == 'custom':
            category = request.form.get('category_custom', '').strip().title()
        product.category = category

        # ── Pricing ──
        product.price = request.form.get('price', '').strip()
        product.sale_price = request.form.get('sale_price', '').strip() or None
        product.on_sale = 'on_sale' in request.form
        product.featured = 'featured' in request.form
        product.new_arrival = 'new_arrival' in request.form

        # ── Inventory ──
        product.stock = int(request.form.get('stock', 0))

        # ── Sizes & Colors ──
        sizes_raw = request.form.get('sizes', '')
        product.sizes = json.dumps([s.strip() for s in sizes_raw.split(',') if s.strip()])

        colors_raw = request.form.get('colors', '')
        product.colors = json.dumps([c.strip() for c in colors_raw.split(',') if c.strip()])

        # ── Tags ──
        tags_raw = request.form.get('tags', '')
        product.tags = json.dumps([t.strip() for t in tags_raw.split(',') if t.strip()])

        # ── Images: remove checked ──
        remove_images = request.form.getlist('remove_images')
        existing_images = json.loads(product.images or '[]')
        kept_images = [img for img in existing_images if img not in remove_images]

        # ── Images: add new uploads ──
        new_images = request.files.getlist('new_images')
        for file in new_images:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                kept_images.append(filename)

        product.images = json.dumps(kept_images)
        product.timestamp = datetime.now(timezone.utc).isoformat()

        db.session.commit()

        # ✅ Notify restock waitlist if stock went from 0 to > 0
        if old_stock == 0 and product.stock > 0:
            waitlist = RestockRequest.query.filter_by(product_id=product.id).all()
            for req in waitlist:
                try:
                    send_email(
                        req.email,
                        f"✅ Back in Stock — {product.name}",
                        f"""
                        <div style="font-family:sans-serif; padding:20px;">
                            <h2 style="color:#198754;">Good news! 🎉</h2>
                            <p><strong>{product.name}</strong> is back in stock.</p>
                            <a href="https://www.shopluxe.online/product/{product.id}"
                               style="background:#198754;color:#fff;padding:10px 20px;
                               border-radius:8px;text-decoration:none;">
                               Shop Now
                            </a>
                        </div>
                        """
                    )
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
        item_lines = "".join(
            f"<div style='margin-bottom:10px;'><strong>{i.get('name')}</strong><br>"
            f"Qty: {i.get('quantity', 1)} | GH₵ {i.get('price')}</div>" for i in items
        )
        send_email(order.email, "✅ Your Order Has Been Delivered - ShopLuxe",
                   render_template('emails/user_delivered_email.html', name=order.name,
                                   product_name=item_lines, quantity=len(items),
                                   total=order.total, order_time=order.local_time,
                                   timezone=order.timezone))
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
            msg = Message("🎉 Welcome to ShopLuxe!", recipients=[email])
            msg.body = f"Hello {name},\n\nThanks for signing up with ShopLuxe!\n\nBest regards,\nShopLuxe Team"
            mail.send(msg)
        except Exception as e:
            print("Email send failed:", e)

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

# DELETE THIS
@app.route('/debug_session')
def debug_session():
    return str(dict(session))

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
        # ✅ Use sale price if on sale
        p['effective_price'] = float(p['sale_price']) if p.get('on_sale') and p.get('sale_price') else float(p['price'])
        cart_items.append(p)

    subtotal = sum(p['effective_price'] * p['quantity'] for p in cart_items)
    # ✅ Paystack Ghana: 1.95% + GH₵ 0.50, capped at GH₵ 500
    payout_fee = round(min((subtotal * 0.0195) + 0.50, 500), 2)
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal,
                           payout_fee=payout_fee, total=round(subtotal + payout_fee, 2),
                           active_page='cart')


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

    subtotal = sum(p['effective_price'] * p['quantity'] for p in cart_items)
    payout_fee = round(min((subtotal * 0.0195) + 0.50, 500), 2)
    total = round(subtotal + payout_fee, 2)

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        subtotal=subtotal,
        payout_fee=payout_fee,
        total=total,
        paystack_public_key=PAYSTACK_PUBLIC_KEY
    )
# ============================================================
# WISHLIST ROUTES
# ============================================================

@app.route('/add_to_wishlist/<product_id>')
def add_to_wishlist(product_id):
    wishlist = get_wishlist()
    product = get_product_by_id(product_id)

    if not product:
        flash("❌ Product not found.")
        return redirect(request.referrer or url_for('index'))
    if any(str(p['id']) == str(product_id) for p in wishlist):
        flash("❤️ Already in your wishlist.")
        return redirect(request.referrer or url_for('wishlist'))

    image_path = product.get('image') or (product.get('images', ['default.png'])[0])
    if image_path.startswith('static/'):
        image_path = image_path.replace('static/', '')

    wishlist.append({'id': product['id'], 'name': product['name'],
                     'price': product['price'], 'image': image_path})
    session['wishlist'] = wishlist
    flash("💖 Added to your wishlist!")
    return redirect(request.referrer or url_for('wishlist'))


@app.route('/toggle_wishlist_ajax/<product_id>', methods=['POST'])
def toggle_wishlist_ajax(product_id):
    wishlist = session.get('wishlist', [])
    in_wishlist = any(str(p['id']) == str(product_id) for p in wishlist)

    if in_wishlist:
        wishlist = [p for p in wishlist if str(p['id']) != str(product_id)]
        message = "💔 Removed from wishlist."
        in_wishlist = False
    else:
        product = get_product_by_id(product_id)
        if not product:
            return jsonify({'success': False, 'message': '❌ Product not found.'})

        image_path = product.get('image') or (product.get('images', ['default.png'])[0])
        if image_path.startswith('static/'):
            image_path = image_path.replace('static/', '')

        wishlist.append({'id': product['id'], 'name': product['name'],
                         'price': product['price'], 'image': image_path})
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
    session['wishlist'] = [p for p in get_wishlist() if str(p.get('id')) != str(product_id)]
    flash("❌ Removed from wishlist.")
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
            password=generate_password_hash(str(uuid4())),  # random password
            is_admin=False
        )
        db.session.add(user)
        db.session.commit()

    session.clear()
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['user_email'] = user.email
    session['is_admin'] = user.is_admin

    flash(f"✅ Welcome, {user.name}!")
    return redirect(url_for('profile'))

# ============================================================
# DB INIT & RUN
# ============================================================

with app.app_context():
    db.create_all()

    with db.engine.connect() as conn:
        # Products table
        for col, definition in [
            ("brand", "VARCHAR(100) DEFAULT ''"),
            ("sku", "VARCHAR(100) DEFAULT ''"),
            ("tags", "TEXT DEFAULT '[]'"),
            ("delivery_info", "VARCHAR(200) DEFAULT 'Delivery in 2-4 working days'"),
            ("new_arrival", "BOOLEAN DEFAULT 1"),
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE products ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass

        # ✅ Users table — reset password columns
        for col, definition in [
            ("reset_token", "VARCHAR DEFAULT NULL"),
            ("reset_token_expiry", "VARCHAR DEFAULT NULL"),
        ]:
            try:
                conn.execute(db.text(f"ALTER TABLE users ADD COLUMN {col} {definition}"))
                conn.commit()
            except:
                pass
        # ✅ Remove bad columns from reviews if they exist (can't drop in SQLite, so just ignore)
        # SQLite doesn't support DROP COLUMN in older versions, so the Review model
        # must NOT have these columns defined

if __name__ == "__main__":
    app.run()