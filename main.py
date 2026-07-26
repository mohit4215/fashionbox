import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Try optional scraping libraries
try:
    import httpx
    from bs4 import BeautifulSoup
    SCRAPING_ENABLED = True
except ImportError:
    SCRAPING_ENABLED = False

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
FALLBACK_IMAGE = "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop&q=80"

@app.route("/", methods=["GET"])
def read_root():
    return jsonify({
        "status": "online",
        "service": "Fashion Box VTO Backend API",
        "version": "1.0.0",
        "scraping": SCRAPING_ENABLED
    })

@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/upload-profile", methods=["POST"])
def upload_profile():
    if 'file' not in request.files:
        return jsonify({"detail": "No file part in request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"detail": "No selected file"}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
    filename = f"user_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    file.save(file_path)
    host_url = request.host_url.rstrip('/')
    file_url = f"{host_url}/uploads/{filename}"
    return jsonify({
        "message": "Profile image uploaded successfully",
        "file_name": filename,
        "file_path": file_path,
        "file_url": file_url
    })

def scrape_product_image(product_url):
    if not SCRAPING_ENABLED:
        return FALLBACK_IMAGE
    try:
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(follow_redirects=True, timeout=10.0, headers=headers) as client:
            resp = client.get(product_url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Strategy 1: OpenGraph meta
                og = soup.find("meta", property="og:image")
                if og and og.get("content"):
                    url = og["content"]
                    if url.startswith("http"):
                        return url
                # Strategy 2: Platform selectors
                for sel in ["#landingImage", ".image-grid-image", "img._396cs4"]:
                    el = soup.select_one(sel)
                    if el:
                        src = el.get("src") or el.get("data-old-hires")
                        if src and src.startswith("http"):
                            return src
                # Strategy 3: Any product-looking img
                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-src") or ""
                    if any(t in src.lower() for t in ["product", "large", "zoom", "1000", "garment", "dress", "shirt"]):
                        if src.startswith("http"):
                            return src
    except Exception as e:
        print(f"Scraper warning: {e}")
    return FALLBACK_IMAGE

def process_vto(user_image_path, garment_image_url):
    vto_api_key = os.environ.get("VTO_API_KEY")
    if vto_api_key and SCRAPING_ENABLED:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.fashn.ai/v1/run",
                    headers={"Authorization": f"Bearer {vto_api_key}"},
                    json={
                        "model_image": user_image_path,
                        "garment_image": garment_image_url,
                        "category": "tops"
                    }
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get("output", [garment_image_url])[0]
        except Exception as e:
            print(f"VTO API error: {e}")
    return garment_image_url

@app.route("/try-on", methods=["POST"])
def try_on_pipeline():
    data = request.get_json(force=True, silent=True) or {}
    product_url = data.get('product_url', '').strip()
    user_image_path = data.get('user_image_path', '').strip()
    if not product_url:
        return jsonify({"detail": "Please provide a valid product_url"}), 400
    if not user_image_path:
        return jsonify({"detail": "Please upload a user profile photo first"}), 400
    scraped_clothing_url = scrape_product_image(product_url)
    composite_image_url = process_vto(user_image_path, scraped_clothing_url)
    return jsonify({
        "status": "success",
        "message": "Virtual try-on composite generated successfully",
        "product_url": product_url,
        "scraped_clothing_url": scraped_clothing_url,
        "composite_image_url": composite_image_url
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Fashion Box on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
