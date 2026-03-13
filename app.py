import sys
sys.stdout.reconfigure(encoding='utf-8')
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer
import os, json, uuid
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import resend
import requests
from werkzeug.middleware.proxy_fix import ProxyFix
from urllib.parse import unquote, quote
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.jinja_env.globals['session'] = session
app.secret_key = 'secret123'
app.config['UPLOAD_FOLDER'] = 'static/shoes'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# ✅ SQLite Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shopluxe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

serializer = URLSafeTimedSerializer(app.secret_key)
ADMIN_PASSWORD = 'Mohammed_@3'
MAX_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=5)

# Email config
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
mail = Mail(app)

PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
print("PAYSTACK_PUBLIC_KEY:", PAYSTACK_PUBLIC_KEY)

resend.api_key = os.getenv("RESEND_API_KEY")

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
    colors = db.Column(db.Text, default='[]')   # JSON string
    sizes = db.Column(db.Text, default='[]')    # JSON string
    images = db.Column(db.Text, default='[]')   # JSON string
    popularity = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
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
            'images': json.loads(self.images or '[]'),
            'image': json.loads(self.images or '[]')[0] if json.loads(self.images or '[]') else None,
            'popularity': self.popularity,
            'timestamp': self.timestamp
        }


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, default='')
    email = db.Column(db.String, default='')
    phone = db.Column(db.String, default='')
    amount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    products = db.Column(db.Text, default='[]')   # JSON string
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


# ============================================================
# HELPER FUNCTIONS (replacing JSON load/save)
# ============================================================

def load_data():
    return [p.to_dict() for p in Product.query.all()]

def save_data(products_list):
    pass  # No longer needed — use db directly

def load_orders():
    orders = Order.query.all()
    result = []
    now = datetime.now(timezone.utc)
    for o in orders:
        d = o.to_dict()
        # Expire unpaid orders older than 15 mins
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

def save_orders(orders_list):
    pass  # No longer needed — use db directly

def load_users():
    return [u.to_dict() for u in User.query.all()]

def save_users(users_list):
    pass  # No longer needed — use db directly

def load_reviews():
    return [r.to_dict() for r in Review.query.all()]

def save_reviews(reviews_list):
    pass  # No longer needed — use db directly

def get_all_products():
    return load_data()

def get_products_by_category(category):
    return [p for p in load_data() if p.get('category', '').lower() == category.lower()]

def get_featured_products():
    products = sorted(load_data(), key=lambda x: x.get('timestamp', ''), reverse=True)
    return products[:4]

@app.route('/migrate_json_to_db')
def migrate_json_to_db():
    if not session.get('admin_logged_in'):
        return "Not authorized", 403

    # Migrate products
    try:
        with open('data.json', 'r') as f:
            products = json.load(f)
        for p in products:
            if not Product.query.get(p.get('id')):
                db.session.add(Product(
                    id=p.get('id', str(uuid4())),
                    name=p.get('name', ''),
                    price=str(p.get('price', '')),
                    sale_price=str(p.get('sale_price', '')) if p.get('sale_price') else None,
                    on_sale=p.get('on_sale', False),
                    featured=p.get('featured', False),
                    category=p.get('category', ''),
                    description=p.get('description', ''),
                    stock=int(p.get('stock', 0)),
                    colors=json.dumps(p.get('colors', [])),
                    sizes=json.dumps(p.get('sizes', [])),
                    images=json.dumps(p.get('images', [])),
                    popularity=p.get('popularity', 0)
                ))
    except Exception as e:
        print("Products migration error:", e)

    # Migrate orders
    try:
        orders_file = os.path.join(os.path.dirname(__file__), "data/orders.json")
        with open(orders_file, 'r') as f:
            orders = json.load(f)
        for o in orders:
            if not Order.query.get(o.get('id')):
                db.session.add(Order(
                    id=o.get('id', str(uuid4())),
                    name=o.get('name', ''),
                    email=o.get('email', ''),
                    phone=o.get('phone', ''),
                    amount=float(o.get('amount', 0)),
                    total=float(o.get('total', 0)),
                    products=json.dumps(o.get('products') or o.get('items', [])),
                    status=o.get('status', 'Pending'),
                    payment_status=o.get('payment_status', 'Unpaid'),
                    timestamp=o.get('timestamp', ''),
                    order_time=o.get('order_time', ''),
                    local_time=o.get('local_time', '')
                ))
    except Exception as e:
        print("Orders migration error:", e)

    # Migrate users
    try:
        with open('users.json', 'r') as f:
            users = json.load(f)
        for u in users:
            if not User.query.filter_by(email=u.get('email')).first():
                db.session.add(User(
                    id=u.get('id', str(uuid4())),
                    name=u.get('name', ''),
                    email=u.get('email', ''),
                    password=u.get('password', ''),
                    is_admin=u.get('is_admin', False)
                ))
    except Exception as e:
        print("Users migration error:", e)

    # Migrate reviews
    try:
        with open('reviews.json', 'r') as f:
            reviews = json.load(f)
        for r in reviews:
            db.session.add(Review(
                product_id=str(r.get('product_id', '')),
                product_index=r.get('product_index', 0),
                name=r.get('name', ''),
                comment=r.get('comment', ''),
                rating=r.get('rating', 5),
                timestamp=r.get('timestamp', '')
            ))
    except Exception as e:
        print("Reviews migration error:", e)

    db.session.commit()
    return "✅ Migration complete!"


@app.route('/', endpoint='home')
def index():
    query = request.args.get('q', '').strip().lower()
    category = request.args.get('category', '').strip().lower()
    products = load_data()
    current_time = datetime.now(timezone.utc)

    # Normalize product data
    for p in products:
        if isinstance(p.get('timestamp'), str):
            try:
                dt = datetime.fromisoformat(p['timestamp'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                p['timestamp'] = dt
            except Exception:
                p['timestamp'] = current_time
        elif isinstance(p.get('timestamp'), datetime):
            if p['timestamp'].tzinfo is None:
                p['timestamp'] = p['timestamp'].replace(tzinfo=timezone.utc)
        else:
            p['timestamp'] = current_time

        # Ensure images exist
        if 'images' not in p and 'image' in p:
            p['images'] = [p['image']]
        elif 'images' in p and 'image' not in p:
            p['image'] = p['images'][0]
        elif 'images' not in p and 'image' not in p:
            p['images'] = []
            p['image'] = None

    # Product sections
    featured_products = [p for p in products if p.get('featured')]
    popular_products = sorted(products, key=lambda x: x.get('popularity', 0), reverse=True)[:8]
    new_products = sorted(products, key=lambda x: x['timestamp'], reverse=True)[:8]
    sale_products = [p for p in products if p.get('on_sale')]

    # Apply search and filters
    filtered_products = []
    for p in products:
        name = p.get('name', '').lower()
        description = p.get('description', '').lower()
        cat = p.get('category', '').lower()

        if query and (query in name or query in description or query in cat):
            filtered_products.append(p)
        elif category and cat == category:
            filtered_products.append(p)

    if not query and not category:
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
        paystack_public_key=PAYSTACK_PUBLIC_KEY  # 👈 pass public key to template
    )


# -------------------------------
# 💳 Initialize Paystack Payment
# -------------------------------
from uuid import uuid4

@app.route('/initialize_payment', methods=['POST'])
def initialize_payment():
    data = request.get_json()
    email = data.get('email')
    amount = int(data.get('amount')) * 100
    reference = str(uuid4())

    # ✅ Save pending order to database
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
        "amount": amount,
        "reference": reference,
        "callback_url": url_for('verify_payment', _external=True)
    }
    response = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    return jsonify(response.json())

import os, json
from datetime import datetime, timezone
from flask import session, flash, redirect, url_for, render_template, request
from urllib.parse import quote

from urllib.parse import unquote

@app.route('/verify_payment')
def verify_payment():

    reference = request.args.get('reference')
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}

    response = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )
    result = response.json()
    payment_data = result.get("data", {})

    if payment_data.get("status") == "success":

        customer = payment_data.get("customer", {})
        metadata = payment_data.get("metadata", {})

        name = metadata.get("name") or customer.get("first_name") or "Customer"
        email = metadata.get("email") or customer.get("email")
        phone = metadata.get("phone") or "-"
        amount = payment_data.get("amount", 0) / 100
        items = metadata.get("items", [])
        order_id = reference

        # ✅ FIX 1: Duplicate order prevention
        if Order.query.get(order_id):
            return redirect(url_for("order_confirmation", reference=order_id))

        track_order_url = url_for("track_order", order_id=order_id, _external=True)
        product_list = "".join(
            f"<p>{i['name']} ({i.get('quantity',1)}x)</p>" for i in items
        )

        # ✅ FIX 2: Stock deduction
        for item in items:
            product = Product.query.filter_by(name=item.get("name")).first()
            if product:
                product.stock = max(0, product.stock - int(item.get("quantity", 1)))
        db.session.commit()

        # ✅ Save order
        new_order = Order(
            id=order_id,
            name=name,
            email=email,
            phone=phone,
            amount=amount,
            total=amount,
            products=json.dumps(items),
            status="Paid",
            payment_status="Paid",
            timestamp=datetime.now(timezone.utc).isoformat(),
            order_time=datetime.now().strftime("%b %d, %Y, %I:%M %p"),
            local_time=datetime.now().strftime("%b %d, %Y, %I:%M %p")
        )
        db.session.add(new_order)
        db.session.commit()

        # ✅ FIX 3: Clear cart
        session.pop('cart', None)

        # ✅ Send emails
        try:
            admin_html = render_template(
                "emails/admin_order_email.html",
                name=name, email=email, phone=phone,
                product_name=product_list, total=amount,
                order_time=datetime.now().strftime("%b %d, %Y, %I:%M %p"),
                track_order_url=track_order_url
            )
            send_email("vybezkhid7@gmail.com", "📦 New Paid Order - ShopLuxe", admin_html)

            user_html = render_template(
                "emails/user_order_email.html",
                name=name, product_name=product_list, total=amount,
                order_time=datetime.now().strftime("%b %d, %Y, %I:%M %p"),
                track_order_url=track_order_url
            )
            send_email(email, "✅ Payment Received - ShopLuxe", user_html)

        except Exception as e:
            print("⚠️ Email sending failed:", e)

        return redirect(url_for("order_confirmation", reference=order_id))

    else:
        return render_template("failure.html", payment=payment_data)

@app.route('/orders')
def orders():
    if not session.get('user_email'):
        flash("❌ Please login first.")
        return redirect(url_for('login'))

    # ✅ Query directly from database
    user_orders = Order.query.filter_by(email=session['user_email']).all()
    user_orders = [o.to_dict() for o in user_orders]

    for order in user_orders:
        order['local_time'] = order.get('local_time') or order.get('order_time', 'N/A')
        if not order.get('products'):
            order['products'] = [{
                'name': order.get('product_name', 'Unknown Product'),
                'price': order.get('total', 0),
                'quantity': order.get('quantity', 1),
                'color': order.get('color', '-'),
                'size': order.get('size', '-')
            }]

    return render_template("orders.html", orders=user_orders)




@app.route('/search')
def search():
    query = request.args.get('q', '').strip().lower()
    products = load_data()
    current_time = datetime.now(timezone.utc)

    # ✅ Fix timestamps and ensure they are timezone-aware
    for p in products:
        if isinstance(p.get('timestamp'), str):
            try:
                dt = datetime.fromisoformat(p['timestamp'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                p['timestamp'] = dt
            except Exception:
                p['timestamp'] = current_time  # fallback if invalid
        elif isinstance(p.get('timestamp'), datetime):
            if p['timestamp'].tzinfo is None:
                p['timestamp'] = p['timestamp'].replace(tzinfo=timezone.utc)
        else:
            p['timestamp'] = current_time

        # ✅ Fix image field consistency
        if 'images' not in p and 'image' in p:
            p['images'] = [p['image']]
        elif 'images' in p and 'image' not in p:
            p['image'] = p['images'][0]

    # ✅ Search by name, category, or description
    if query:
        filtered = [
            p for p in products
            if query in p.get('name', '').lower()
            or query in p.get('category', '').lower()
            or query in p.get('description', '').lower()
        ]
    else:
        filtered = products

    # ✅ Featured = recently added (safe timezone comparison)
    featured_products = [
        p for p in filtered
        if (current_time - p['timestamp']).days <= 7
    ]

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
    products = load_data()

    if not query:
        return jsonify([])

    filtered = [
        p for p in products
        if query in p.get('name', '').lower()
        or query in p.get('category', '').lower()
        or query in p.get('description', '').lower()
    ]

    # Send minimal info for faster loading
    for p in filtered:
        p['image_url'] = url_for('static', filename='shoes/' + (p.get('images', ['placeholder.jpg'])[0]))
    return jsonify(filtered)




resend.api_key = os.getenv("RESEND_API_KEY")  # uncomment this line!

def send_email(to, subject, html):
    resend.Emails.send({
        "from": "Shopluxe <onboarding@resend.dev>",
        "to": [to],
        "subject": subject,
        "html": html
    })


@app.route('/filtered/<category>')
def filtered(category):
    current_time = datetime.now(timezone.utc)
    all_products = load_data()

    # Convert timestamps safely and make them timezone-aware
    for p in all_products:
        if isinstance(p.get('timestamp'), str):
            try:
                dt = datetime.fromisoformat(p['timestamp'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                p['timestamp'] = dt
            except Exception:
                p['timestamp'] = current_time  # fallback if invalid

    # Filter products by category
    if category.lower() == 'all':
        filtered_products = all_products
    else:
        filtered_products = [p for p in all_products if category.lower() in p['category'].lower()]

    # Add index to each product
    products = [{'index': i, **p} for i, p in enumerate(filtered_products)]

    # Featured = products added in last 7 days
    featured_products = [
        p for p in filtered_products
        if (current_time - p['timestamp']).days <= 7
    ]

    return render_template(
        'filtered.html',
        products=products,
        featured_products=featured_products,
        current_time=current_time,
        selected_category=category,
        active_page='categories'
    )





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
        else:
            # Lockout expired
            session.pop('admin_locked_until', None)
            session['admin_attempts'] = 0

    if request.method == 'POST':
        password = request.form.get('password')

        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session['admin_attempts'] = 0
            session.pop('admin_locked_until', None)
            return redirect(url_for('admin'))
        else:
            session['admin_attempts'] = attempts + 1
            if session['admin_attempts'] >= MAX_ATTEMPTS:
                lockout_time = now + LOCKOUT_DURATION
                session['admin_locked_until'] = lockout_time.isoformat()
                flash("🚫 Too many failed attempts. You're locked out for 5 minutes.")
            else:
                remaining = MAX_ATTEMPTS - session['admin_attempts']
                flash(f"❌ Incorrect password. {remaining} attempt(s) remaining.")

    return render_template('admin_login.html')


# -------- Admin Dashboard Route --------
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_data()
    reviews = load_reviews()
    orders = load_orders()

    if request.method == 'POST':
        name = request.form.get('name', '').title()
        price = request.form.get('price', '')
        category = request.form.get('category', '').title()
        description = request.form.get('description', '')
        stock = int(request.form.get('stock', 0))

        on_sale = 'on_sale' in request.form
        sale_price = request.form.get('sale_price', '')
        featured = 'featured' in request.form

        colors = [c.strip() for c in request.form.get('colors', '').split(',')] if request.form.get('colors') else []
        sizes = [s.strip() for s in request.form.get('sizes', '').split(',')] if request.form.get('sizes') else []

        if on_sale and sale_price:
            try:
                if float(sale_price) >= float(price):
                    flash("⚠️ Sale price must be less than the original price.")
                    return redirect(url_for('admin'))
            except ValueError:
                flash("⚠️ Invalid sale price entered.")
                return redirect(url_for('admin'))

        uploaded_files = request.files.getlist('images')
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            flash("❌ Please upload at least one image.")
            return redirect(url_for('admin'))

        image_filenames = []
        for file in uploaded_files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filenames.append(filename)

        # ✅ Save to database
        new_product = Product(
            id=str(uuid4()),
            name=name,
            price=price,
            sale_price=sale_price if on_sale and sale_price else None,
            on_sale=on_sale,
            featured=featured,
            category=category,
            description=description,
            stock=stock,
            colors=json.dumps(colors),
            sizes=json.dumps(sizes),
            images=json.dumps(image_filenames),
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(new_product)
        db.session.commit()
        flash("✅ Product added successfully!")
        return redirect(url_for('admin'))

    # Normalize orders for display
    for order in orders:
        order['id'] = order.get('id', str(uuid4()))
        order['status'] = order.get('status', 'Pending')
        order['payment_status'] = order.get('payment_status', 'Unpaid')
        order['local_time'] = order.get('local_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        order['delivered_time'] = order.get('delivered_time', '')
        order['cancelled_time'] = order.get('cancelled_time') or (
            order['local_time'] if order['status'] == 'Cancelled' else ''
        )

        if not order.get('products'):
            order['products'] = [{
                'name': order.get('product_name', 'Unknown Product'),
                'price': order.get('total', 0),
                'quantity': order.get('quantity', 1),
                'color': order.get('color', '-'),
                'size': order.get('size', '-')
            }]

        if order.get('payment_status') == 'Paid' and order['status'] == 'Pending':
            order['status'] = 'Paid'

        if order['status'] == 'Delivered':
            order['completed_time'] = order['delivered_time']
        elif order['status'] == 'Cancelled':
            order['completed_time'] = order['cancelled_time']
        elif order['status'] == 'Paid':
            order['completed_time'] = order.get('paid_time', order['local_time'])
        else:
            order['completed_time'] = ''

    return render_template(
        'admin.html',
        products=products,
        reviews=reviews,
        orders=orders,
        current_time=datetime.now(timezone.utc),
        active_page='admin'
    )

  # <-- Add this
@app.template_filter('todatetime')
def todatetime_filter(s):
    if isinstance(s, datetime):
        return s.astimezone(timezone.utc)
    if isinstance(s, str):
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None
    return None

  



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not name or not email or not password:
            flash("❌ All fields are required.")
            return redirect(url_for('signup'))

        # ✅ Check if email already exists
        if User.query.filter_by(email=email).first():
            flash("❌ Email already registered.")
            return redirect(url_for('signup'))

        # ✅ Save to database
        new_user = User(
            id=str(uuid4()),
            name=name,
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(new_user)
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

        # ✅ Query from database
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session.clear()
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_email'] = user.email
            session['is_admin'] = user.is_admin
            flash("✅ Logged in successfully.")
            return redirect(url_for('profile'))
        else:
            flash("❌ Invalid credentials.")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # ✅ Query from database
        user = User.query.filter_by(email=email).first()

        if not user:
            flash("❌ Email not found.")
            return redirect(url_for('forgot_password'))

        token = serializer.dumps(email, salt='reset-password')
        reset_link = url_for('reset_with_token', token=token, _external=True)

        try:
            msg = Message("🔐 Password Reset Request", recipients=[email])
            msg.body = f"Hello,\n\nClick the link below to reset your password:\n\n{reset_link}\n\nThis link expires in 30 minutes."
            mail.send(msg)
        except Exception as e:
            print("Failed to send email:", e)
            flash("❌ Email send failed.")
            return redirect(url_for('forgot_password'))

        flash("📧 Check your email for the reset link.")
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


@app.route('/reset_with_token/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    try:
        email = serializer.loads(token, salt='reset-password', max_age=1800)
    except:
        flash("❌ Reset link expired or invalid.")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password')
        if not new_password:
            flash("❌ Please enter a new password.")
            return redirect(url_for('reset_with_token', token=token))

        # ✅ Query from database
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash("✅ Password reset successful. Please log in.")
            return redirect(url_for('login'))

        flash("❌ User not found.")
        return redirect(url_for('login'))

    return render_template('reset_with_token.html')


def load_json(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        flash("⚠️ Please log in first.")
        return redirect(url_for('login'))

    # ✅ Query from database
    user = User.query.get(session['user_id'])
    if not user:
        flash("⚠️ User not found.")
        return redirect(url_for('login'))

    # ✅ Load orders and reviews from database
    user_orders = Order.query.filter_by(email=user.email).all()
    user_reviews = Review.query.filter_by(user_email=user.email).all()

    total_spent = sum(o.total or 0 for o in user_orders)
    user_stats = {
        "orders": len(user_orders),
        "reviews": len(user_reviews),
        "spent": total_spent
    }

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_name = request.form.get('name')
        new_password = request.form.get('password')

        if not check_password_hash(user.password, current_password):
            flash("❌ Incorrect current password.")
            return redirect(url_for('profile'))

        user.name = new_name or user.name
        if new_password:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        session['user_name'] = user.name
        flash("✅ Profile updated successfully.")
        return redirect(url_for('profile'))

    return render_template('profile.html', user=user.to_dict(), stats=user_stats)


@app.route('/logout')
def logout():
    session.clear()
    flash("👋 Logged out.")
    return redirect(url_for('index'))

@app.route('/delete/<product_id>', methods=['POST'])
def delete(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    product = Product.query.get(product_id)
    if not product:
        flash("❌ Product not found.")
        return redirect(url_for('admin'))

    # Delete images from filesystem
    images = json.loads(product.images or '[]')
    for img in images:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(product)
    db.session.commit()
    flash("🗑️ Product deleted.")
    return redirect(url_for('admin'))


@app.route('/product/<product_id>')
def product_detail(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("⚠️ Product not found.")
        return redirect(url_for('index'))

    product_dict = product.to_dict()
    products = load_data()
    product_dict['index'] = next(
        (i for i, p in enumerate(products) if p['id'] == product_id), 0
    )

    # Related products
    related = [
        p for p in products
        if p.get('category', '').lower() == product_dict['category'].lower()
        and p.get('id') != product_id
    ][:4]

    # ✅ Reviews by product_id
    product_reviews = Review.query.filter_by(product_id=product_id).all()
    product_reviews = [r.to_dict() for r in product_reviews]

    product_images = product_dict.get('images') or []

    return render_template(
        'product_detail.html',
        product=product_dict,
        related=related,
        reviews=product_reviews,
        product_images=product_images
    )



@app.route('/submit_review/<product_id>', methods=['POST'])
def submit_review(product_id):
    name = request.form.get('name')
    comment = request.form.get('comment')
    rating = int(request.form.get('rating'))

    if not name or not comment or rating not in range(1, 6):
        flash("❌ Please provide a name, comment, and rating (1-5).")
        return redirect(url_for('product_detail', product_id=product_id))

    # ✅ Save to database
    new_review = Review(
        product_id=product_id,
        name=name,
        comment=comment,
        rating=rating,
        user_id=session.get('user_id', ''),
        user_email=session.get('user_email', ''),
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    db.session.add(new_review)
    db.session.commit()

    flash("✅ Review submitted!")
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/restock_notify/<product_id>', methods=['POST'])
def restock_notify(product_id):
    email = request.form.get('email')
    product = Product.query.get(product_id)

    if not email or not product:
        flash("❌ Invalid request")
        return redirect(url_for('product_detail', product_id=product_id))

    # ✅ Save to database
    new_request = RestockRequest(
        email=email,
        product_name=product.name,
        product_id=product_id,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    db.session.add(new_request)
    db.session.commit()

    flash("✅ You'll be notified when it's back in stock!")
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/edit/<product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    product = Product.query.get(product_id)
    if not product:
        flash("❌ Product not found.")
        return redirect(url_for('admin'))

    if request.method == 'POST':
        product.name = request.form.get('name').title()
        product.price = request.form.get('price')
        product.category = request.form.get('category').title()
        product.description = request.form.get('description')
        product.stock = int(request.form.get('stock', 0))

        sale_price = request.form.get('sale_price')
        on_sale = 'on_sale' in request.form
        product.on_sale = on_sale

        if on_sale and sale_price:
            try:
                if float(sale_price) >= float(product.price):
                    flash("⚠️ Sale price must be less than the original price.")
                    return redirect(url_for('edit_product', product_id=product_id))
                product.sale_price = sale_price
            except ValueError:
                flash("⚠️ Invalid sale price entered.")
                return redirect(url_for('edit_product', product_id=product_id))
        else:
            product.sale_price = None

        product.featured = 'featured' in request.form

        sizes = request.form.get('sizes', '')
        colors = request.form.get('colors', '')
        product.sizes = json.dumps([s.strip() for s in sizes.split(',')]) if sizes else '[]'
        product.colors = json.dumps([c.strip() for c in colors.split(',')]) if colors else '[]'

        # Handle removing images
        remove_images = request.form.getlist('remove_images')
        current_images = json.loads(product.images or '[]')
        current_images = [img for img in current_images if img not in remove_images]

        # Delete removed images from filesystem
        for img in remove_images:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
            if os.path.exists(img_path):
                os.remove(img_path)

        # Handle new image uploads
        new_files = request.files.getlist('new_images')
        for f in new_files:
            if f and f.filename != '':
                filename = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_images.append(filename)

        product.images = json.dumps(current_images)
        db.session.commit()
        flash("✅ Product updated successfully!")
        return redirect(url_for('admin'))

    # Pass product as dict for template compatibility
    return render_template('edit_product.html', product=product.to_dict())



@app.route('/test_email')
def test_email():
    try:
        msg = Message("✅ Test Email from Flask App", recipients=[app.config['MAIL_USERNAME']])
        msg.body = "This is a test email to verify email sending from your Flask app."
        mail.send(msg)
        return "✅ Test email sent successfully!"
    except Exception as e:
        return f"❌ Email failed: {str(e)}"
    
@app.route('/test-logo')
def test_logo():
    return '''
    <img src="/static/logo/shopluxe.png" alt="Test Logo" style="height:100px;">
    '''
    
@app.route('/shop')
def shop():
    category = request.args.get('category', 'all')
    
    if category.lower() == 'all':
        products = get_all_products()
    else:
        products = get_products_by_category(category)

    featured_products = get_featured_products()
    current_time = datetime.now(timezone.utc)

    return render_template(
        'shop.html',
        products=products,
        featured_products=featured_products,
        selected_category=category,
        current_time=current_time
    )

    
# ------------------ CART ROUTES ------------------

# ------------------ CART ROUTES ------------------

def get_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']


# ✅ Add to Cart
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
    return redirect(request.referrer or url_for('index'))


# ✅ AJAX Add to Cart
@app.route('/add_to_cart_ajax/<product_id>', methods=['POST'])
def add_to_cart_ajax(product_id):
    color = request.form.get("color", "-")
    size = request.form.get("size", "-")

    cart = session.get('cart', [])
    found = next((item for item in cart if item['product_id'] == product_id and item.get('color') == color and item.get('size') == size), None)

    if found:
        found['quantity'] += 1
        message = "➕ Increased quantity in cart!"
    else:
        cart.append({'product_id': product_id, 'quantity': 1, 'color': color, 'size': size})
        message = "🛒 Added to cart!"

    session['cart'] = cart
    return jsonify({'success': True, 'message': message, 'count': len(cart)})


# ✅ Cart page
@app.route('/cart')
def cart():
    cart = get_cart()
    cart_items = []

    for item in cart:
        product_id = item.get("product_id")
        product = Product.query.get(product_id)
        if not product:
            continue

        p = product.to_dict()
        p['quantity'] = item.get('quantity', 1)
        p['color'] = item.get('color', '-')
        p['size'] = item.get('size', '-')
        cart_items.append(p)

    subtotal = sum(float(p['price']) * p['quantity'] for p in cart_items)
    payout_fee = round(min(subtotal * 0.0195, 50), 2)
    total = round(subtotal + payout_fee, 2)

    return render_template(
        'cart.html',
        cart_items=cart_items,
        subtotal=subtotal,
        payout_fee=payout_fee,
        total=total,
        active_page='cart'
    )


# ✅ Clear cart
@app.route('/clear-cart')
def clear_cart():
    session['cart'] = []
    return redirect(url_for('cart'))


# ✅ Increase quantity
@app.route('/cart/increase/<product_id>')
def increase_quantity(product_id):
    cart = get_cart()
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += 1
            break
    session['cart'] = cart
    return redirect(url_for('cart'))


# ✅ Decrease quantity
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


# ✅ Remove from cart
@app.route('/cart/remove/<product_id>')
def remove_from_cart(product_id):
    cart = get_cart()
    cart = [item for item in cart if item['product_id'] != product_id]
    session['cart'] = cart
    return redirect(url_for('cart'))


# ✅ Cart count API
@app.route('/cart_count')
def cart_count():
    return jsonify({'count': len(session.get('cart', []))})

from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# -------- Checkout Route --------
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = get_cart()
    cart_items = []

    for item in cart:
        product_id = item.get("product_id")
        product = Product.query.get(product_id)
        if not product:
            continue

        p = product.to_dict()
        p['quantity'] = item.get('quantity', 1)
        p['color'] = item.get('color', '-')
        p['size'] = item.get('size', '-')
        cart_items.append(p)

    if not cart_items:
        flash("⚠️ Your cart is empty.")
        return redirect(url_for("cart"))

    total = sum(float(p.get('price', 0)) * p['quantity'] for p in cart_items)

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        total=total,
        paystack_public_key=os.getenv('PAYSTACK_PUBLIC_KEY')
    )

@app.route('/track-order/<order_id>')
def track_order(order_id):
    order_id = unquote(order_id)
    order = Order.query.get(order_id)
    if not order:
        return "Order not found.", 404
    return render_template("track_order.html", order=order.to_dict())

# ✅ Mark an order as delivered
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
        base_url = request.url_root.rstrip('/')
        item_lines = [
            f"""<div style='margin-bottom:10px;'>
                <strong>{item.get('name')}</strong><br>
                Qty: {item.get('quantity', 1)} | GH₵ {item.get('price')}
            </div>""" for item in items
        ]
        user_html = render_template(
            'emails/user_delivered_email.html',
            name=order.name,
            product_name=''.join(item_lines),
            quantity=len(items),
            total=order.total,
            order_time=order.local_time,
            timezone=order.timezone
        )
        send_email(order.email, "✅ Your Order Has Been Delivered - ShopLuxe", user_html)
        flash("✅ Order marked delivered and email sent to user.")
    except Exception as e:
        print("❌ Email sending failed:", e)
        flash("⚠️ Order marked delivered but email could not be sent.")

    return redirect(url_for('admin'))

# ✅ Cancel an order
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
        track_order_url = url_for('track_order', order_id=quote(order_id), _external=True)
        cancelled_html = render_template(
            'emails/order_cancelled_email.html',
            name=order.name,
            order_id=order_id,
            track_order_url=track_order_url
        )
        send_email(order.email, "❌ Your ShopLuxe Order Has Been Cancelled", cancelled_html)
        flash("✅ Order cancelled and email sent to user.")
    except Exception as e:
        print("❌ Order cancelled but email could not be sent:", e)
        flash("⚠️ Order cancelled but email could not be sent.")

    return redirect(url_for('admin'))


@app.route('/order_confirmation')
def order_confirmation():
    reference = request.args.get("reference")
    order = Order.query.get(reference)
    if not order:
        flash("⚠️ Order not found.")
        return redirect(url_for('cart'))
    return render_template("order_confirmation.html", order=order.to_dict())

@app.route('/settings')
def settings():
    # You can later replace this with user settings logic
    return render_template('settings.html')


@app.route('/support')
def support():
    # You can later replace this with real support/help info
    return render_template('support.html')




@app.route("/healthz")
def health_check():
    return "OK", 200
  
# ------------------ WISHLIST ROUTES ------------------

# Helper: fetch product by ID + index
def get_product_by_id(product_id):
    products = load_data()
    for i, product in enumerate(products):
        if str(product.get('id')) == str(product_id):
            product['index'] = i  # ✅ store index for add_to_cart
            return product
    return None


# Initialize wishlist in session if not present
def get_wishlist():
    if 'wishlist' not in session:
        session['wishlist'] = []
    return session['wishlist']


# Add product to wishlist (non-AJAX fallback)
@app.route('/add_to_wishlist/<product_id>')
def add_to_wishlist(product_id):
    wishlist = get_wishlist()
    product = get_product_by_id(product_id)

    if not product:
        flash("❌ Product not found.")
        return redirect(request.referrer or url_for('index'))

    # Avoid duplicates
    if any(str(p['id']) == str(product_id) for p in wishlist):
        flash("❤️ Already in your wishlist.")
        return redirect(request.referrer or url_for('wishlist'))

    # ✅ Clean image path (prevent duplicate 'static/')
    image_path = product.get('image') or (
        product.get('images')[0] if product.get('images') else 'default.png'
    )
    if image_path.startswith('static/'):
        image_path = image_path.replace('static/', '')

    wishlist.append({
        'id': product['id'],
        'index': product['index'],  # ✅ added for add_to_cart
        'name': product['name'],
        'price': product['price'],
        'image': image_path
    })
    session['wishlist'] = wishlist
    flash("💖 Added to your wishlist!")
    return redirect(request.referrer or url_for('wishlist'))


# ✅ AJAX Toggle Wishlist
@app.route('/toggle_wishlist_ajax/<product_id>', methods=['POST'])
def toggle_wishlist_ajax(product_id):
    wishlist = session.get('wishlist', [])
    products = load_data()
    product = next((p for p in products if str(p.get('id')) == str(product_id)), None)

    if not product:
        return jsonify({'success': False, 'message': '❌ Product not found.'})

    in_wishlist = any(str(p['id']) == str(product_id) for p in wishlist)

    if in_wishlist:
        # Remove product
        wishlist = [p for p in wishlist if str(p['id']) != str(product_id)]
        session['wishlist'] = wishlist
        message = "💔 Removed from wishlist."
        in_wishlist = False
    else:
        # Add product
        product_with_index = get_product_by_id(product_id)

        # ✅ Clean image path (prevent duplicate 'static/')
        image_path = product_with_index.get('image') or (
            product_with_index.get('images')[0] if product_with_index.get('images') else 'default.png'
        )
        if image_path.startswith('static/'):
            image_path = image_path.replace('static/', '')

        wishlist.append({
            'id': product_with_index['id'],
            'index': product_with_index['index'],
            'name': product_with_index['name'],
            'price': product_with_index['price'],
            'image': image_path
        })
        session['wishlist'] = wishlist
        message = "💖 Added to wishlist!"
        in_wishlist = True

    return jsonify({
        'success': True,
        'in_wishlist': in_wishlist,
        'message': message,
        'count': len(wishlist)
    })


# ✅ View wishlist page
@app.route('/wishlist')
def wishlist():
    wishlist = get_wishlist()
    return render_template('wishlist.html', wishlist=wishlist, active_page='wishlist')


# ✅ Remove product from wishlist (non-AJAX)
@app.route('/remove_from_wishlist/<product_id>')
def remove_from_wishlist(product_id):
    wishlist = get_wishlist()
    updated_wishlist = [p for p in wishlist if str(p.get('id')) != str(product_id)]
    session['wishlist'] = updated_wishlist
    flash("❌ Removed from wishlist.")
    return redirect(url_for('wishlist'))


# ✅ Wishlist count API (for navbar live badge)
@app.route('/wishlist_count')
def wishlist_count():
    return jsonify({'count': len(session.get('wishlist', []))})
  
@app.route('/categories')
def categories():
    categories = [
        {'name': 'Shoes', 'image': 'shoes.jpg'},
        {'name': 'Tops', 'image': 'tops.jpg'},
        {'name': 'Bottoms', 'image': 'bottoms.jpg'},
        {'name': 'Men\'s', 'image': 'men.jpg'},
        {'name': 'Women\'s', 'image': 'women.jpg'},
        {'name': 'Kid\'s', 'image': 'kids.jpg'},
        {'name': 'Accessories', 'image': 'accessories.jpg'}
    ]
    return render_template('categories.html', categories=categories, active_page='categories')

@app.route('/rate-product', methods=['POST'])
def rate_product():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Login required"})

    data = request.get_json()
    product_id = data['product_id']
    rating = int(data['rating'])

    # ✅ Check for duplicate rating in database
    existing = Review.query.filter_by(
        product_id=product_id,
        user_id=session['user_id']
    ).first()

    if existing:
        return jsonify({"success": False, "message": "Already rated"})

    new_review = Review(
        product_id=product_id,
        user_id=session['user_id'],
        rating=rating,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    db.session.add(new_review)
    db.session.commit()

    return jsonify({"success": True})

app.jinja_env.add_extension('jinja2.ext.do')

with app.app_context():
    db.create_all()

if __name__ == "__main__":
  
    app.run()

