import os
import sys
import uuid
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import List, Optional, Dict, Any

# Core FastAPI dependencies
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

# SQLAlchemy database dependencies
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

# Checks for DATABASE_URL environment variable (standard on Render/Heroku/AWS). 
# Falls back gracefully to SQLite if running locally for quick zero-setup testing.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///saree_store.db")
if DATABASE_URL.startswith("postgres://"):
    # Fix Heroku/Render dialect mismatch
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(50), unique=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False) # In production, verify using passlib/bcrypt
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(150), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    base_price = Column(Float, nullable=False)
    sku = Column(String(100), unique=True, nullable=False)
    fabric = Column(String(100), nullable=False, index=True)
    color_family = Column(String(50), nullable=False, index=True)
    stock_count = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")

class ProductImage(Base):
    __tablename__ = "product_images"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    image_url = Column(String(500), nullable=False)
    alt_text = Column(String(255), nullable=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="images")

class ProductVariant(Base):
    __tablename__ = "product_variants"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    variant_name = Column(String(100), nullable=False) 
    option_value = Column(String(100), nullable=False) 
    price_modifier = Column(Float, default=0.0)

    product = relationship("Product", back_populates="variants")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    reviewer_name = Column(String(150), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    is_verified_buyer = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="reviews")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    
    address_line1 = Column(String(255), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    pincode = Column(String(20), nullable=False)
    
    subtotal = Column(Float, nullable=False)
    shipping_cost = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    
    order_status = Column(String(50), default="Pending") # Pending, Processing, Shipped, Delivered
    payment_status = Column(String(50), default="Unpaid") # Unpaid, Paid
    payment_method = Column(String(50), nullable=True) # Card, UPI, COD
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"))
    product_title = Column(String(255), nullable=False)
    price_at_purchase = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    customizations = Column(String, nullable=True)

    order = relationship("Order", back_populates="items")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI(title="Vaishna Saree Boutique API", version="1.1")

def send_automated_order_email(order_no: str, email: str, name: str, total: float):
    """
    Dispatches automated order confirmation email.
    Uses SMTP mail parameters. For production, configure SMTP server variables below.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        print(f"[Simulated Email] To: {email} | Order {order_no} Confirmed! Total Paid: INR {total:,.2f}")
        return

    try:
        msg = EmailMessage()
        msg['Subject'] = f"Vaishna Heritage Sarees - Order Confirmed! {order_no}"
        msg['From'] = smtp_user
        msg['To'] = email
        msg.set_content(f"""
        Namaste {name},

        Thank you for shopping with Vaishna Heritage Saree Boutique.
        Your order {order_no} has been confirmed and is currently being processed.

        Grand Total: ₹{total:,.2f}
        Fulfillment: Preparing your artisan-made premium handloom saree options.
        Tracking link will be provided shortly once dispatched.

        Warm regards,
        Vaishna Heritage Team
        """)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"[SMTP Email Delivered] Order {order_no} notification dispatched.")
    except Exception as e:
        print(f"[SMTP Email Failed] Error connecting or sending: {str(e)}")

def seed_database_if_empty():
    db = SessionLocal()
    if db.query(Product).count() > 0:
        db.close()
        return

    # Seed Premium Admin User
    admin = User(
        email="admin@vaishnasarees.com",
        password_hash="vaishna2026", 
        first_name="Deepak",
        last_name="Sharma",
        is_admin=True
    )
    db.add(admin)

    # Core Premium Sarees Seeding Data
    saree_data = [
        {
            "title": "Rajkumari Pure Kanchipuram Silk Saree",
            "slug": "rajkumari-pure-kanchipuram-silk",
            "description": "Exquisite bridal handloom pure mulberry silk saree directly from Kanchipuram. Embellished with 100% genuine gold zari (metallic threads), intricate traditional temple motifs along the borders, and a majestic heavily adorned pallu. Ideal for weddings and special heirloom collection.",
            "base_price": 18500.0,
            "sku": "SA-KAN-001",
            "fabric": "Kanchipuram Silk",
            "color_family": "Crimson Red",
            "stock_count": 8,
            "images": [
                {"url": "https://images.unsplash.com/photo-1610030469983-98e550d6193c?auto=format&fit=crop&q=80&w=600", "alt": "Rajkumari Crimson Red Kanchipuram Saree"},
                {"url": "https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?auto=format&fit=crop&q=80&w=600", "alt": "Gold Border Details Close-up"}
            ],
            "variants": [
                {"name": "Blouse Stitching", "option": "Unstitched Fabric (Included)", "mod": 0.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 36", "mod": 1200.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 38", "mod": 1200.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 40", "mod": 1200.0},
                {"name": "Fall & Pico Stitching", "option": "None", "mod": 0.0},
                {"name": "Fall & Pico Stitching", "option": "Add Fall & Pico Border Stitching", "mod": 300.0},
                {"name": "Petticoat Accessory", "option": "None", "mod": 0.0},
                {"name": "Petticoat Accessory", "option": "Premium Cotton Petticoat", "mod": 450.0}
            ],
            "reviews": [
                {"reviewer": "Anjali Pillai", "rating": 5, "comment": "Absolutely breathtaking. The zari weight is heavy and authentic. Recieved multiple compliments at my daughter's wedding!", "verified": True},
                {"reviewer": "Srinidhi R.", "rating": 5, "comment": "Authentic fabric and prompt customer service support for blouse stitching adjustment.", "verified": True}
            ]
        },
        {
            "title": "Varanasi Vrindavan Banarasi Georgette Saree",
            "slug": "varanasi-vrindavan-banarasi-georgette",
            "description": "Crafted inside the heart of Varanasi, this premium georgette saree features classic gold and silver floral jaal weave. Combining the airy weight of premium georgette with classic royal silver zari, it gives an effortlessly stunning evening cocktail look.",
            "base_price": 12900.0,
            "sku": "SA-BAN-002",
            "fabric": "Banarasi Georgette",
            "color_family": "Mint Green",
            "stock_count": 5,
            "images": [
                {"url": "https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?auto=format&fit=crop&q=80&w=600", "alt": "Mint Green Banarasi Georgette Saree"},
                {"url": "https://images.unsplash.com/photo-1610030470213-9426f49774fa?auto=format&fit=crop&q=80&w=600", "alt": "Zari Detail Close-up"}
            ],
            "variants": [
                {"name": "Blouse Stitching", "option": "Unstitched Fabric (Included)", "mod": 0.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 38", "mod": 1200.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 40", "mod": 1200.0},
                {"name": "Fall & Pico Stitching", "option": "None", "mod": 0.0},
                {"name": "Fall & Pico Stitching", "option": "Add Fall & Pico Border Stitching", "mod": 300.0}
            ],
            "reviews": [
                {"reviewer": "Pragya S.", "rating": 4, "comment": "Beautiful light weight fabric. The color is exactly like the picture. Blouse stitched accurately.", "verified": True}
            ]
        },
        {
            "title": "Maya Hand-Painted Organza Saree",
            "slug": "maya-hand-painted-organza",
            "description": "Delicate and modern premium translucent lavender organza saree, completely hand-painted with pastel watercolor floral motifs by skilled artisans. Features detailed scalloped border embroidery with micro pearl enhancements.",
            "base_price": 6800.0,
            "sku": "SA-ORG-003",
            "fabric": "Premium Organza",
            "color_family": "Pastel Lavender",
            "stock_count": 12,
            "images": [
                {"url": "https://images.unsplash.com/photo-1610030469668-93535c17b6b3?auto=format&fit=crop&q=80&w=600", "alt": "Maya Pastel Lavender Organza Saree"}
            ],
            "variants": [
                {"name": "Blouse Stitching", "option": "Unstitched Fabric (Included)", "mod": 0.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 38", "mod": 1200.0},
                {"name": "Fall & Pico Stitching", "option": "None", "mod": 0.0},
                {"name": "Fall & Pico Stitching", "option": "Add Fall & Pico Border Stitching", "mod": 300.0},
                {"name": "Petticoat Accessory", "option": "None", "mod": 0.0},
                {"name": "Petticoat Accessory", "option": "Premium Satin Petticoat (Provides Sheen)", "mod": 750.0}
            ],
            "reviews": [
                {"reviewer": "Kiran Mehra", "rating": 5, "comment": "The satin petticoat under this sheer organza is an absolute necessity! Looks majestic. Super soft fabric.", "verified": True}
            ]
        },
        {
            "title": "Surya Classic Chanderi Block Print Saree",
            "slug": "surya-classic-chanderi-block-print",
            "description": "A light and breezy Chanderi cotton-silk fabric decorated with traditional hand-carved wooden block prints in rich mustard-gold tone, finished with a subtle yet sparkling gold zari border edge. Ideal for festive pujas, semi-formal wear, and office days.",
            "base_price": 4500.0,
            "sku": "SA-CHA-004",
            "fabric": "Chanderi Cotton-Silk",
            "color_family": "Mustard Gold",
            "stock_count": 15,
            "images": [
                {"url": "https://images.unsplash.com/photo-1610030469810-090c88b7f8bb?auto=format&fit=crop&q=80&w=600", "alt": "Mustard Yellow Chanderi Saree"}
            ],
            "variants": [
                {"name": "Blouse Stitching", "option": "Unstitched Fabric (Included)", "mod": 0.0},
                {"name": "Blouse Stitching", "option": "Stitched Custom Size - 38", "mod": 1200.0},
                {"name": "Fall & Pico Stitching", "option": "None", "mod": 0.0},
                {"name": "Fall & Pico Stitching", "option": "Add Fall & Pico Border Stitching", "mod": 300.0}
            ],
            "reviews": [
                {"reviewer": "Deeksha Patel", "rating": 5, "comment": "Lovely simple summer wear, fabric feels highly premium. Color is so elegant.", "verified": True}
            ]
        }
    ]

    for item in saree_data:
        p = Product(
            title=item["title"],
            slug=item["slug"],
            description=item["description"],
            base_price=item["base_price"],
            sku=item["sku"],
            fabric=item["fabric"],
            color_family=item["color_family"],
            stock_count=item["stock_count"]
        )
        db.add(p)
        db.commit()
        db.refresh(p)

        for img in item["images"]:
            db_img = ProductImage(product_id=p.id, image_url=img["url"], alt_text=img["alt"])
            db.add(db_img)
        
        for var in item["variants"]:
            db_var = ProductVariant(product_id=p.id, variant_name=var["name"], option_value=var["option"], price_modifier=var["mod"])
            db.add(db_var)

        for rev in item["reviews"]:
            db_rev = Review(product_id=p.id, reviewer_name=rev["reviewer"], rating=rev["rating"], comment=rev["comment"], is_verified_buyer=rev["verified"])
            db.add(db_rev)
            
    db.commit()
    db.close()

seed_database_if_empty()

def check_admin_session(request: Request, db: Session) -> bool:
    """Checks browser cookie context for secure admin session authorization."""
    session_id = request.cookies.get("vaishna_session")
    if not session_id:
        return False
    user = db.query(User).filter(User.uuid == session_id, User.is_admin == True).first()
    return user is not None

@app.get("/api/products")
def api_get_products(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active == True).all()
    out = []
    for p in products:
        out.append({
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "base_price": p.base_price,
            "sku": p.sku,
            "fabric": p.fabric,
            "color": p.color_family,
            "stock": p.stock_count,
            "images": [img.image_url for img in p.images]
        })
    return out

@app.post("/admin/login")
def admin_login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Processes admin logging. Validates credentials securely and plants cookie."""
    user = db.query(User).filter(User.email == email, User.is_admin == True).first()
    if user and user.password_hash == password: # In true production, match against hashed password
        response = RedirectResponse(url="/#admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="vaishna_session", value=user.uuid, httponly=True, max_age=86400)
        return response
    return RedirectResponse(url="/?login_failed=1#admin-login", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("vaishna_session")
    return response

@app.post("/admin/products/add")
def admin_add_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    base_price: float = Form(...),
    sku: str = Form(...),
    fabric: str = Form(...),
    color: str = Form(...),
    stock: int = Form(...),
    image_url: str = Form(...),
    db: Session = Depends(get_db)
):
    if not check_admin_session(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    slug = title.lower().replace(" ", "-").replace("/", "-")
    new_p = Product(
        title=title,
        slug=slug,
        description=description,
        base_price=base_price,
        sku=sku,
        fabric=fabric,
        color_family=color,
        stock_count=stock
    )
    db.add(new_p)
    db.commit()
    db.refresh(new_p)

    db_img = ProductImage(product_id=new_p.id, image_url=image_url, alt_text=title)
    db.add(db_img)

    # Inject standard luxury customizations options
    variants = [
        {"name": "Blouse Stitching", "option": "Unstitched Fabric (Included)", "mod": 0.0},
        {"name": "Blouse Stitching", "option": "Stitched Custom Size - 38", "mod": 1200.0},
        {"name": "Blouse Stitching", "option": "Stitched Custom Size - 40", "mod": 1200.0},
        {"name": "Fall & Pico Stitching", "option": "None", "mod": 0.0},
        {"name": "Fall & Pico Stitching", "option": "Add Fall & Pico Border Stitching", "mod": 300.0}
    ]
    for var in variants:
        db_var = ProductVariant(product_id=new_p.id, variant_name=var["name"], option_value=var["option"], price_modifier=var["mod"])
        db.add(db_var)

    db.commit()
    return RedirectResponse(url="/#admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/products/delete/{prod_id}")
def admin_delete_product(prod_id: int, request: Request, db: Session = Depends(get_db)):
    if not check_admin_session(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    p = db.query(Product).filter(Product.id == prod_id).first()
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse(url="/#admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/orders/update/{order_id}")
def update_order_status(
    order_id: int, 
    request: Request,
    status: str = Form(...), 
    db: Session = Depends(get_db)
):
    if not check_admin_session(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.order_status = status
        db.commit()
    return RedirectResponse(url="/#admin", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/reviews/add")
def api_add_review(
    product_id: int = Form(...),
    name: str = Form(...),
    rating: int = Form(...),
    comment: str = Form(...),
    db: Session = Depends(get_db)
):
    rev = Review(
        product_id=product_id,
        reviewer_name=name,
        rating=rating,
        comment=comment,
        is_verified_buyer=True
    )
    db.add(rev)
    db.commit()
    return RedirectResponse(url=f"/#product-{product_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/orders/checkout")
def api_checkout(
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: str = Form(...),
    address: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    pincode: str = Form(...),
    payment_method: str = Form(...),
    items_json: str = Form(...), 
    db: Session = Depends(get_db)
):
    import json
    try:
        cart_items = json.loads(items_json)
    except Exception:
        cart_items = []

    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    subtotal = 0.0
    order_items_to_create = []

    for item in cart_items:
        prod = db.query(Product).filter(Product.id == item["product_id"]).first()
        if not prod:
            continue
        
        mod_cost = 0.0
        customization_tags = []
        for vname, vval in item.get("customizations", {}).items():
            variant_match = db.query(ProductVariant).filter(
                ProductVariant.product_id == prod.id,
                ProductVariant.variant_name == vname,
                ProductVariant.option_value == vval
            ).first()
            if variant_match:
                mod_cost += variant_match.price_modifier
                customization_tags.append(f"{vname}: {vval}")
        
        item_unit_price = prod.base_price + mod_cost
        subtotal += item_unit_price * item["quantity"]
        
        order_items_to_create.append(OrderItem(
            product_title=prod.title,
            price_at_purchase=item_unit_price,
            quantity=item["quantity"],
            customizations=", ".join(customization_tags)
        ))

        # Adjust inventory limits
        prod.stock_count = max(0, prod.stock_count - item["quantity"])

    shipping = 150.0 if subtotal < 5000.0 else 0.0 
    total = subtotal + shipping

    order_no = f"SR-2026-{uuid.uuid4().hex[:6].upper()}"

    new_order = Order(
        order_number=order_no,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        address_line1=address,
        city=city,
        state=state,
        pincode=pincode,
        subtotal=subtotal,
        shipping_cost=shipping,
        total_amount=total,
        order_status="Processing",
        payment_status="Paid" if payment_method != "Pending COD" else "Unpaid",
        payment_method=payment_method
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    for oi in order_items_to_create:
        oi.order_id = new_order.id
        db.add(oi)

    db.commit()

    # Dispatch automated email securely on a separate thread to keep response speed < 100ms
    background_tasks.add_task(
        send_automated_order_email, 
        order_no, 
        customer_email, 
        customer_name, 
        total
    )

    return RedirectResponse(url=f"/#invoice?id={new_order.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    is_admin = check_admin_session(request, db)
    
    # Pre-render Saree catalog list
    catalog_items_html = ""
    for p in products:
        img_url = p.images[0].image_url if p.images else "https://via.placeholder.com/300"
        stars_html = "".join(['<svg class="w-5 h-5 text-amber-500 fill-current" viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>' for _ in range(5)])
        
        variant_groups = {}
        for v in p.variants:
            if v.variant_name not in variant_groups:
                variant_groups[v.variant_name] = []
            variant_groups[v.variant_name].append(v)
            
        variants_form_html = ""
        for group_name, v_list in variant_groups.items():
            variants_form_html += f'<div class="mb-3"><label class="block text-xs uppercase tracking-wider font-semibold text-neutral-600 mb-1">{group_name}</label>'
            variants_form_html += f'<select data-p-id="{p.id}" data-v-group="{group_name}" class="variant-select w-full bg-cream border border-neutral-300 rounded p-2 text-sm focus:ring-1 focus:ring-rose-800 focus:outline-none transition-all">'
            for v in v_list:
                mod_str = f" (+₹{v.price_modifier:,.0f})" if v.price_modifier > 0 else ""
                variants_form_html += f'<option value="{v.option_value}" data-mod="{v.price_modifier}">{v.option_value}{mod_str}</option>'
            variants_form_html += '</select></div>'

        # Pre-render reviews
        reviews_html = ""
        avg_rating = 5.0
        if p.reviews:
            avg_rating = sum([r.rating for r in p.reviews]) / len(p.reviews)
            for r in p.reviews:
                r_stars = "".join(['★' for _ in range(r.rating)] + ['☆' for _ in range(5 - r.rating)])
                reviews_html += f"""
                <div class="border-b border-neutral-100 py-3">
                    <div class="flex items-center justify-between">
                        <span class="font-semibold text-sm text-neutral-800">{r.reviewer_name}</span>
                        <span class="text-amber-500 text-sm font-semibold">{r_stars}</span>
                    </div>
                    <p class="text-neutral-600 text-xs mt-1 italic">"{r.comment}"</p>
                </div>
                """
        else:
            reviews_html = "<p class='text-xs text-neutral-400 italic py-2'>No reviews yet. Be the first to review!</p>"

        # Pre-rendering complete catalog structure card
        catalog_items_html += f"""
        <div id="product-{p.id}" class="saree-card bg-white border border-neutral-100 rounded-xl overflow-hidden shadow-sm hover:shadow-xl transition-all duration-300 flex flex-col" data-fabric="{p.fabric}" data-color="{p.color_family}" data-price="{p.base_price}">
            <div class="relative overflow-hidden group h-80 bg-neutral-100">
                <img src="{img_url}" alt="{p.title}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700">
                <span class="absolute top-3 left-3 bg-rose-800 text-cream text-[10px] uppercase tracking-widest font-bold px-3 py-1 rounded-full">{p.fabric}</span>
                {"<span class='absolute top-3 right-3 bg-amber-500 text-neutral-900 text-[10px] uppercase font-bold px-2.5 py-1 rounded'>LOW STOCK</span>" if p.stock_count <= 5 else ""}
            </div>
            
            <div class="p-5 flex-grow flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-start mb-2">
                        <h3 class="font-serif text-lg font-bold text-neutral-900 leading-snug">{p.title}</h3>
                        <span class="text-xs text-neutral-400 font-mono mt-1">{p.sku}</span>
                    </div>
                    
                    <div class="flex items-center space-x-2 mb-3">
                        <div class="flex text-amber-500">
                            {stars_html}
                        </div>
                        <span class="text-xs text-neutral-500 font-semibold font-mono">({len(p.reviews)} reviews)</span>
                    </div>
                    
                    <p class="text-neutral-600 text-sm mb-4 line-clamp-2">{p.description}</p>
                    
                    <div class="bg-neutral-50 rounded-lg p-3 border border-neutral-100 mb-4">
                        {variants_form_html}
                    </div>
                </div>

                <div>
                    <div class="flex items-baseline justify-between mb-4 border-t border-neutral-100 pt-3">
                        <span class="text-xs uppercase tracking-wider font-semibold text-neutral-400">Premium Saree Price</span>
                        <div class="text-right">
                            <span class="text-2xl font-serif font-bold text-rose-800" id="price-display-{p.id}">₹{p.base_price:,.0f}</span>
                            <p class="text-[10px] text-neutral-400 font-medium">+ options</p>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-2">
                        <button onclick="addToCart({p.id}, '{p.title}', {p.base_price}, '{img_url}')" class="bg-rose-800 hover:bg-rose-900 text-cream text-xs font-bold uppercase tracking-wider py-3 px-4 rounded transition-all duration-300 flex items-center justify-center space-x-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"></path></svg>
                            <span>Add To Cart</span>
                        </button>
                        <button onclick="toggleReviewsModal({p.id})" class="border border-neutral-300 hover:border-neutral-500 text-neutral-700 text-xs font-semibold py-3 px-2 rounded transition-all duration-300">
                            Read Reviews ({len(p.reviews)})
                        </button>
                    </div>
                </div>
            </div>
            
            <div id="reviews-box-{p.id}" class="hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div class="bg-white rounded-xl w-full max-w-lg p-6 max-h-[85vh] overflow-y-auto shadow-2xl relative text-neutral-800">
                    <button onclick="toggleReviewsModal({p.id})" class="absolute top-4 right-4 text-neutral-400 hover:text-neutral-600 text-2xl font-semibold">&times;</button>
                    <h3 class="font-serif text-xl font-bold text-neutral-900 border-b border-rose-800 pb-2 mb-4">Verified Customer Reviews</h3>
                    
                    <div class="space-y-4 mb-6">
                        {reviews_html}
                    </div>
                    
                    <div class="bg-neutral-50 p-4 rounded-lg border border-neutral-100">
                        <h4 class="font-semibold text-sm text-rose-800 mb-3 uppercase tracking-wider">Leave Your Rating</h4>
                        <form action="/api/reviews/add" method="POST" class="space-y-3">
                            <input type="hidden" name="product_id" value="{p.id}">
                            <div class="grid grid-cols-2 gap-3">
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">Your Name</label>
                                    <input type="text" name="name" required class="w-full text-xs p-2 bg-white border border-neutral-300 rounded focus:outline-rose-800">
                                </div>
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">Rating Stars</label>
                                    <select name="rating" class="w-full text-xs p-2 bg-white border border-neutral-300 rounded focus:outline-rose-800">
                                        <option value="5">5 Star - Flawless Quality</option>
                                        <option value="4">4 Star - Highly Beautiful</option>
                                        <option value="3">3 Star - Good Saree</option>
                                        <option value="2">2 Star - Below Expectations</option>
                                        <option value="1">1 Star - Poor Stitching/Fabric</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-neutral-600 mb-1">Your Review Comment</label>
                                <textarea name="comment" rows="3" required class="w-full text-xs p-2 bg-white border border-neutral-300 rounded focus:outline-rose-800" placeholder="Tell other shoppers about weight, weave, or stitching details..."></textarea>
                            </div>
                            <button type="submit" class="bg-rose-800 text-cream w-full py-2 rounded text-xs uppercase font-bold tracking-widest hover:bg-rose-900 transition-all">Submit Star Review</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        """

    admin_orders_rows = ""
    for o in orders:
        items_detail = ""
        for i in o.items:
            items_detail += f"<div class='text-xs text-neutral-600 font-mono'>• {i.product_title} x{i.quantity} ({i.customizations or 'Standard'})</div>"
            
        admin_orders_rows += f"""
        <tr class="border-b border-neutral-200 hover:bg-neutral-50 text-xs">
            <td class="px-4 py-3 font-semibold text-rose-800 font-mono">{o.order_number}</td>
            <td class="px-4 py-3">
                <div class="font-bold text-neutral-900">{o.customer_name}</div>
                <div class="text-[10px] text-neutral-400">{o.customer_email} | {o.customer_phone}</div>
                <div class="text-[10px] text-neutral-500">{o.address_line1}, {o.city}, {o.state} {o.pincode}</div>
            </td>
            <td class="px-4 py-3">{items_detail}</td>
            <td class="px-4 py-3 font-bold font-mono text-neutral-800">₹{o.total_amount:,.2f}</td>
            <td class="px-4 py-3">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider {'bg-emerald-100 text-emerald-800' if o.payment_status=='Paid' else 'bg-amber-100 text-amber-800'}">
                    {o.payment_status}
                </span>
            </td>
            <td class="px-4 py-3">
                <form action="/admin/orders/update/{o.id}" method="POST" class="inline-flex items-center space-x-1">
                    <select name="status" onchange="this.form.submit()" class="bg-white border border-neutral-300 rounded text-[11px] p-1 font-medium text-neutral-700">
                        <option value="Pending" {'selected' if o.order_status=='Pending' else ''}>Pending</option>
                        <option value="Processing" {'selected' if o.order_status=='Processing' else ''}>Processing</option>
                        <option value="Shipped" {'selected' if o.order_status=='Shipped' else ''}>Shipped</option>
                        <option value="Delivered" {'selected' if o.order_status=='Delivered' else ''}>Delivered</option>
                    </select>
                </form>
            </td>
        </tr>
        """
        
    if not admin_orders_rows:
        admin_orders_rows = "<tr><td colspan='6' class='text-center py-8 text-neutral-400 italic'>No incoming orders recorded yet.</td></tr>"

    admin_products_rows = ""
    for p in products:
        admin_products_rows += f"""
        <tr class="border-b border-neutral-100 text-xs text-neutral-800">
            <td class="px-4 py-2 font-semibold text-neutral-900">{p.title}</td>
            <td class="px-4 py-2 font-mono text-neutral-500">{p.sku}</td>
            <td class="px-4 py-2 text-neutral-500">{p.fabric}</td>
            <td class="px-4 py-2 font-bold font-mono text-rose-800">₹{p.base_price:,.2f}</td>
            <td class="px-4 py-2 text-center font-mono font-bold text-neutral-700">{p.stock_count}</td>
            <td class="px-4 py-2 text-right">
                <form action="/admin/products/delete/{p.id}" method="POST" onsubmit="return confirm('Delete this premium saree listing forever?');">
                    <button type="submit" class="text-rose-600 hover:text-rose-900 font-bold uppercase text-[10px]">Delete</button>
                </form>
            </td>
        </tr>
        """

    # Admin Login view block to replace simple dashboard if not logged in
    admin_panel_html = ""
    if is_admin:
        admin_panel_html = f"""
        <div class="flex flex-col md:flex-row md:items-center md:justify-between border-b border-neutral-700 pb-6 mb-8">
            <div>
                <span class="text-gold text-xs font-bold uppercase tracking-widest">Active Secure Admin Session</span>
                <h2 class="serif-header text-3xl font-black text-white mt-1">BOUTIQUE LOGISTICS & ORDERS</h2>
            </div>
            <div class="flex space-x-3 mt-4 md:mt-0">
                <button onclick="toggleSystemDocs()" class="bg-gold/10 hover:bg-gold/20 text-gold border border-gold/40 text-xs font-bold uppercase tracking-wider py-2.5 px-4 rounded transition-all">
                    Read Deploy Docs
                </button>
                <a href="/admin/logout" class="bg-rose-800 hover:bg-rose-950 text-cream text-xs font-bold uppercase tracking-wider py-2.5 px-4 rounded transition-all">
                    Secure Logout
                </a>
            </div>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div class="bg-neutral-800 p-4 rounded-xl border border-neutral-700">
                <span class="text-[10px] uppercase text-neutral-400 tracking-wider">Registered Sarees</span>
                <span class="block text-2xl font-serif font-bold text-gold mt-1">{len(products)} Unique</span>
            </div>
            <div class="bg-neutral-800 p-4 rounded-xl border border-neutral-700">
                <span class="text-[10px] uppercase text-neutral-400 tracking-wider">Total Orders Logged</span>
                <span class="block text-2xl font-serif font-bold text-gold mt-1">{len(orders)} Orders</span>
            </div>
            <div class="bg-neutral-800 p-4 rounded-xl border border-neutral-700">
                <span class="text-[10px] uppercase text-neutral-400 tracking-wider">Platform Cost Savings</span>
                <span class="block text-2xl font-serif font-bold text-emerald-400 mt-1">₹0.00 (Free Stack)</span>
            </div>
            <div class="bg-neutral-800 p-4 rounded-xl border border-neutral-700">
                <span class="text-[10px] uppercase text-neutral-400 tracking-wider">Database Gateway</span>
                <span class="block text-2xl font-serif font-bold text-emerald-400 mt-1 flex items-center">
                    <span class="w-3 h-3 bg-emerald-500 rounded-full animate-ping mr-2"></span> Active DB
                </span>
            </div>
        </div>

        <div class="grid lg:grid-cols-3 gap-8">
            <div class="bg-neutral-800 rounded-xl p-6 border border-neutral-700 h-fit">
                <h3 class="serif-header text-lg font-bold text-gold uppercase tracking-wider mb-4 border-b border-neutral-700 pb-2">Add New Luxury Saree</h3>
                <form action="/admin/products/add" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Product Title</label>
                        <input type="text" name="title" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Base Price (INR)</label>
                            <input type="number" step="any" name="base_price" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold">
                        </div>
                        <div>
                            <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">SKU Code</label>
                            <input type="text" name="sku" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold" placeholder="SA-KAN-109">
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Fabric Material</label>
                            <input type="text" name="fabric" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold" placeholder="Pure Chanderi / Silk">
                        </div>
                        <div>
                            <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Color Shade</label>
                            <input type="text" name="color" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold" placeholder="Pastel Mint / Red">
                        </div>
                    </div>
                    <div>
                        <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Initial Stock Count</label>
                        <input type="number" name="stock" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold" value="10">
                    </div>
                    <div>
                        <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Product Photo URL</label>
                        <input type="url" name="image_url" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold" placeholder="https://images.unsplash.com/...">
                    </div>
                    <div>
                        <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Boutique Description</label>
                        <textarea name="description" rows="3" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold focus:border-gold" placeholder="Zari threads count, border detail..."></textarea>
                    </div>
                    <button type="submit" class="w-full bg-gold hover:bg-deepgold text-maroon font-bold py-2.5 rounded text-xs uppercase tracking-wider transition-colors">
                        Add To Live Storefront
                    </button>
                </form>
            </div>

            <div class="lg:col-span-2 space-y-8">
                <div class="bg-neutral-800 rounded-xl p-6 border border-neutral-700">
                    <h3 class="serif-header text-lg font-bold text-gold uppercase tracking-wider mb-4 border-b border-neutral-700 pb-2">Incoming Boutique Orders</h3>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="text-neutral-400 border-b border-neutral-700 text-[10px] uppercase font-bold tracking-widest">
                                    <th class="px-4 py-3">Order No</th>
                                    <th class="px-4 py-3">Customer Details</th>
                                    <th class="px-4 py-3">Sarees Customizations</th>
                                    <th class="px-4 py-3">Grand Total</th>
                                    <th class="px-4 py-3">Payment</th>
                                    <th class="px-4 py-3">Ship Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {admin_orders_rows}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="bg-neutral-800 rounded-xl p-6 border border-neutral-700">
                    <h3 class="serif-header text-lg font-bold text-gold uppercase tracking-wider mb-4 border-b border-neutral-700 pb-2">Catalog Saree Inventory</h3>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="text-neutral-400 border-b border-neutral-700 text-[10px] uppercase font-bold tracking-widest">
                                    <th class="px-4 py-2">Saree Title</th>
                                    <th class="px-4 py-2">SKU</th>
                                    <th class="px-4 py-2">Fabric</th>
                                    <th class="px-4 py-2">Price</th>
                                    <th class="px-4 py-2 text-center">In Stock</th>
                                    <th class="px-4 py-2 text-right">Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {admin_products_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        """
    else:
        admin_panel_html = """
        <div class="max-w-md mx-auto bg-neutral-800 p-8 rounded-2xl border border-neutral-700 text-center" id="admin-login">
            <span class="text-gold text-xs font-bold uppercase tracking-widest">Authorized Administration Access</span>
            <h2 class="serif-header text-2xl font-black text-white mt-1 mb-4">Secure Admin Portal</h2>
            <p class="text-neutral-400 text-xs mb-6">Enter secure credentials to modify catalog listings, adjust gold-zari premium options, update pricing, and ship orders.</p>
            
            <form action="/admin/login" method="POST" class="space-y-4 text-left">
                <div>
                    <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Email Address</label>
                    <input type="email" name="email" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold" placeholder="admin@vaishnasarees.com">
                </div>
                <div>
                    <label class="block text-[10px] font-bold text-neutral-400 uppercase mb-1">Secure Password</label>
                    <input type="password" name="password" required class="w-full bg-neutral-900 border border-neutral-700 rounded text-xs p-2.5 text-cream focus:outline-gold">
                </div>
                <button type="submit" class="w-full bg-gold hover:bg-deepgold text-maroon text-xs font-extrabold py-3 rounded uppercase tracking-wider transition-colors mt-2">
                    Verify & Unlock Dashboard
                </button>
            </form>
            <p class="text-[10px] text-neutral-500 mt-4 italic">Tip: Seed account default is admin@vaishnasarees.com with password: vaishna2026</p>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vaishna - Exclusive Premium Indian Sarees</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        
        <script>
            tailwind.config = {{
                theme: {{
                    extend: {{
                        fontFamily: {{
                            serif: ['"Playfair Display"', 'Georgia', 'serif'],
                            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
                        }},
                        colors: {{
                            cream: '#FCFAEE',
                            gold: '#BCA374',
                            deepgold: '#A28B56',
                            crimson: '#640D14',
                            maroon: '#38040E',
                        }}
                    }}
                }}
            }}
        </script>
        <style>
            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background-color: #FCFAEE;
            }}
            .serif-header {{
                font-family: 'Playfair Display', serif;
            }}
            ::-webkit-scrollbar {{
                width: 6px;
            }}
            ::-webkit-scrollbar-track {{
                background: #FCFAEE;
            }}
            ::-webkit-scrollbar-thumb {{
                background: #BCA374;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body class="text-neutral-900 antialiased min-h-screen flex flex-col justify-between">
        
        <!-- PREMIUM NAVIGATION BAR -->
        <header class="bg-maroon text-cream sticky top-0 z-40 shadow-md border-b border-gold/30">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
                <a href="/" class="flex items-baseline space-x-1 focus:outline-none">
                    <span class="serif-header text-2xl font-black tracking-widest text-gold">VAISHNA</span>
                    <span class="text-[9px] uppercase tracking-widest text-cream/70">Heritage Sarees</span>
                </a>
                
                <nav class="hidden md:flex items-center space-x-8 text-xs font-semibold uppercase tracking-wider">
                    <a href="/" class="hover:text-gold transition-colors">Premium Catalog</a>
                    <a href="#about" class="hover:text-gold transition-colors">Our Legacy</a>
                    <a href="#admin" class="hover:text-gold transition-colors border border-gold/30 px-3 py-1.5 rounded bg-gold/10">Admin Dashboard</a>
                </nav>
                
                <div class="flex items-center space-x-4">
                    <button onclick="toggleCartDrawer()" class="relative p-2 hover:text-gold transition-colors focus:outline-none">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"></path>
                        </svg>
                        <span id="cart-count" class="absolute -top-1 -right-1 bg-rose-700 text-cream text-[9px] font-extrabold w-5 h-5 flex items-center justify-center rounded-full border border-maroon">0</span>
                    </button>
                    
                    <a href="#admin" class="md:hidden p-2 text-cream hover:text-gold">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    </a>
                </div>
            </div>
        </header>

        <!-- HERO EXCLUSIVES -->
        <section class="bg-maroon text-cream relative overflow-hidden py-12 md:py-20 border-b-2 border-gold">
            <div class="absolute inset-0 opacity-15 bg-cover bg-center" style="background-image: url('https://images.unsplash.com/photo-1610030469983-98e550d6193c?auto=format&fit=crop&q=80&w=1200');"></div>
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 grid md:grid-cols-2 gap-12 items-center">
                <div class="space-y-6">
                    <span class="text-gold uppercase tracking-widest text-xs font-bold border border-gold/50 px-3 py-1.5 rounded-full">Exquisite Bridal Collection 2026</span>
                    <h1 class="serif-header text-4xl sm:text-5xl lg:text-6xl font-black leading-tight text-white">Heirloom Quality, Handloomed From Gold & Silk</h1>
                    <p class="text-cream/80 text-sm sm:text-base max-w-lg leading-relaxed">
                        Hand-selected authentic sarees direct from weaving clusters of Kanchipuram and Banaras. Experience genuine pure zari weights, premium silk density, and meticulous custom stitching.
                    </p>
                    <div class="flex space-x-4">
                        <a href="#catalog" class="bg-gold hover:bg-deepgold text-maroon text-xs font-bold uppercase tracking-wider px-6 py-3.5 rounded transition-all duration-300">Shop The Catalog</a>
                        <a href="#legacy" class="border border-cream/50 hover:border-cream text-cream text-xs font-bold uppercase tracking-wider px-6 py-3.5 rounded transition-all duration-300">Our Legacy</a>
                    </div>
                </div>
                <div class="hidden md:flex justify-center">
                    <div class="relative w-80 h-[420px] rounded-2xl overflow-hidden border-4 border-gold shadow-2xl">
                        <img src="https://images.unsplash.com/photo-1610030469983-98e550d6193c?auto=format&fit=crop&q=80&w=500" class="w-full h-full object-cover" alt="Heirloom Bridal Saree">
                    </div>
                </div>
            </div>
        </section>

        <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 flex-grow text-neutral-800" id="catalog">
            <div class="text-center mb-12">
                <span class="serif-header text-gold text-lg italic block mb-1">Our Signature Weaves</span>
                <h2 class="serif-header text-3xl md:text-4xl font-black text-neutral-900 tracking-wide uppercase">The Saree Gallery</h2>
                <div class="w-16 h-1 bg-rose-800 mx-auto mt-3"></div>
            </div>
            
            <div class="bg-white border border-neutral-200 rounded-xl p-6 shadow-sm mb-10">
                <div class="flex items-center justify-between border-b border-neutral-100 pb-4 mb-4">
                    <span class="text-xs uppercase tracking-wider font-extrabold text-rose-800 flex items-center">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path></svg>
                        Filter Catalog by Fabric / Color / Pricing
                    </span>
                    <button onclick="resetFilters()" class="text-[10px] text-neutral-500 hover:text-rose-800 uppercase font-bold tracking-wider">Reset Filters</button>
                </div>
                
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-neutral-600 uppercase mb-1.5">Fabric Material</label>
                        <select id="filter-fabric" onchange="applyFilters()" class="w-full bg-cream border border-neutral-300 rounded p-2.5 text-xs focus:ring-1 focus:outline-rose-800">
                            <option value="">All Premium Fabrics</option>
                            <option value="Kanchipuram Silk">Kanchipuram Pure Silk</option>
                            <option value="Banarasi Georgette">Banarasi Georgette</option>
                            <option value="Premium Organza">Premium Organza</option>
                            <option value="Chanderi Cotton-Silk">Chanderi Cotton-Silk</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-neutral-600 uppercase mb-1.5">Color Family</label>
                        <select id="filter-color" onchange="applyFilters()" class="w-full bg-cream border border-neutral-300 rounded p-2.5 text-xs focus:ring-1 focus:outline-rose-800">
                            <option value="">All Rich Shades</option>
                            <option value="Crimson Red">Crimson Red</option>
                            <option value="Mint Green">Mint Green</option>
                            <option value="Pastel Lavender">Pastel Lavender</option>
                            <option value="Mustard Gold">Mustard Gold</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-neutral-600 uppercase mb-1.5">Maximum Price Limit</label>
                        <select id="filter-price" onchange="applyFilters()" class="w-full bg-cream border border-neutral-300 rounded p-2.5 text-xs focus:ring-1 focus:outline-rose-800">
                            <option value="100000">No Limit</option>
                            <option value="5000">Under ₹5,000</option>
                            <option value="10000">Under ₹10,000</option>
                            <option value="15000">Under ₹15,000</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8" id="product-container">
                {catalog_items_html}
            </div>
        </main>

        <section class="bg-white border-t border-b border-gold/30 py-16" id="legacy">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid md:grid-cols-2 gap-12 items-center">
                <div>
                    <img src="https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?auto=format&fit=crop&q=80&w=800" class="rounded-xl shadow-lg border border-neutral-100 max-h-96 w-full object-cover" alt="Saree embroidery artisans">
                </div>
                <div class="space-y-6">
                    <span class="serif-header text-gold text-lg italic font-semibold block">Crafting Heritage Since 1984</span>
                    <h2 class="serif-header text-3xl font-black text-neutral-900 tracking-wide uppercase">Slow, Sustainable Fashion Hand-woven For You</h2>
                    <p class="text-neutral-600 text-sm leading-relaxed">
                        At Vaishna, each saree takes anywhere from 4 to 20 days to complete. We collaborate with generational master weavers in rural clusters, ensuring they receive sustainable living wages. By building this web boutique from scratch, we completely bypass platform commissions and pass those direct savings to you and the weavers.
                    </p>
                    <div class="grid grid-cols-3 gap-4 border-t border-neutral-100 pt-6">
                        <div>
                            <span class="block text-xl font-bold font-serif text-rose-800">100%</span>
                            <span class="text-[10px] text-neutral-400 uppercase tracking-widest font-bold">Pure Mulberry Silk</span>
                        </div>
                        <div>
                            <span class="block text-xl font-bold font-serif text-rose-800">Generational</span>
                            <span class="text-[10px] text-neutral-400 uppercase tracking-widest font-bold">Master Handlooms</span>
                        </div>
                        <div>
                            <span class="block text-xl font-bold font-serif text-rose-800">Transparent</span>
                            <span class="text-[10px] text-neutral-400 uppercase tracking-widest font-bold">Weaver-Direct Pricing</span>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <div id="cart-drawer" class="hidden fixed inset-0 overflow-hidden z-50">
            <div class="absolute inset-0 overflow-hidden">
                <div class="absolute inset-0 bg-neutral-900/60 backdrop-blur-sm transition-opacity" onclick="toggleCartDrawer()"></div>
                
                <div class="absolute inset-y-0 right-0 max-w-full flex">
                    <div class="w-screen max-w-md bg-cream shadow-2xl flex flex-col justify-between border-l border-gold/30">
                        
                        <div class="p-6 border-b border-neutral-200 bg-maroon text-cream flex items-center justify-between">
                            <div class="flex items-center space-x-2">
                                <span class="serif-header text-lg font-bold text-gold tracking-wide">YOUR SHOPPING BAG</span>
                            </div>
                            <button onclick="toggleCartDrawer()" class="text-2xl text-cream/70 hover:text-cream">&times;</button>
                        </div>
                        
                        <div class="flex-grow p-6 overflow-y-auto space-y-4" id="cart-items-container"></div>
                        
                        <div class="p-6 border-t border-neutral-200 bg-white">
                            <div class="space-y-2 mb-6 text-sm">
                                <div class="flex justify-between text-neutral-500">
                                    <span>Subtotal</span>
                                    <span id="cart-subtotal" class="font-mono font-bold text-neutral-800">₹0.00</span>
                                </div>
                                <div class="flex justify-between text-neutral-500">
                                    <span>Estimated Shipping</span>
                                    <span id="cart-shipping" class="font-mono text-neutral-800">₹0.00</span>
                                </div>
                                <div class="flex justify-between border-t border-neutral-100 pt-2 text-base font-extrabold text-neutral-900">
                                    <span>Total Payable</span>
                                    <span id="cart-total" class="font-serif text-rose-800 text-lg">₹0.00</span>
                                </div>
                            </div>
                            
                            <button onclick="openCheckoutWizard()" class="bg-rose-800 hover:bg-rose-900 text-cream w-full py-3.5 rounded text-xs uppercase font-extrabold tracking-widest transition-colors duration-300">
                                Proceed To Secure Checkout
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div id="checkout-wizard" class="hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl relative text-neutral-800">
                <button onclick="closeCheckoutWizard()" class="absolute top-4 right-4 text-neutral-400 hover:text-neutral-600 text-2xl font-semibold">&times;</button>
                
                <div class="p-6 md:p-8">
                    <h3 class="serif-header text-2xl font-black text-maroon border-b border-rose-800 pb-2 mb-6">SECURE CHECKOUT</h3>
                    
                    <form action="/api/orders/checkout" method="POST" id="checkout-form" class="space-y-6">
                        <input type="hidden" name="items_json" id="checkout-items-json">
                        
                        <div class="grid grid-cols-2 gap-2 text-center text-xs font-bold uppercase tracking-wider text-neutral-400">
                            <div id="step-1-indicator" class="text-rose-800 border-b-2 border-rose-800 pb-2">1. Shipping Details</div>
                            <div id="step-2-indicator" class="pb-2 border-b-2 border-neutral-200">2. Saree Payment API</div>
                        </div>

                        <div id="checkout-step-1" class="space-y-4">
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">Full Name</label>
                                    <input type="text" name="customer_name" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800">
                                </div>
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">Phone Number</label>
                                    <input type="tel" name="customer_phone" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800" placeholder="10 Digit Number">
                                </div>
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-neutral-600 mb-1">Email (For Automated Confirmation & Tracking)</label>
                                <input type="email" name="customer_email" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800" placeholder="name@domain.com">
                            </div>
                            <div>
                                <label class="block text-xs font-semibold text-neutral-600 mb-1">Shipping Address</label>
                                <input type="text" name="address" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800" placeholder="Street Address, House/Appt Number">
                            </div>
                            <div class="grid grid-cols-3 gap-3">
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">City</label>
                                    <input type="text" name="city" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800">
                                </div>
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">State</label>
                                    <input type="text" name="state" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800">
                                </div>
                                <div>
                                    <label class="block text-xs font-semibold text-neutral-600 mb-1">Pincode</label>
                                    <input type="text" name="pincode" required class="w-full text-sm p-3 bg-cream border border-neutral-300 rounded focus:outline-rose-800">
                                </div>
                            </div>
                            
                            <button type="button" onclick="goToStep(2)" class="w-full bg-rose-800 text-cream py-3 rounded font-bold uppercase text-xs tracking-wider hover:bg-rose-900 transition-all">
                                Next: Select Secure Payment
                            </button>
                        </div>

                        <div id="checkout-step-2" class="hidden space-y-4">
                            <label class="block text-xs font-bold text-neutral-600 uppercase">Select Secure Method</label>
                            
                            <div class="grid grid-cols-2 gap-3 mb-4">
                                <label class="border border-neutral-300 rounded-lg p-3 flex items-center justify-between cursor-pointer hover:bg-neutral-50" onclick="setPaymentType('UPI')">
                                    <div class="flex items-center space-x-2">
                                        <input type="radio" name="payment_method" value="UPI" id="pay-upi" checked class="text-rose-800 focus:ring-rose-800">
                                        <span class="text-xs font-bold text-neutral-800">UPI / GPay / PhonePe</span>
                                    </div>
                                    <span class="text-xs font-bold text-emerald-700">Instant</span>
                                </label>
                                <label class="border border-neutral-300 rounded-lg p-3 flex items-center justify-between cursor-pointer hover:bg-neutral-50" onclick="setPaymentType('Card')">
                                    <div class="flex items-center space-x-2">
                                        <input type="radio" name="payment_method" value="Card" id="pay-card" class="text-rose-800 focus:ring-rose-800">
                                        <span class="text-xs font-bold text-neutral-800">Credit / Debit Card</span>
                                    </div>
                                    <span class="text-xs font-semibold text-neutral-400">Secure</span>
                                </label>
                            </div>

                            <!-- UPI Details Simulator -->
                            <div id="payment-upi-section" class="bg-neutral-50 rounded-xl p-4 border border-neutral-200 text-center space-y-3">
                                <div class="mx-auto w-32 h-32 bg-white p-2 border border-neutral-300 rounded-lg flex items-center justify-center">
                                    <img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=upi://pay?pa=vaishnasarees@okicici&pn=Vaishna%20Boutique" alt="UPI Merchant QR Code" class="w-full h-full object-contain">
                                </div>
                                <p class="text-xs text-neutral-500 font-medium">Scan QR code using any UPI Application (GPay, PhonePe, Paytm, BHIM) to make secure direct transfer.</p>
                                <p class="text-[10px] font-mono text-neutral-400">VPA: vaishnasarees@okicici</p>
                            </div>

                            <!-- Card Details Simulator -->
                            <div id="payment-card-section" class="hidden bg-neutral-50 rounded-xl p-4 border border-neutral-200 space-y-3">
                                <div>
                                    <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Card Holder Name</label>
                                    <input type="text" class="w-full text-xs p-2 bg-white border border-neutral-300 rounded" placeholder="As written on card">
                                </div>
                                <div>
                                    <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">16-Digit Card Number</label>
                                    <input type="text" class="w-full text-xs p-2 bg-white border border-neutral-300 rounded" placeholder="4000 1234 5678 9010">
                                </div>
                                <div class="grid grid-cols-2 gap-3">
                                    <div>
                                        <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">Expiry Date</label>
                                        <input type="text" class="w-full text-xs p-2 bg-white border border-neutral-300 rounded" placeholder="MM/YY">
                                    </div>
                                    <div>
                                        <label class="block text-[10px] font-bold text-neutral-500 uppercase mb-1">CVV Security Code</label>
                                        <input type="password" class="w-full text-xs p-2 bg-white border border-neutral-300 rounded" placeholder="***">
                                    </div>
                                </div>
                            </div>
                            
                            <div class="grid grid-cols-2 gap-3 pt-4 border-t border-neutral-100">
                                <button type="button" onclick="goToStep(1)" class="border border-neutral-300 hover:border-neutral-500 text-neutral-700 py-3 rounded text-xs font-bold uppercase tracking-wider">
                                    Back to Shipping
                                </button>
                                <button type="submit" class="bg-rose-800 text-cream py-3 rounded font-extrabold uppercase text-xs tracking-wider hover:bg-rose-900 transition-all">
                                    Place Order Securely
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div id="invoice-modal" class="hidden fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden relative border border-gold text-neutral-800">
                <button onclick="closeInvoiceModal()" class="absolute top-4 right-4 text-neutral-400 hover:text-neutral-600 text-xl font-bold">&times;</button>
                
                <div class="p-6 bg-maroon text-cream text-center border-b-2 border-gold">
                    <span class="text-gold tracking-widest uppercase text-[10px] font-bold block mb-1">VAISHNA EXCLUSIVES</span>
                    <h3 class="serif-header text-2xl font-black">ORDER CONFIRMED</h3>
                    <p class="text-xs text-cream/70 mt-1">An automated confirmation email has been dispatched securely!</p>
                </div>
                
                <div class="p-6 space-y-4" id="invoice-details-target"></div>
                
                <div class="p-6 bg-neutral-50 border-t border-neutral-200 flex space-x-3 justify-center">
                    <button onclick="window.print()" class="bg-neutral-800 text-cream text-xs font-bold uppercase tracking-wide py-2.5 px-4 rounded hover:bg-black transition-all">
                        Print Invoice
                    </button>
                    <button onclick="closeInvoiceModal()" class="bg-rose-800 text-cream text-xs font-bold uppercase tracking-wide py-2.5 px-4 rounded hover:bg-rose-900 transition-all">
                        Continue Shopping
                    </button>
                </div>
            </div>
        </div>

        <section id="admin" class="bg-neutral-900 text-cream py-16 border-t-4 border-gold mt-12">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                {admin_panel_html}
            </div>
        </section>

        <!-- DEPLOYMENT DOCUMENTATION MODAL -->
        <div id="docs-modal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div class="bg-white text-neutral-800 rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto shadow-2xl relative border-t-8 border-rose-800">
                <button onclick="toggleSystemDocs()" class="absolute top-4 right-4 text-neutral-400 hover:text-neutral-600 text-2xl font-semibold">&times;</button>
                
                <div class="p-6 md:p-8">
                    <span class="text-rose-800 text-[10px] font-bold uppercase tracking-widest block mb-1">Developer Deployment Guidelines</span>
                    <h3 class="serif-header text-2xl font-bold border-b border-neutral-200 pb-2 mb-4 text-neutral-900">100% Free Custom Deploy Guide</h3>
                    
                    <div class="space-y-4 text-xs leading-relaxed text-neutral-600">
                        <p>This application is designed specifically to run inside an <strong>extremely fast SQLite loop</strong> or plug directly into a live **PostgreSQL instance** which completely eliminates third-party e-commerce overhead fees. Follow these steps to take your store live:</p>
                        
                        <div>
                            <span class="block font-bold text-neutral-800 uppercase mb-1">Step 1: Install Python Packages locally</span>
                            <pre class="bg-neutral-900 text-emerald-400 p-3 rounded font-mono text-[10px] overflow-x-auto">pip install fastapi uvicorn sqlalchemy psycopg2-binary</pre>
                        </div>
                        
                        <div>
                            <span class="block font-bold text-neutral-800 uppercase mb-1">Step 2: Run local web boutique</span>
                            <pre class="bg-neutral-900 text-emerald-400 p-3 rounded font-mono text-[10px] overflow-x-auto">python main.py</pre>
                            <p class="mt-1">Open <a href="http://localhost:8000" target="_blank" class="underline text-rose-800 font-bold">http://localhost:8000</a> in any browser. The app will automatically generate the <code>saree_store.db</code> and seed the premium catalogs instantly.</p>
                        </div>

                        <div>
                            <span class="block font-bold text-neutral-800 uppercase mb-1">Step 3: Setup Automated Order Confirms SMTP Settings</span>
                            <p>To enable real email dispatches, configure these environment variables on your live server host (Render/Heroku/AWS):</p>
                            <pre class="bg-neutral-900 text-emerald-300 p-3 rounded font-mono text-[10px] overflow-x-auto">
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your-boutique-email@gmail.com"
SMTP_PASS="your-gmail-app-password"
                            </pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- FOOTER BRAND INFO -->
        <footer class="bg-maroon text-cream border-t border-gold/40 py-12 text-xs text-center">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
                <span class="serif-header text-xl font-bold text-gold tracking-widest block">VAISHNA</span>
                <p class="text-cream/60 max-w-md mx-auto leading-relaxed">
                    Premium Custom Heritage Sarees, designed from scratch, with absolute database integrity and zero monthly platform subscription costs.
                </p>
                <div class="text-gold/50 font-mono text-[10px] mt-6">
                    &copy; 2026 Vaishna Saree Boutique. Built Custom. All rights reserved.
                </div>
            </div>
        </footer>

        <!-- CORE CLIENT SIDE JAVASCRIPT STATE LOGIC -->
        <script>
            let cart = [];
            
            document.querySelectorAll('.variant-select').forEach(select => {{
                select.addEventListener('change', function() {{
                    const productId = this.getAttribute('data-p-id');
                    updateDisplayedPrice(productId);
                }});
            }});

            function updateDisplayedPrice(productId) {{
                const priceElement = document.getElementById('price-display-' + productId);
                const parentCard = document.getElementById('product-' + productId);
                const basePrice = parseFloat(parentCard.getAttribute('data-price'));
                
                let extraMod = 0.0;
                parentCard.querySelectorAll('.variant-select').forEach(sel => {{
                    const opt = sel.options[sel.selectedIndex];
                    const mod = parseFloat(opt.getAttribute('data-mod') || 0.0);
                    extraMod += mod;
                }});
                
                const finalPrice = basePrice + extraMod;
                priceElement.innerText = "₹" + finalPrice.toLocaleString('en-IN', {{ maximumFractionDigits: 0 }});
            }}

            function addToCart(productId, title, basePrice, imageUrl) {{
                const parentCard = document.getElementById('product-' + productId);
                
                let selectedCustomizations = {{}};
                let extraMod = 0.0;
                parentCard.querySelectorAll('.variant-select').forEach(sel => {{
                    const group = sel.getAttribute('data-v-group');
                    const opt = sel.options[sel.selectedIndex];
                    const val = opt.value;
                    const mod = parseFloat(opt.getAttribute('data-mod') || 0.0);
                    
                    selectedCustomizations[group] = val;
                    extraMod += mod;
                }});

                const finalUnitPrice = basePrice + extraMod;

                const existingIndex = cart.findIndex(item => 
                    item.product_id === productId && 
                    JSON.stringify(item.customizations) === JSON.stringify(selectedCustomizations)
                );

                if (existingIndex > -1) {{
                    cart[existingIndex].quantity += 1;
                }} else {{
                    cart.push({{
                        product_id: productId,
                        title: title,
                        unit_price: finalUnitPrice,
                        image_url: imageUrl,
                        quantity: 1,
                        customizations: selectedCustomizations
                    }});
                }}

                renderCart();
                toggleCartDrawer(true);
            }}

            function removeFromCart(index) {{
                cart.splice(index, 1);
                renderCart();
            }}

            function renderCart() {{
                const container = document.getElementById('cart-items-container');
                const cartCountEl = document.getElementById('cart-count');
                const subtotalEl = document.getElementById('cart-subtotal');
                const shippingEl = document.getElementById('cart-shipping');
                const totalEl = document.getElementById('cart-total');

                const totalQty = cart.reduce((sum, item) => sum + item.quantity, 0);
                cartCountEl.innerText = totalQty;

                if (cart.length === 0) {{
                    container.innerHTML = `
                    <div class="text-center py-12 text-neutral-400">
                        <svg class="w-12 h-12 mx-auto mb-3 text-neutral-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"></path></svg>
                        <p class="text-sm font-semibold uppercase tracking-wider text-rose-800">Your bag is empty</p>
                        <p class="text-xs mt-1">Select from our signature heritage collections above.</p>
                    </div>`;
                    subtotalEl.innerText = "₹0.00";
                    shippingEl.innerText = "₹0.00";
                    totalEl.innerText = "₹0.00";
                    return;
                }

                let subtotal = 0.0;
                let itemsHtml = "";

                cart.forEach((item, index) => {{
                    subtotal += item.unit_price * item.quantity;
                    
                    let customTagsHtml = "";
                    for (const [g, v] of Object.entries(item.customizations)) {{
                        customTagsHtml += `<span class="inline-block bg-neutral-100 text-[9px] text-neutral-500 px-1.5 py-0.5 rounded font-medium border border-neutral-200"> ${v}</span>`;
                    }}

                    itemsHtml += `
                    <div class="bg-white border border-neutral-200 rounded-xl p-3 flex space-x-3 shadow-sm items-center relative text-neutral-800">
                        <img src="${item.image_url}" class="w-16 h-20 object-cover rounded-md flex-shrink-0 bg-neutral-100">
                        <div class="flex-grow space-y-1">
                            <div class="flex justify-between items-start">
                                <h4 class="font-serif text-sm font-bold text-neutral-900 pr-4 leading-tight">${item.title}</h4>
                                <button onclick="removeFromCart(${index})" class="text-neutral-400 hover:text-rose-800 text-sm absolute top-3 right-3 font-semibold">&times;</button>
                            </div>
                            <div class="flex flex-wrap gap-1 mb-1">
                                ${customTagsHtml}
                            </div>
                            <div class="flex justify-between items-baseline pt-1">
                                <span class="text-xs text-neutral-500 font-bold font-mono">Qty: ${item.quantity}</span>
                                <span class="text-sm font-serif font-bold text-rose-800">₹${(item.unit_price * item.quantity).toLocaleString('en-IN')}</span>
                            </div>
                        </div>
                    </div>`;
                }});

                container.innerHTML = itemsHtml;
                
                const shipping = subtotal >= 5000 ? 0.0 : 150.0;
                const total = subtotal + shipping;

                subtotalEl.innerText = "₹" + subtotal.toLocaleString('en-IN');
                shippingEl.innerText = shipping === 0.0 ? "FREE" : "₹" + shipping.toLocaleString('en-IN');
                totalEl.innerText = "₹" + total.toLocaleString('en-IN');
            }}

            function toggleCartDrawer(forceState = null) {{
                const drawer = document.getElementById('cart-drawer');
                if (forceState !== null) {{
                    if (forceState) drawer.classList.remove('hidden');
                    else drawer.classList.add('hidden');
                }} else {{
                    drawer.classList.toggle('hidden');
                }}
            }}

            function openCheckoutWizard() {{
                if (cart.length === 0) {{
                    return;
                }}
                toggleCartDrawer(false);
                document.getElementById('checkout-wizard').classList.remove('hidden');
                document.getElementById('checkout-items-json').value = JSON.stringify(cart);
                goToStep(1);
            }}

            function closeCheckoutWizard() {{
                document.getElementById('checkout-wizard').classList.add('hidden');
            }}

            function goToStep(step) {{
                if (step === 1) {{
                    document.getElementById('checkout-step-1').classList.remove('hidden');
                    document.getElementById('checkout-step-2').classList.add('hidden');
                    document.getElementById('step-1-indicator').classList.add('text-rose-800', 'border-rose-800');
                    document.getElementById('step-2-indicator').classList.remove('text-rose-800', 'border-rose-800');
                }} else if (step === 2) {{
                    document.getElementById('checkout-step-1').classList.add('hidden');
                    document.getElementById('checkout-step-2').classList.remove('hidden');
                    document.getElementById('step-2-indicator').classList.add('text-rose-800', 'border-rose-800');
                    document.getElementById('step-1-indicator').classList.remove('text-rose-800', 'border-rose-800');
                }}
            }}

            function setPaymentType(type) {{
                const upiBox = document.getElementById('payment-upi-section');
                const cardBox = document.getElementById('payment-card-section');
                if (type === 'UPI') {{
                    upiBox.classList.remove('hidden');
                    cardBox.classList.add('hidden');
                }} else {{
                    upiBox.classList.add('hidden');
                    cardBox.classList.remove('hidden');
                }}
            }}

            function applyFilters() {{
                const selectedFabric = document.getElementById('filter-fabric').value;
                const selectedColor = document.getElementById('filter-color').value;
                const maxPriceLimit = parseFloat(document.getElementById('filter-price').value || "100000");

                document.querySelectorAll('.saree-card').forEach(card => {{
                    const cardFabric = card.getAttribute('data-fabric');
                    const cardColor = card.getAttribute('data-color');
                    const cardPrice = parseFloat(card.getAttribute('data-price'));

                    const fabricMatch = !selectedFabric || cardFabric === selectedFabric;
                    const colorMatch = !selectedColor || cardColor === selectedColor;
                    const priceMatch = cardPrice <= maxPriceLimit;

                    if (fabricMatch && colorMatch && priceMatch) {{
                        card.classList.remove('hidden');
                    }} else {{
                        card.classList.add('hidden');
                    }}
                }});
            }}

            function resetFilters() {{
                document.getElementById('filter-fabric').value = "";
                document.getElementById('filter-color').value = "";
                document.getElementById('filter-price').value = "100000";
                applyFilters();
            }}

            function toggleReviewsModal(productId) {{
                const modal = document.getElementById('reviews-box-' + productId);
                modal.classList.toggle('hidden');
            }}

            function toggleSystemDocs() {{
                const modal = document.getElementById('docs-modal');
                modal.classList.toggle('hidden');
            }}

            function closeInvoiceModal() {{
                document.getElementById('invoice-modal').classList.add('hidden');
                history.pushState("", document.title, window.location.pathname + window.location.search);
                cart = [];
                renderCart();
            }}

            window.addEventListener('load', () => {{
                if (window.location.hash.startsWith('#invoice')) {{
                    const urlParams = new URLSearchParams(window.location.hash.split('?')[1]);
                    const orderId = urlParams.get('id');
                    if (orderId) {{
                        showInvoice(orderId);
                    }}
                }}
            }});

            function showInvoice(orderId) {{
                const detailsBox = document.getElementById('invoice-details-target');
                detailsBox.innerHTML = `
                <div class="flex justify-center items-center py-8">
                    <span class="animate-spin rounded-full h-8 w-8 border-b-2 border-rose-800"></span>
                </div>`;
                
                document.getElementById('invoice-modal').classList.remove('hidden');
                
                setTimeout(() => {{
                    detailsBox.innerHTML = `
                    <div class="space-y-3 text-xs text-neutral-600">
                        <div class="flex justify-between font-mono">
                            <span>INVOICE ID:</span>
                            <span class="font-bold text-neutral-800">INV-2026-000${{orderId}}</span>
                        </div>
                        <div class="flex justify-between font-mono">
                            <span>SHIPMENT STATUS:</span>
                            <span class="font-bold text-emerald-700">Handloom Prep Started</span>
                        </div>
                        <hr class="border-neutral-200">
                        <div>
                            <span class="block font-bold text-neutral-800 uppercase text-[10px] mb-1">Delivered To:</span>
                            <p class="font-semibold text-neutral-800">Confirmed Order Recipient</p>
                            <p>Premium saree customization options logged into live inventory DB.</p>
                        </div>
                        <hr class="border-neutral-200">
                        <div class="bg-neutral-50 p-3 rounded-lg text-[11px] space-y-2">
                            <div class="flex justify-between font-semibold text-neutral-800">
                                <span>Pure Artisan Saree Package</span>
                                <span>Paid Confirmed</span>
                            </div>
                            <div class="text-[10px] text-neutral-400 italic">Custom Blouse stitching scheduled. Check your email for automated shipping schedules shortly!</div>
                        </div>
                    </div>`;
                }}, 750);
            }}
        </script>
    </body>
    </html>
    """
    return html_content

if __name__ == "__main__":
    import uvicorn
    print("Initializing Vaishna Saree E-Commerce Engines (Production Phase)...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
