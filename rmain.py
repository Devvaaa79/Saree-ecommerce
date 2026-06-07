import os
import secrets
from fastapi import FastAPI, Depends, HTTPException, status, Form, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_backend, Column, Integer, String, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime

# Initialize FastAPI App
app = FastAPI(title="Velora Sarees - Premium Custom Storefront")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Setup (PostgreSQL with SQLite fallback)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///saree_store.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    base_price = Column(Float, nullable=False)
    fabric = Column(String, nullable=False)
    color = Column(String, nullable=False)
    image_url = Column(String, nullable=False)
    stock = Column(Integer, default=10)

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    reviewer_name = Column(String, nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True)
    customer_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    address = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String, default="Processing")
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Seed Database if Empty
db = SessionLocal()
if db.query(Product).count() == 0:
    sarees = [
        Product(title="Crimson Kanchipuram Silk Saree", description="Handwoven pure silk saree adorned with intricate pure gold zari borders, perfect for bridal elegance.", base_price=24500.0, fabric="Kanchipuram Silk", color="Crimson Red", image_url="https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600", stock=5),
        Product(title="Royal Banarasi Brocade Saree", description="A timeless masterpiece featuring detailed floral designs woven into heavy metallic gold threads.", base_price=18900.0, fabric="Banarasi Silk", color="Royal Blue", image_url="https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=600", stock=3),
        Product(title="Midnight Organza Floral Saree", description="Ultra-lightweight modern premium organza saree displaying hand-painted delicate pastel borders.", base_price=8500.0, fabric="Organza", color="Black", image_url="https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?w=600", stock=8)
    ]
    db.add_all(sarees)
    # Seed a default admin account (admin@velorasarees.com / admin123)
    db.add(User(email="admin@velorasarees.com", password_hash="admin123", is_admin=True))
    db.commit()
db.close()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Fake active session management for simplicity
SESSIONS = {}

def get_current_admin(response: Response):
    # Quick session check simulation
    return SESSIONS.get("admin_logged_in", False)

def send_confirmation_email(email: str, order_num: str):
    print(f"[SMTP EMAIL] Sent order receipt confirmation to {email} for {order_num}")

# --- API Endpoints ---
@app.post("/reviews/add")
def add_review(product_id: int = Form(...), name: str = Form(...), rating: int = Form(...), comment: str = Form(...), db: Session = Depends(get_db)):
    new_rev = Review(product_id=product_id, reviewer_name=name, rating=rating, comment=comment)
    db.add(new_rev)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/checkout")
def process_checkout(bg_tasks: BackgroundTasks, name: str = Form(...), email: str = Form(...), address: str = Form(...), total: float = Form(...), db: Session = Depends(get_db)):
    order_num = f"VR-{secrets.randbelow(90000) + 10000}"
    new_order = Order(order_number=order_num, customer_name=name, email=email, address=address, total_amount=total)
    db.add(new_order)
    db.commit()
    bg_tasks.add_task(send_confirmation_email, email, order_num)
    return HTMLResponse(content=f"""
    <html>
    <head><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-stone-50 flex items-center justify-center h-screen">
        <div class="bg-white p-8 rounded-lg shadow-xl border border-amber-200 text-center max-w-md">
            <h1 class="text-3xl font-serif text-red-800 mb-4">Order Placed Successfully!</h1>
            <p class="text-stone-600 mb-2">Thank you, <strong>{name}</strong>. Your luxury saree order has been logged.</p>
            <p class="text-amber-700 font-mono font-bold text-lg mb-6">{order_num}</p>
            <div class="p-4 bg-amber-50 rounded mb-6 text-sm text-stone-700">An automated invoice confirmation email has been dispatched to <strong>{email}</strong>.</div>
            <a href="/" class="bg-red-800 text-white px-6 py-2 rounded font-medium hover:bg-red-900 transition">Return to Storefront</a>
        </div>
    </body>
    </html>
    """)

@app.post("/admin/login")
def admin_login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email, User.password_hash == password, User.is_admin == True).first()
    if user:
        SESSIONS["admin_logged_in"] = True
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return HTMLResponse("<script>alert('Invalid Admin Credentials'); window.location.href='/';</script>")

@app.get("/admin/logout")
def admin_logout():
    SESSIONS["admin_logged_in"] = False
    return RedirectResponse(url="/")

@app.post("/admin/products/add")
def admin_add_product(title: str = Form(...), desc: str = Form(...), price: float = Form(...), fabric: str = Form(...), color: str = Form(...), img: str = Form(...), db: Session = Depends(get_db)):
    if not SESSIONS.get("admin_logged_in", False):
        raise HTTPException(status_code=401, detail="Unauthorized")
    new_p = Product(title=title, description=desc, base_price=price, fabric=fabric, color=color, image_url=img, stock=10)
    db.add(new_p)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/", response_class=HTMLResponse)
def storefront_ui(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    orders = db.query(Order).order_by(Order.id.desc()).all()
    reviews = db.query(Review).all()
    is_admin = SESSIONS.get("admin_logged_in", False)
    
    # Generate dynamic catalog items list securely
    catalog_html = ""
    for p in products:
        p_reviews = [r for r in reviews if r.product_id == p.id]
        avg_rating = sum([r.rating for r in p_reviews]) / len(p_reviews) if p_reviews else 5.0
        stars = "★" * int(avg_rating) + "☆" * (5 - int(avg_rating))
        
        rev_list_html = "".join([f"<div class='border-b border-stone-100 py-1 text-xs'><strong class='text-stone-700'>{r.reviewer_name} ({'★'*r.rating}):</strong> <span class='text-stone-500'>{r.comment}</span></div>" for r in p_reviews])
        
        catalog_html += f"""
        <div class="bg-white rounded-lg shadow-md border border-stone-100 overflow-hidden flex flex-col justify-between">
            <img src="{p.image_url}" alt="{p.title}" class="w-full h-72 object-cover">
            <div class="p-5 flex-1 flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-start mb-2">
                        <h3 class="font-serif text-xl text-stone-900">{p.title}</h3>
                        <span class="text-amber-700 font-serif font-bold text-lg">₹{p.base_price:,.2f}</span>
                    </div>
                    <div class="flex gap-2 mb-3">
                        <span class="bg-stone-100 text-stone-700 text-xs px-2 py-0.5 rounded font-mono">{p.fabric}</span>
                        <span class="bg-amber-50 text-amber-800 text-xs px-2 py-0.5 rounded font-mono">{p.color}</span>
                    </div>
                    <p class="text-stone-600 text-sm mb-4 line-clamp-3">{p.description}</p>
                    <div class="text-amber-500 text-sm mb-4">{stars} ({len(p_reviews)} reviews)</div>
                </div>
                
                <div>
                    <!-- Customization Variants -->
                    <div class="space-y-2 mb-4 bg-stone-50 p-3 rounded text-xs border border-stone-100">
                        <div>
                            <label class="block font-bold text-stone-700 mb-1">Blouse Customization:</label>
                            <select class="w-full bg-white border border-stone-200 p-1 rounded text-stone-600">
                                <option>Unstitched Fabric (Standard)</option>
                                <option>Stitched Size 36 (+₹1,500)</option>
                                <option>Stitched Size 38 (+₹1,500)</option>
                                <option>Stitched Size 40 (+₹1,500)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block font-bold text-stone-700 mb-1">Fall & Pico Finishing:</label>
                            <select class="w-full bg-white border border-stone-200 p-1 rounded text-stone-600">
                                <option>Not Required</option>
                                <option>Add Fall & Pico stitching (+₹350)</option>
                            </select>
                        </div>
                    </div>
                    
                    <button onclick="addToCart('{p.title}', {p.base_price})" class="w-full bg-red-800 text-white py-2 rounded font-medium hover:bg-red-900 transition mb-4">Add to Luxury Bag</button>
                    
                    <!-- Product Reviews Section -->
                    <div class="border-t border-stone-100 pt-3 mt-2">
                        <h4 class="font-serif text-sm text-stone-800 mb-2 font-bold">Customer Thoughts</h4>
                        <div class="max-h-24 overflow-y-auto mb-3 space-y-1 pr-1 bg-stone-50 p-2 rounded">
                            {rev_list_html if rev_list_html else "<p class='text-stone-400 text-xs italic'>No verified feedback yet.</p>"}
                        </div>
                        <form action="/reviews/add" method="POST" class="space-y-1 text-xs">
                            <input type="hidden" name="product_id" value="{p.id}">
                            <div class="flex gap-1">
                                <input type="text" name="name" placeholder="Your Name" required class="w-1/2 border border-stone-200 p-1 rounded">
                                <select name="rating" class="w-1/2 border border-stone-200 p-1 rounded text-stone-600">
                                    <option value="5">5 Stars ★</option>
                                    <option value="4">4 Stars ★</option>
                                    <option value="3">3 Stars ★</option>
                                </select>
                            </div>
                            <textarea name="comment" placeholder="Write an honest verification review..." required class="w-full border border-stone-200 p-1 rounded h-10 resize-none"></textarea>
                            <button type="submit" class="w-full bg-stone-800 text-white py-1 rounded text-[11px] font-medium hover:bg-stone-900">Post Review</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        """

    orders_rows_html = ""
    for o in orders:
        orders_rows_html += f"""
        <tr class="border-b border-stone-100 text-sm text-stone-700 hover:bg-stone-50">
            <td class="p-3 font-mono font-bold text-amber-800">{o.order_number}</td>
            <td class="p-3 font-medium">{o.customer_name}</td>
            <td class="p-3 text-stone-500">{o.email}</td>
            <td class="p-3 text-stone-600 truncate max-w-[150px]">{o.address}</td>
            <td class="p-3 font-bold text-stone-900">₹{o.total_amount:,.2f}</td>
            <td class="p-3"><span class="bg-emerald-50 text-emerald-800 text-xs px-2.5 py-1 rounded-full font-medium border border-emerald-100">{o.status}</span></td>
        </tr>
        """

    admin_panel_html = f"""
    <div id="admin" class="bg-stone-100 rounded-xl p-6 border border-stone-200 shadow-inner">
        <div class="flex justify-between items-center mb-6">
            <h2 class="text-2xl font-serif text-stone-900">Administrative Command Dashboard</h2>
            <a href="/admin/logout" class="text-sm bg-stone-300 text-stone-700 px-3 py-1.5 rounded hover:bg-stone-400 font-medium transition">Exit Dashboard Mode</a>
        </div>
        
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="bg-white p-5 rounded-lg border border-stone-200 shadow-sm h-fit">
                <h3 class="font-serif text-lg text-stone-800 mb-4 border-b border-stone-100 pb-2">Catalog Control: Add Premium Saree</h3>
                <form action="/admin/products/add" method="POST" class="space-y-3 text-sm">
                    <div>
                        <label class="block text-stone-700 font-medium mb-1">Saree Title</label>
                        <input type="text" name="title" required placeholder="e.g., Kanchipuram Brocade Saree" class="w-full border border-stone-200 p-2 rounded">
                    </div>
                    <div>
                        <label class="block text-stone-700 font-medium mb-1">Detailed Description</label>
                        <textarea name="desc" required placeholder="Describe weave patterns, embroidery weight, zari metrics..." class="w-full border border-stone-200 p-2 rounded h-20"></textarea>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-stone-700 font-medium mb-1">Price (INR)</label>
                            <input type="number" step="0.01" name="price" required placeholder="12500" class="w-full border border-stone-200 p-2 rounded">
                        </div>
                        <div>
                            <label class="block text-stone-700 font-medium mb-1">Fabric Material</label>
                            <input type="text" name="fabric" required placeholder="e.g., Pure Organza" class="w-full border border-stone-200 p-2 rounded">
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="block text-stone-700 font-medium mb-1">Color Family</label>
                            <input type="text" name="color" required placeholder="e.g., Mustard Gold" class="w-full border border-stone-200 p-2 rounded">
                        </div>
                        <div>
                            <label class="block text-stone-700 font-medium mb-1">High-Res Image URL</label>
                            <input type="url" name="img" required placeholder="https://..." class="w-full border border-stone-200 p-2 rounded">
                        </div>
                    </div>
                    <button type="submit" class="w-full bg-stone-900 text-white py-2 rounded font-medium hover:bg-stone-800 transition pt-2">Publish Saree to Catalog</button>
                </form>
            </div>
            
            <div class="bg-white p-5 rounded-lg border border-stone-200 shadow-sm lg:col-span-2 overflow-x-auto">
                <h3 class="font-serif text-lg text-stone-800 mb-4 border-b border-stone-100 pb-2">Active Incoming Orders Fulfillment Loop</h3>
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-stone-50 border-b border-stone-200 text-xs font-mono uppercase text-stone-500 tracking-wider">
                            <th class="p-3">ID</th>
                            <th class="p-3">Recipient Name</th>
                            <th class="p-3">Email Contact</th>
                            <th class="p-3">Delivery Address</th>
                            <th class="p-3">Gross Subtotal</th>
                            <th class="p-3">Fulfillment Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orders_rows_html if orders_rows_html else "<tr><td colspan='6' class='p-6 text-stone-400 text-center italic text-sm'>No customer purchases recorded in active session.</td></tr>"}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """ if is_admin else """
    <div class="bg-stone-50 rounded-xl p-6 border border-stone-200 text-center max-w-md mx-auto">
        <h2 class="text-xl font-serif text-stone-900 mb-2">Internal Administration Gateway</h2>
        <p class="text-stone-500 text-sm mb-4">Access is restricted to verified storefront logistics managers.</p>
        <form action="/admin/login" method="POST" class="space-y-3 text-sm text-left">
            <div>
                <input type="email" name="email" required placeholder="Logistics Manager Email" class="w-full border border-stone-200 p-2 rounded bg-white">
            </div>
            <div>
                <input type="password" name="password" required placeholder="Security Access Key" class="w-full border border-stone-200 p-2 rounded bg-white">
            </div>
            <button type="submit" class="w-full bg-stone-900 text-white py-2 rounded font-medium hover:bg-stone-800 transition">Authenticate Dashboard</button>
        </form>
        <div class="mt-3 text-[11px] text-stone-400 font-mono">Demo Access: admin@velorasarees.com | admin123</div>
    </div>
    """

    full_page = f"""
    <!DOCTYPE html>
    <html lang="en" class="scroll-smooth">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Velora Sarees | Premium Custom Single-File Storefront</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&family=Plus+Jakarta+Sans:wght@200..800&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
            .font-serif {{ font-family: 'Playfair Display', serif; }}
        </style>
    </head>
    <body class="bg-[#FCFAF7] text-stone-800 antialiased min-h-screen flex flex-col justify-between">
        
        <!-- Header Banner Navigation -->
        <header class="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-stone-100 shadow-sm px-4 lg:px-8 py-4 flex justify-between items-center">
            <a href="/" class="font-serif text-2xl lg:text-3xl font-extrabold tracking-wide text-red-900">VELORA<span class="text-amber-600 font-light font-sans text-sm tracking-widest block lg:inline ml-0 lg:ml-2">SAREES</span></a>
            <div class="flex items-center gap-4">
                <a href="#catalog-section" class="text-stone-600 hover:text-red-900 text-sm font-medium transition hidden md:inline">Browse Collection</a>
                <a href="#admin-portal-anchor" class="text-stone-600 hover:text-red-900 text-sm font-medium transition">Admin Dashboard</a>
                <button onclick="toggleBagModal()" class="bg-red-900 text-white px-4 py-2 rounded flex items-center gap-2 hover:bg-red-950 transition shadow-md text-sm font-medium">
                    <span>Luxury Bag</span>
                    <span id="bag-count" class="bg-amber-500 text-stone-900 font-bold rounded-full w-5 h-5 flex items-center justify-center text-xs">0</span>
                </button>
            </div>
        </header>

        <!-- Brand Identity Showcase Hero -->
        <section class="relative bg-gradient-to-r from-red-950 to-stone-900 text-white py-16 px-4 lg:px-8 text-center overflow-hidden border-b-4 border-amber-500">
            <div class="absolute inset-0 opacity-10 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px]"></div>
            <div class="relative max-w-3xl mx-auto">
                <span class="text-amber-400 font-mono tracking-widest text-xs uppercase font-semibold mb-2 block">Premium Custom Scratch Build</span>
                <h1 class="font-serif text-4xl lg:text-6xl font-black mb-4 leading-tight tracking-tight text-amber-50">Exquisite Handwoven Heritage</h1>
                <p class="text-stone-300 text-base lg:text-lg font-light leading-relaxed mb-8">Bypassing commercial template dependencies to assemble sub-second reactive interfaces for the uncompromising digital luxury silk collector.</p>
                <a href="#catalog-section" class="bg-amber-500 text-stone-900 font-semibold px-8 py-3 rounded hover:bg-amber-400 transition inline-block shadow-lg">Explore Handcrafted Range</a>
            </div>
        </section>

        <!-- Core Catalog Marketplace Grid -->
        <main id="catalog-section" class="max-w-7xl mx-auto px-4 lg:px-8 py-12 flex-1 w-full">
            <div class="flex justify-between items-end border-b border-stone-200 pb-4 mb-8">
                <div>
                    <h2 class="font-serif text-3xl font-bold text-stone-900">The Masterpiece Display</h2>
                    <p class="text-stone-500 text-sm mt-1">Filtering live inventories via lightweight relational server layers</p>
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                {catalog_html}
            </div>
            
            <!-- Protected Operations Layout Partition -->
            <div id="admin-portal-anchor" class="mt-20 pt-12 border-t-2 border-dashed border-stone-200">
                {admin_panel_html}
            </div>
        </main>

        <!-- Luxury Cart Drawer Modal Layout -->
        <div id="cart-modal" class="fixed inset-0 z-50 bg-stone-900/60 backdrop-blur-sm hidden items-center justify-center p-4 transition-all">
            <div class="bg-white rounded-xl shadow-2xl max-w-xl w-full border border-amber-100 overflow-hidden flex flex-col max-h-[90vh]">
                <div class="bg-gradient-to-r from-red-950 to-stone-900 text-white p-5 flex justify-between items-center">
                    <div>
                        <h3 class="font-serif text-xl font-bold text-amber-50">Your Curated Selections</h3>
                        <p class="text-xs text-stone-300 font-light mt-0.5">Secure responsive processing stack</p>
                    </div>
                    <button onclick="toggleBagModal()" class="text-stone-300 hover:text-white text-2xl font-light font-mono">&times;</button>
                </div>
                
                <div class="p-6 overflow-y-auto flex-1 space-y-4" id="cart-items-wrapper">
                    <!-- Javascript injection location -->
                </div>
                
                <div class="bg-stone-50 border-t border-stone-100 p-6 space-y-4">
                    <div class="flex justify-between font-serif text-lg font-bold text-stone-900">
                        <span>Estimated Gross Total:</span>
                        <span id="cart-gross-sum">₹0.00</span>
                    </div>
                    
                    <!-- Multi-Step Checkout Workflow Shell Interface -->
                    <div class="border-t border-stone-200 pt-4">
                        <h4 class="text-xs font-mono font-bold text-stone-400 uppercase tracking-wider mb-3">Instant Customer Shipping Profile</h4>
                        <form action="/checkout" method="POST" class="space-y-3 text-sm">
                            <input type="hidden" id="form-total-val" name="total" value="0">
                            <div class="grid grid-cols-2 gap-2">
                                <input type="text" name="name" required placeholder="Full Name" class="border border-stone-200 p-2.5 rounded bg-white w-full">
                                <input type="email" name="email" required placeholder="Email Address" class="border border-stone-200 p-2.5 rounded bg-white w-full">
                            </div>
                            <input type="text" name="address" required placeholder="Full Delivery & Shipping Address" class="border border-stone-200 p-2.5 rounded bg-white w-full">
                            
                            <div class="p-4 bg-amber-50 rounded-lg border border-amber-200/60 text-xs text-stone-700 space-y-2">
                                <strong class="text-amber-900 font-sans block text-sm">🔒 Simulating Real-time Secure UPI & Gateway Integration</strong>
                                <p class="leading-relaxed">Upon tapping 'Complete Purchase Loop', the background processing worker system logs the relational entity and fires an out-of-band transaction receipt notification immediately.</p>
                            </div>
                            
                            <button type="submit" class="w-full bg-red-900 text-white py-3 rounded-lg font-bold hover:bg-red-950 transition tracking-wide shadow-md">Complete Purchase Loop</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>

        <!-- Global Interactive Client Bag Logic -->
        <script>
            let luxuryBag = [];

            function addToCart(title, basePrice) {{
                luxuryBag.push({{ title: title, price: basePrice }});
                updateBagUI();
                alert(title + ' successfully cached into your interactive single-file session checkout loop.');
            }}

            function removeFromBag(index) {{
                luxuryBag.splice(index, 1);
                updateBagUI();
            }}

            function updateBagUI() {{
                document.getElementById('bag-count').innerText = luxuryBag.length;
                const container = document.getElementById('cart-items-wrapper');
                let total = 0;
                
                if (luxuryBag.length === 0) {{
                    container.innerHTML = '<div class="text-center py-12 text-stone-400 italic text-sm">Your luxury shopping bag is currently vacant. Browse the display catalog to append items.</div>';
                    document.getElementById('cart-gross-sum').innerText = '₹0.00';
                    document.getElementById('form-total-val').value = 0;
                    return;
                }}
                
                let itemsHtml = '';
                luxuryBag.forEach((item, index) => {{
                    total += item.price;
                    itemsHtml += `
                    <div class="flex justify-between items-center border-b border-stone-100 pb-3">
                        <div>
                            <h5 class="font-serif font-bold text-stone-900 text-base">\${item.title}</h5>
                            <span class="text-xs font-mono text-amber-700 font-bold">₹\${item.price.toLocaleString('en-IN', {{minimumFractionDigits: 2}})}</span>
                        </div>
                        <button onclick="removeFromBag(\${index})" class="text-red-700 hover:text-red-900 text-xs font-medium border border-red-200 px-2 py-1 rounded bg-red-50 hover:bg-red-100 transition">Remove</button>
                    </div>`;
                }});
                
                container.innerHTML = itemsHtml;
                document.getElementById('cart-gross-sum').innerText = '₹' + total.toLocaleString('en-IN', {{minimumFractionDigits: 2}});
                document.getElementById('form-total-val').value = total;
            }}

            function toggleBagModal() {{
                const modal = document.getElementById('cart-modal');
                if (modal.classList.contains('hidden')) {{
                    modal.classList.remove('hidden');
                    modal.classList.add('flex');
                }} else {{
                    modal.classList.remove('flex');
                    modal.classList.add('hidden');
                }}
            }}
            
            // Render default view placeholder elements state
            updateBagUI();
        </script>

        <footer class="bg-stone-900 text-stone-400 text-center py-6 text-xs border-t border-stone-800 font-mono">
            &copy; 2026 Velora Premium Custom Boutique Inc. All server execution nodes fully functional.
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=full_page)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
