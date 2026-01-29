import sys
sys.stdout.reconfigure(encoding='utf-8')
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer  # ✅ Add this
import os, json, uuid
from uuid import uuid4
from datetime import datetime,timezone, timedelta 
import resend
from flask import Flask
import requests


from werkzeug.middleware.proxy_fix import ProxyFix
from urllib.parse import unquote
from urllib.parse import quote
from flask import url_for
from dotenv import load_dotenv
load_dotenv()  # ✅ Load environment variables from .env (Render handles this automatically)



app = Flask(__name__)
app.jinja_env.globals['session'] = session
app.secret_key = 'secret123'
app.config['UPLOAD_FOLDER'] = 'static/shoes'
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# ✅ Add this line below secret key
serializer = URLSafeTimedSerializer(app.secret_key)


DATA_FILE = 'data.json'
RESTOCK_FILE = 'restock_requests.json'
REVIEWS_FILE = 'reviews.json'
USERS_FILE = 'users.json'
ADMIN_PASSWORD = 'Mohammed_@3'

# Email config
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
mail = Mail(app)


# Helper functions
def load_data():
    if not os.path.exists(DATA_FILE): return []
    with open(DATA_FILE, 'r') as f: return json.load(f)


def save_data(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)

def load_restock_requests():
    if not os.path.exists(RESTOCK_FILE): return []
    with open(RESTOCK_FILE, 'r') as f: return json.load(f)

def save_restock_requests(data):
    with open(RESTOCK_FILE, 'w') as f: json.dump(data, f, indent=4)

def load_reviews():
    if not os.path.exists(REVIEWS_FILE): return []
    with open(REVIEWS_FILE, 'r') as f: return json.load(f)

def save_reviews(data):
    with open(REVIEWS_FILE, 'w') as f: json.dump(data, f, indent=4)

def load_users():
    if not os.path.exists(USERS_FILE): return []
    with open(USERS_FILE, 'r') as f: return json.load(f)

def save_users(data):
    with open(USERS_FILE, 'w') as f: json.dump(data, f, indent=4)

# Get all products
def get_all_products():
    return load_data()  # Returns the full list of products

# Get products by category
def get_products_by_category(category):
    products = load_data()
    return [p for p in products if p.get('category', '').lower() == category.lower()]

# Get featured products (e.g., newest 4 products)
def get_featured_products():
    products = load_data()
    # Sort products by timestamp descending
    products_sorted = sorted(products, key=lambda x: x.get('timestamp', ''), reverse=True)
    return products_sorted[:4]  # Returns top 4 newest products
  
# ✅ Define orders file path (consistent with your setup)
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "data/orders.json")

# ✅ Load all orders safely
def load_orders():
    try:
        with open(ORDERS_FILE, 'r') as f:
            orders = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    # ✅ Normalize timestamp formats for old entries
    from datetime import datetime
    for o in orders:
        for key in ['delivered_time', 'cancelled_time', 'completed_time']:
            if key in o and isinstance(o[key], str) and 'T' in o[key]:
                try:
                    o[key] = datetime.fromisoformat(o[key]).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

    return orders


# ✅ Save orders back to file
def save_orders(data):
    with open(ORDERS_FILE, 'w') as f:
        json.dump(data, f, indent=4)


# Routes

# Load Paystack keys from environment

# ✅ Fetch Paystack keys from .env
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")

print("PAYSTACK_PUBLIC_KEY:", PAYSTACK_PUBLIC_KEY)  # 🔍 Debug: should start with pk_live_ or pk_test_





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
@app.route('/initialize_payment', methods=['POST'])
def initialize_payment():
    data = request.get_json()
    email = data.get('email')
    amount = int(data.get('amount')) * 100  # convert to pesewas

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "email": email,
        "amount": amount,
        "callback_url": url_for('verify_payment', _external=True)
    }

    response = requests.post('https://api.paystack.co/transaction/initialize', json=payload, headers=headers)
    return jsonify(response.json())


# -------------------------------
# ✅ Verify Payment
# -------------------------------
@app.route('/verify_payment')
def verify_payment():
    reference = request.args.get('reference')

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
    result = response.json()

    if result.get('data', {}).get('status') == 'success':
        # ✅ Payment successful — now save the order
        order = session.get('pending_order')

        if order:
            order['payment_status'] = 'Paid'
            order['status'] = 'Paid'  # ✅ Added so it shows correctly in admin
            order['payment_reference'] = reference
            order['paid_time'] = datetime.now(timezone.utc).isoformat()

            orders_file = os.path.join(os.path.dirname(__file__), "data/orders.json")
            if os.path.exists(orders_file):
                with open(orders_file, 'r', encoding='utf-8') as f:
                    try:
                        existing_orders = json.load(f)
                    except json.JSONDecodeError:
                        existing_orders = []
            else:
                existing_orders = []

            existing_orders.append(order)
            with open(orders_file, 'w', encoding='utf-8') as f:
                json.dump(existing_orders, f, indent=2)

            # ✅ Optionally send admin + user emails
            try:
                name = order['name']
                email = order['email']
                total = order['total']
                base_url = request.url_root.rstrip('/')
                track_order_url = url_for('track_order', order_id=quote(order['id']), _external=True)

                # Admin email
                admin_html = render_template(
                    'emails/admin_order_email.html',
                    name=name,
                    email=email,
                    phone=order['phone'],
                    product_name=''.join(
                        f"<p>{i['name']} ({i['quantity']}x)</p>" for i in order['items']
                    ),
                    total=total,
                    order_time=order['local_time'],
                    track_order_url=track_order_url,
                    base_url=base_url
                )
                send_email("vybezkhid7@gmail.com", "📦 New Paid Order - ShopLuxe", admin_html)

                # User email
                user_html = render_template(
                    'emails/user_order_email.html',
                    name=name,
                    product_name=''.join(
                        f"<p>{i['name']} ({i['quantity']}x)</p>" for i in order['items']
                    ),
                    total=total,
                    order_time=order['local_time'],
                    track_order_url=track_order_url
                )
                send_email(email, "✅ Payment Received - ShopLuxe", user_html)
            except Exception as e:
                print("⚠️ Email sending failed:", e)

            # ✅ Clear session data
            session.pop('pending_order', None)
            session.pop('cart', None)

        # ✅ Show success page
        return render_template("success.html", payment=result['data'])

    else:
        return render_template("failure.html", payment=result['data'])






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


# ✅ Set API key directly for testing (you can remove this later and use env var)
resend.api_key = "re_hc8dC54W_99qkQMJq4UcVRErCEo6nsGDM"

# ✅ Test email (you can comment this out later)
r = resend.Emails.send({
    "from": "onboarding@resend.dev",
    "to": "vybezkhid7@gmail.com",
    "subject": "Hello World",
    "html": "<p>Congrats on sending your <strong>first email</strong>!</p>"
})

print("Test email sent:", r)

# ✅ For production: use environment variable instead of hardcoding
# (Set RESEND_API_KEY in Render environment variables)
# resend.api_key = os.getenv("RESEND_API_KEY")

def send_email(to, subject, html):
    """Reusable function to send emails via Resend"""
    try:
        resend.Emails.send({
            "from": "Shopluxe <onboarding@resend.dev>",
            "to": [to],
            "subject": subject,
            "html": html
        })
        print("✅ Email sent successfully")
    except Exception as e:
        print("❌ Email sending failed:", e)


# ✅ Example call
send_email("vybezkhid7@gmail.com", "New Order", "<p>New order received!</p>")


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


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_data()
    reviews = load_reviews()
    orders = load_orders()

    # ---------------------- ADD NEW PRODUCT ---------------------- #
    if request.method == 'POST':
        name = request.form.get('name', '').title()
        price = request.form.get('price', '')
        category = request.form.get('category', '').title()
        description = request.form.get('description', '')
        stock = int(request.form.get('stock', 0))

        # Sale & Featured
        on_sale = 'on_sale' in request.form
        sale_price = request.form.get('sale_price', '')
        featured = 'featured' in request.form

        # Colors & Sizes
        colors = [c.strip() for c in request.form.get('colors', '').split(',')] if request.form.get('colors') else []
        sizes = [s.strip() for s in request.form.get('sizes', '').split(',')] if request.form.get('sizes') else []

        # Validate sale price
        if on_sale and sale_price:
            try:
                if float(sale_price) >= float(price):
                    flash("⚠️ Sale price must be less than the original price.")
                    return redirect(url_for('admin'))
            except ValueError:
                flash("⚠️ Invalid sale price entered.")
                return redirect(url_for('admin'))

        # Handle image uploads
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

        # Create new product
        new_product = {
            'id': str(uuid4()),
            'name': name,
            'price': price,
            'sale_price': sale_price if on_sale and sale_price else None,
            'on_sale': on_sale,
            'featured': featured,
            'category': category,
            'description': description,
            'stock': stock,
            'colors': colors,
            'sizes': sizes,
            'images': image_filenames,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        products.append(new_product)
        save_data(products)
        flash("✅ Product added successfully!")
        return redirect(url_for('admin'))

    # ---------------------- NORMALIZE ORDERS ---------------------- #
    for order in orders:
        order['id'] = order.get('id', str(uuid4()))
        order['status'] = order.get('status', 'Pending')
        order['local_time'] = order.get('local_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        order['delivered_time'] = order.get('delivered_time', '')
        order['cancelled_time'] = order.get('cancelled_time') or (
            order['local_time'] if order['status'] == 'Cancelled' else ''
        )

        # 🧠 Support both 'items' and 'products'
        if 'items' in order and not order.get('products'):
            order['products'] = order['items']

        # 🧩 Fallback for legacy single-item orders
        if not order.get('products'):
            order['products'] = [{
                'name': order.get('product_name', 'Unknown Product'),
                'price': order.get('total', 0),
                'quantity': order.get('quantity', 1),
                'color': order.get('color', '-'),
                'size': order.get('size', '-')
            }]

        # ✅ Mark paid orders clearly for display
        if order.get('payment_status') == 'Paid' and order['status'] == 'Pending':
            order['status'] = 'Paid'

        # Unified completed_time for template
        if order['status'] == 'Delivered':
            order['completed_time'] = order['delivered_time']
        elif order['status'] == 'Cancelled':
            order['completed_time'] = order['cancelled_time']
        else:
            order['completed_time'] = ''

    # ---------------------- RENDER TEMPLATE ---------------------- #
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

        users = load_users()
        if any(u['email'] == email for u in users):
            flash("❌ Email already registered.")
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        users.append({'name': name, 'email': email, 'password': hashed_password})
        save_users(users)

        # Send welcome email
        try:
            msg = Message("🎉 Welcome to ShopLuxe!", recipients=[email])
            msg.body = f"""Hello {name},

Thanks for signing up with ShopLuxe!

You can now log in and start exploring amazing products.

Best regards,  
ShopLuxe Team
"""
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
        users = load_users()
        user = next((u for u in users if u['email'] == email), None)

        if user and check_password_hash(user['password'], password):
            session['user'] = {'name': user['name'], 'email': user['email']}
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
        users = load_users()
        user = next((u for u in users if u['email'] == email), None)

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

# Admin login lockout config
MAX_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=5)


@app.route('/reset_with_token/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    try:
        email = serializer.loads(token, salt='reset-password', max_age=1800)  # 30 min
    except:
        flash("❌ Reset link expired or invalid.")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password')
        if not new_password:
            flash("❌ Please enter a new password.")
            return redirect(url_for('reset_with_token', token=token))

        users = load_users()
        user = next((u for u in users if u['email'] == email), None)
        if user:
            user['password'] = generate_password_hash(new_password)
            save_users(users)
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
    if 'user' not in session:
        flash("⚠️ Please log in first.")
        return redirect(url_for('login'))

    users = load_users()
    user = next((u for u in users if u['email'] == session['user']['email']), None)
    if not user:
        flash("⚠️ User not found.")
        return redirect(url_for('login'))

    # ✅ Load all orders and reviews
    orders = load_json('data/orders.json')
    reviews = load_json('data/reviews.json')

    # ✅ Filter for this specific user
    user_orders = [o for o in orders if o.get('user_email') == user['email']]
    user_reviews = [r for r in reviews if r.get('user_email') == user['email']]

    # ✅ Compute totals
    total_spent = sum(o.get('total', 0) for o in user_orders)
    order_count = len(user_orders)
    review_count = len(user_reviews)

    user_stats = {
        "orders": order_count,
        "reviews": review_count,
        "spent": total_spent
    }

    # ✅ Handle profile update
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_name = request.form.get('name')
        new_password = request.form.get('password')

        if not check_password_hash(user['password'], current_password):
            flash("❌ Incorrect current password.")
            return redirect(url_for('profile'))

        user['name'] = new_name or user['name']
        if new_password:
            user['password'] = generate_password_hash(new_password)

        save_users(users)
        flash("✅ Profile updated successfully.")
        return redirect(url_for('profile'))

    # ✅ Pass everything to the template
    return render_template('profile.html', user=user, stats=user_stats)



@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("👋 Logged out.")
    return redirect(url_for('index'))


@app.route('/delete/<int:index>', methods=['POST'])
def delete(index):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_data()
    if 0 <= index < len(products):
        # Only try to delete image if it exists
        if 'image' in products[index] and products[index]['image']:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], products[index]['image'])
            if os.path.exists(image_path):
                os.remove(image_path)

        # Remove product from the list
        del products[index]
        save_data(products)
        flash("🗑️ Product deleted.")
    else:
        flash("❌ Invalid product index.")

    return redirect(url_for('admin'))


@app.route('/product/<product_id>')
def product_detail(product_id):
    products = load_data()
    reviews = load_reviews()

    # Find product by ID safely
    product = next((p for p in products if p.get('id') == product_id), None)
    if not product:
        flash("⚠️ Product not found.")
        return redirect(url_for('index'))

    # Optional: add 'index' for templates needing it
    product['index'] = products.index(product)

    # Related products (max 4)
    product_category = product.get('category', '').strip().lower()
    related = []
    for p in products:
        if p.get('category', '').strip().lower() == product_category and p.get('id') != product_id:
            # Ensure each related product has an 'id'
            if 'id' not in p:
                continue
            related.append(p)
        if len(related) >= 4:
            break

    # Images for product_detail page
    product_images = product.get('images') or ([product.get('image')] if product.get('image') else [])

    # Product reviews
    product_reviews = [r for r in reviews if r.get('product_index') == product['index']]

    return render_template(
        'product_detail.html',
        product=product,
        related=related,
        reviews=product_reviews,
        product_images=product_images
    )


@app.route('/submit_review/<int:index>', methods=['POST'])
def submit_review(index):
    name = request.form.get('name')
    comment = request.form.get('comment')
    rating = int(request.form.get('rating'))
    timestamp = datetime.now(timezone.utc).isoformat()

    if not name or not comment or rating not in range(1, 6):
        flash("❌ Please provide a name, comment, and rating (1-5).")
        return redirect(url_for('product_detail', index=index))

    reviews = load_reviews()
    reviews.append({
        'product_index': index,
        'name': name,
        'comment': comment,
        'rating': rating,
        'timestamp':  datetime.now(timezone.utc).isoformat()
    })
    save_reviews(reviews)

    flash("✅ Review submitted!")
    return redirect(url_for('product_detail', index=index))

@app.route('/restock_notify/<int:index>', methods=['POST'])
def restock_notify(index):
    email = request.form.get('email')
    products = load_data()
    if not email or index < 0 or index >= len(products):
        flash("❌ Invalid request")
        return redirect(url_for('product_detail', index=index))
    requests = load_restock_requests()
    product = products[index]
    requests.append({
        'email': email,
        'product_name': product['name'],
        'product_index': index,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    save_restock_requests(requests)
    flash("✅ You’ll be notified when it's back in stock!")
    return redirect(url_for('product_detail', index=index))

@app.route('/edit/<product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_data()
    product = next((p for p in products if p.get('id') == product_id), None)
    if not product:
        flash("❌ Product not found.")
        return redirect(url_for('admin'))

    if request.method == 'POST':
        # Update basic fields
        product['name'] = request.form.get('name').title()
        product['price'] = request.form.get('price')
        product['category'] = request.form.get('category').title()
        product['description'] = request.form.get('description')
        product['stock'] = int(request.form.get('stock', 0))

        # ✅ Handle sale toggle and sale price
        sale_price = request.form.get('sale_price')
        on_sale = 'on_sale' in request.form
        product['on_sale'] = on_sale
        if on_sale and sale_price:
            try:
                if float(sale_price) >= float(product['price']):
                    flash("⚠️ Sale price must be less than the original price.")
                    return redirect(url_for('edit_product', product_id=product_id))
                product['sale_price'] = sale_price
            except ValueError:
                flash("⚠️ Invalid sale price entered.")
                return redirect(url_for('edit_product', product_id=product_id))
        else:
            product.pop('sale_price', None)

        # ✅ Handle Featured checkbox
        product['featured'] = 'featured' in request.form

        # ✅ Handle sizes and colors
        sizes = request.form.get('sizes', '')
        colors = request.form.get('colors', '')
        product['sizes'] = [s.strip() for s in sizes.split(',')] if sizes else []
        product['colors'] = [c.strip() for c in colors.split(',')] if colors else []

        # Handle removing images
        remove_images = request.form.getlist('remove_images')
        if 'images' not in product:
            product['images'] = [product.get('image')] if product.get('image') else []

        product['images'] = [img for img in product['images'] if img not in remove_images]

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
                product['images'].append(filename)

        # Ensure main 'image' field always exists
        if product['images']:
            product['image'] = product['images'][0]
        else:
            product['image'] = None

        save_data(products)
        flash("✅ Product updated successfully!")
        return redirect(url_for('admin'))

    return render_template('edit_product.html', product=product)



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

# ✅ Initialize cart in session if not present
def get_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']


# ✅ Add to Cart (AJAX + fallback)
# ✅ Add to Cart (includes color & size)
@app.route('/add_to_cart/<int:index>', methods=['POST'])
def add_to_cart(index):
    quantity = int(request.form.get("quantity", 1))
    color = request.form.get("color", "-")
    size = request.form.get("size", "-")

    cart = get_cart()

    # Check if the exact same product (index+color+size) already exists
    for item in cart:
        if item['index'] == index and item.get('color') == color and item.get('size') == size:
            item['quantity'] += quantity
            break
    else:
        cart.append({'index': index, 'quantity': quantity, 'color': color, 'size': size})

    session['cart'] = cart

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': '🛒 Added to cart!', 'count': len(cart)})

    flash("🛒 Product added to cart!")
    return redirect(request.referrer or url_for('index'))



# ✅ Cart count API (for navbar live badge)
@app.route('/cart_count')
def cart_count():
    return jsonify({'count': len(session.get('cart', []))})
  
  # 🛒 AJAX Add to Cart (Live)
# ✅ AJAX Add to Cart (includes color & size)
@app.route('/add_to_cart_ajax/<int:index>', methods=['POST'])
def add_to_cart_ajax(index):
    color = request.form.get("color", "-")
    size = request.form.get("size", "-")

    cart = session.get('cart', [])
    found = next((item for item in cart if item['index'] == index and item.get('color') == color and item.get('size') == size), None)

    if found:
        found['quantity'] += 1
        message = "➕ Increased quantity in cart!"
    else:
        cart.append({'index': index, 'quantity': 1, 'color': color, 'size': size})
        message = "🛒 Added to cart!"

    session['cart'] = cart
    return jsonify({'success': True, 'message': message, 'count': len(cart)})



@app.route('/cart')
def cart():
    cart = get_cart()
    products = load_data()
    cart_items = []

    for item in cart:
        index = item.get("index")
        quantity = item.get("quantity", 1)
        color = item.get("color", "-")
        size = item.get("size", "-")

        if 0 <= index < len(products):
            product = products[index].copy()
            product['quantity'] = quantity
            product['index'] = index
            product['color'] = color
            product['size'] = size

            # ✅ Ensure image exists
            if 'images' in product and product['images']:
                product['image'] = product['images'][0]
            elif 'image' in product:
                product['image'] = product['image']
            else:
                product['image'] = 'default.png'

            cart_items.append(product)

    # 🧮 Totals
    subtotal = sum(float(p['price']) * p['quantity'] for p in cart_items)

    # ✅ Accurate Paystack payout fee: 1.95% capped at GHS 50
    payout_fee = round(min(subtotal * 0.0195, 50), 2)
    total = round(subtotal + payout_fee, 2)

    return render_template(
        'cart.html',
        cart_items=cart_items,
        subtotal=subtotal,
        payout_fee=payout_fee,  # renamed variable
        total=total,
        active_page='cart'
    )



@app.route('/clear-cart')
def clear_cart():
    session['cart'] = []  # ✅ correct: cart is a list of dicts
    return redirect(url_for('cart'))

@app.route('/cart/increase/<int:index>')
def increase_quantity(index):
    cart = get_cart()
    for item in cart:
        if item['index'] == index:
            item['quantity'] += 1
            break
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/cart/decrease/<int:index>')
def decrease_quantity(index):
    cart = get_cart()
    for item in cart:
        if item['index'] == index:
            item['quantity'] -= 1
            if item['quantity'] < 1:
                cart.remove(item)
            break
    session['cart'] = cart
    return redirect(url_for('cart'))


@app.route('/cart/remove/<int:index>')
def remove_from_cart(index):
    cart = get_cart()
    cart = [item for item in cart if item['index'] != index]
    session['cart'] = cart
    return redirect(url_for('cart'))


from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# -------- Checkout Route --------
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = get_cart()
    products = load_data()
    cart_items = []

    # ✅ Build cart items with color, size, and quantity
    for item in cart:
        index = item.get("index")
        quantity = item.get("quantity", 1)
        color = item.get("color", "-")
        size = item.get("size", "-")

        if 0 <= index < len(products):
            product = products[index].copy()
            product['quantity'] = quantity
            product['id'] = products[index].get('id', index)
            product['color'] = color
            product['size'] = size
            cart_items.append(product)

    total = sum(float(p['price']) * p['quantity'] for p in cart_items)

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        timezone_str = request.form.get('timezone', 'UTC')

        if not name or not email or not phone:
            flash("❌ All fields are required.")
            return redirect(url_for('checkout'))

        utc_now = datetime.now(timezone.utc)
        try:
            user_zone = ZoneInfo(timezone_str)
        except Exception:
            user_zone = ZoneInfo("UTC")
        local_time = utc_now.astimezone(user_zone)
        formatted_time = local_time.strftime("%b %d, %Y, %I:%M %p")

        order_id = str(uuid.uuid4())
        base_url = request.url_root.rstrip('/')

        # ✅ Prepare order (not saving yet)
        order = {
            'id': order_id,
            'name': name,
            'email': email,
            'phone': phone,
            'items': [
                {
                    "name": p["name"],
                    "price": p["price"],
                    "quantity": p["quantity"],
                    "color": p.get("color", "-"),
                    "size": p.get("size", "-")
                }
                for p in cart_items
            ],
            'total': total,
            'timestamp': utc_now.isoformat(),
            'local_time': formatted_time,
            'timezone': timezone_str
        }

        # ✅ Save order temporarily in session until payment is verified
        session['pending_order'] = order

        # ✅ Redirect to Paystack payment initialization
        return render_template(
            'payment.html',  # your template where Paystack is initialized
            email=email,
            amount=total,
            paystack_public_key=os.getenv('PAYSTACK_PUBLIC_KEY'),
            reference=order_id
        )

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        total=total,
        paystack_public_key=os.getenv('PAYSTACK_PUBLIC_KEY')  # 👈 add this line
    )





@app.route('/track-order/<order_id>')
def track_order(order_id):
    order_id = unquote(order_id)
    orders_file = "data/orders.json"  # or persistent path on Render
    if not os.path.exists(orders_file):
        return "No orders found.", 404

    with open(orders_file, "r") as f:
        orders = json.load(f)

    order = next((o for o in orders if str(o["id"]) == str(order_id)), None)
    if not order:
        return "Order not found.", 404

    return render_template("track_order.html", order=order)


# ✅ Mark an order as delivered
@app.route('/mark_delivered/<order_id>', methods=['POST'])
def mark_delivered(order_id):
    orders = load_orders()
    order_found = False

    for o in orders:
        if str(o['id']) == str(order_id):
            o['status'] = 'Delivered'

            # ✅ Get user's timezone safely
            timezone_str = o.get('timezone', 'UTC')
            try:
                user_tz = pytz.timezone(timezone_str)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.UTC

            # ✅ Store localized timestamp for history display
            local_time = datetime.now(user_tz).strftime("%Y-%m-%d %H:%M:%S")
            o['delivered_time'] = local_time
            o['completed_time'] = local_time  # ✅ Add for history tracking

            order_found = True
            user_email = o.get('email')
            name = o.get('name')
            items = o.get('products', [])  # ✅ Ensure consistency with template
            total = o.get('total', 0)
            formatted_time = o.get('local_time', '')
            break

    if not order_found:
        flash("⚠️ Order not found.")
        return redirect(url_for('admin'))

    save_orders(orders)

    # ✅ Send delivery email to user
    try:
        base_url = request.url_root.rstrip('/')
        item_lines = [
            f"""
            <div style='display:flex;align-items:center;margin-bottom:10px;border:1px solid #eee;padding:8px;border-radius:10px;'>
                <img src='{base_url}/static/shoes/{(item.get('images') or [None])[0]}' 
                     alt='{item.get('name')}' 
                     style='width:60px;height:60px;object-fit:cover;border-radius:8px;margin-right:10px;'>
                <div>
                    <strong>{item.get('name')}</strong><br>
                    Qty: {item.get('quantity', 1)} | GH₵ {item.get('price')}
                </div>
            </div>
            """ for item in items
        ]

        user_html = render_template(
            'emails/user_delivered_email.html',
            name=name,
            product_name=''.join(item_lines),
            quantity=len(items),
            total=total,
            order_time=formatted_time,
            timezone=timezone_str
        )
        send_email(user_email, "✅ Your Order Has Been Delivered - ShopLuxe", user_html)
        flash("✅ Order marked delivered and email sent to user.")
    except Exception as e:
        print("❌ Email sending failed:", e)
        flash("⚠️ Order marked delivered but email could not be sent.")

    return redirect(url_for('admin'))


# ✅ Cancel an order
@app.route('/cancel_order/<order_id>', methods=['POST'])
def cancel_order(order_id):
    orders = load_orders()
    order_found = False
    for o in orders:
        if str(o['id']) == str(order_id):
            o['status'] = 'Cancelled'

            # ✅ Get user's timezone safely
            timezone_str = o.get('timezone', 'UTC')
            try:
                user_tz = pytz.timezone(timezone_str)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.UTC

            # ✅ Store localized timestamp for history display
            local_time = datetime.now(user_tz).strftime("%Y-%m-%d %H:%M:%S")
            o['cancelled_time'] = local_time
            o['completed_time'] = local_time  # ✅ Add for history tracking

            order_found = True
            user_email = o.get('email')
            user_name = o.get('name')
            break

    if order_found:
        save_orders(orders)

        # ✅ Send cancelled email to user
        try:
            track_order_url = url_for('track_order', order_id=quote(order_id), _external=True)
            cancelled_html = render_template(
                'emails/order_cancelled_email.html',
                name=user_name,
                order_id=order_id,
                track_order_url=track_order_url
            )
            send_email(user_email, "❌ Your ShopLuxe Order Has Been Cancelled", cancelled_html)
            flash("✅ Order cancelled and email sent to user.")
        except Exception as e:
            print("❌ Order cancelled but email could not be sent:", e)
            flash("⚠️ Order cancelled but email could not be sent.")
    else:
        flash("❌ Order not found.")

    return redirect(url_for('admin'))


@app.route('/order_confirmation')
def order_confirmation():
    order_info = session.get('order_info')
    if not order_info:
        flash("⚠️ No order found.")
        return redirect(url_for('cart'))
    return render_template('order_confirmation.html', order=order_info)


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






if __name__ == "__main__":
    app.run()

