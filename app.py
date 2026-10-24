import os
import sqlite3
import secrets
from pathlib import Path
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import (
    check_password_hash, generate_password_hash
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "shop.db"
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "change-this-secret-before-deployment"
)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# Initial products displayed in the shop.
SEED_PRODUCTS = [
    {
        "name": "Fresh Oranges",
        "category": "fruit",
        "origin": "Premium selection",
        "price": 180.0,
        "unit": "kg",
        "description": "Juicy, bright and refreshing oranges.",
        "image": "images/oranges.jpg",
        "featured": 1,
    },
    {
        "name": "iG Apple Box",
        "category": "fruit",
        "origin": "USA",
        "price": 350.0,
        "unit": "kg",
        "description": "Crisp red apples with a sweet-tart bite.",
        "image": "images/ig-apple-box.jpg",
        "featured": 1,
    },
    {
        "name": "Premium Red Apples",
        "category": "fruit",
        "origin": "USA",
        "price": 350.0,
        "unit": "kg",
        "description": "Beautiful red apples with a crisp texture.",
        "image": "images/ig-apples-display.jpg",
        "featured": 1,
    },
    {
        "name": "Peruvian Blueberries",
        "category": "fruit",
        "origin": "Peru",
        "price": 649.0,
        "unit": "250 g",
        "description": "Plump, juicy berries with a bright flavour.",
        "image": "",
        "featured": 0,
    },
    {
        "name": "Parmigiano Reggiano",
        "category": "cheese",
        "origin": "Italy",
        "price": 1499.0,
        "unit": "250 g",
        "description": "Aged, nutty and full of savoury flavour.",
        "image": "",
        "featured": 0,
    },
]


def connect_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'fruit',
                origin TEXT DEFAULT '',
                price REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg',
                description TEXT DEFAULT '',
                image TEXT DEFAULT '',
                featured INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)

        # Insert demo products only when the catalogue is empty.
        count = con.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]

        if count == 0:
            con.executemany("""
                INSERT INTO products (
                    name, category, origin, price, unit,
                    description, image, featured
                )
                VALUES (
                    :name, :category, :origin, :price, :unit,
                    :description, :image, :featured
                )
            """, SEED_PRODUCTS)

        # Create the admin account from environment variables.
        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")

        if username and password:
            existing = con.execute(
                "SELECT id FROM admins WHERE username = ?",
                (username,)
            ).fetchone()

            if not existing:
                con.execute("""
                    INSERT INTO admins (username, password_hash)
                    VALUES (?, ?)
                """, (
                    username,
                    generate_password_hash(password)
                ))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(
                url_for("admin_login", next=request.path)
            )
        return fn(*args, **kwargs)

    return wrapper


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


@app.context_processor
def inject_cart_count():
    cart = session.get("cart", {})
    return {
        "cart_count": sum(cart.values())
    }


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    with connect_db() as con:
        featured = con.execute("""
            SELECT *
            FROM products
            WHERE active = 1 AND featured = 1
            ORDER BY id DESC
        """).fetchall()

        if not featured:
            featured = con.execute("""
                SELECT *
                FROM products
                WHERE active = 1
                ORDER BY id DESC
                LIMIT 3
            """).fetchall()

    return render_template(
        "index.html",
        featured=featured
    )


# ---------------- SHOP PAGE ----------------

@app.route("/shop")
def shop():
    category = request.args.get(
        "category", ""
    ).strip()

    query = request.args.get("q", "").strip()

    sql = "SELECT * FROM products WHERE active = 1"
    args = []

    if category in {"fruit", "cheese"}:
        sql += " AND category = ?"
        args.append(category)

    if query:
        sql += """
            AND (
                name LIKE ?
                OR origin LIKE ?
                OR description LIKE ?
            )
        """
        args.extend([f"%{query}%"] * 3)

    sql += " ORDER BY featured DESC, id DESC"

    with connect_db() as con:
        products = con.execute(sql, args).fetchall()

    return render_template(
        "shop.html",
        products=products,
        category=category,
        query=query
    )


# ---------------- PRODUCT DETAILS ----------------

@app.route("/product/<int:product_id>")
def product(product_id):
    with connect_db() as con:
        item = con.execute("""
            SELECT *
            FROM products
            WHERE id = ? AND active = 1
        """, (product_id,)).fetchone()

    if not item:
        abort(404)

    return render_template(
        "product.html",
        p=item
    )


# ---------------- SHOPPING CART ----------------

@app.route("/cart")
def cart():
    cart_data = session.get("cart", {})
    items = []
    total = 0

    with connect_db() as con:
        for product_id, qty in cart_data.items():
            item = con.execute("""
                SELECT *
                FROM products
                WHERE id = ? AND active = 1
            """, (int(product_id),)).fetchone()

            if item:
                subtotal = item["price"] * qty
                total += subtotal

                items.append({
                    "product": item,
                    "qty": qty,
                    "subtotal": subtotal
                })

    return render_template(
        "cart.html",
        items=items,
        total=total
    )


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    with connect_db() as con:
        exists = con.execute("""
            SELECT id
            FROM products
            WHERE id = ? AND active = 1
        """, (product_id,)).fetchone()

    if not exists:
        abort(404)

    try:
        qty = max(
            1,
            min(99, int(request.form.get("qty", 1)))
        )
    except (TypeError, ValueError):
        qty = 1

    cart_data = session.get("cart", {})
    key = str(product_id)

    cart_data[key] = min(
        99,
        cart_data.get(key, 0) + qty
    )

    session["cart"] = cart_data

    flash("Added to your cart!", "success")

    return redirect(
        request.referrer or url_for("cart")
    )


@app.route(
    "/cart/remove/<int:product_id>",
    methods=["POST"]
)
def remove_from_cart(product_id):
    cart_data = session.get("cart", {})
    cart_data.pop(str(product_id), None)
    session["cart"] = cart_data

    return redirect(url_for("cart"))


# ---------------- ABOUT PAGE ----------------

@app.route("/about")
def about():
    return render_template("about.html")


# ---------------- ADMIN LOGIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get("password", "")

        with connect_db() as con:
            admin = con.execute("""
                SELECT *
                FROM admins
                WHERE username = ?
            """, (username,)).fetchone()

        if admin and check_password_hash(
            admin["password_hash"], password
        ):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]

            # Redirect only to a local path.
            next_url = request.args.get("next", "")

            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("admin_dashboard")

            return redirect(next_url)

        flash("Invalid username or password.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)

    return redirect(url_for("home"))


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    with connect_db() as con:
        products = con.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
        """).fetchall()

        active_count = con.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE active = 1
        """).fetchone()[0]

        fruit_count = con.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE active = 1 AND category = 'fruit'
        """).fetchone()[0]

        cheese_count = con.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE active = 1 AND category = 'cheese'
        """).fetchone()[0]

    return render_template(
        "admin_dashboard.html",
        products=products,
        active_count=active_count,
        fruit_count=fruit_count,
        cheese_count=cheese_count
    )


# ---------------- ADD / EDIT PRODUCTS ----------------

@app.route(
    "/admin/product/new",
    methods=["GET", "POST"]
)
@app.route(
    "/admin/product/<int:product_id>/edit",
    methods=["GET", "POST"]
)
@admin_required
def admin_product_form(product_id=None):
    with connect_db() as con:
        item = None

        if product_id:
            item = con.execute("""
                SELECT *
                FROM products
                WHERE id = ?
            """, (product_id,)).fetchone()

    if product_id and not item:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "fruit")
        origin = request.form.get("origin", "").strip()
        description = request.form.get("description", "").strip()
        unit = request.form.get("unit", "kg").strip()

        try:
            price = max(
                0,
                float(request.form.get("price", 0))
            )
        except (TypeError, ValueError):
            price = 0

        featured = 1 if request.form.get("featured") else 0
        active = 1 if request.form.get("active") else 0

        if not name or category not in {"fruit", "cheese"}:
            flash(
                "Enter a product name and choose a valid category.",
                "error"
            )
            return redirect(request.url)

        image_path = item["image"] if item else ""

        upload = request.files.get("image")

        if upload and upload.filename:
            if not allowed_file(upload.filename):
                flash(
                    "Use a PNG, JPG, JPEG or WEBP image.",
                    "error"
                )
                return redirect(request.url)

            filename = secure_filename(upload.filename)
            filename = f"{secrets.token_hex(6)}_{filename}"

            upload.save(UPLOAD_FOLDER / filename)
            image_path = f"uploads/{filename}"

        elif request.form.get("image_url", "").strip():
            image_path = request.form["image_url"].strip()

        values = (
            name,
            category,
            origin,
            price,
            unit,
            description,
            image_path,
            featured,
            active
        )

        with connect_db() as con:
            if item:
                con.execute("""
                    UPDATE products
                    SET name = ?, category = ?, origin = ?,
                        price = ?, unit = ?, description = ?,
                        image = ?, featured = ?, active = ?
                    WHERE id = ?
                """, values + (product_id,))
            else:
                con.execute("""
                    INSERT INTO products (
                        name, category, origin, price, unit,
                        description, image, featured, active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, values)

        flash("Product saved successfully.", "success")

        return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_product_form.html",
        item=item
    )


# ---------------- DELETE PRODUCTS ----------------

@app.route(
    "/admin/product/<int:product_id>/delete",
    methods=["POST"]
)
@admin_required
def admin_delete_product(product_id):
    with connect_db() as con:
        con.execute(
            "DELETE FROM products WHERE id = ?",
            (product_id,)
        )

    flash("Product deleted.", "success")

    return redirect(url_for("admin_dashboard"))


# ---------------- UPLOAD ERROR ----------------

@app.errorhandler(413)
def too_large(_error):
    flash(
        "Image is too large. Please upload an image under 8 MB.",
        "error"
    )

    return redirect(
        request.referrer or url_for("admin_dashboard")
    )


# Create database tables and seed initial products.
init_db()


if __name__ == "__main__":
    app.run(debug=True)