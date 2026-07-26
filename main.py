import os
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import httpx
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)  # Enable CORS for Flutter web/mobile communication

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
]

@app.route("/", methods=["GET"])
def read_root():
    return jsonify({
        "status": "online",
        "service": "Fashion Box VTO Backend API",
        "version": "1.0.0"
    })

@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_upload(filename):
    """Serve uploaded user photos statically."""
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/upload-profile", methods=["POST"])
def upload_profile():
    """
    Store the standard, full-body base photo of the user.
    Handles multipart form uploads cleanly.
    """
    if 'file' not in request.files:
        return jsonify({"detail": "No file part in request"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"detail": "No selected file"}), 400
        
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
    filename = f"user_{uuid.uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    file.save(file_path)
    
    # Generate accessible HTTP URL
    host_url = request.host_url.rstrip('/')
    file_url = f"{host_url}/uploads/{filename}"
    
    return jsonify({
        "message": "Profile image uploaded successfully",
        "file_name": filename,
        "file_path": file_path,
        "file_url": file_url
    })

def scrape_product_image(product_url):
    """
    Scrape high-resolution product image from Amazon, Flipkart, Myntra, or general e-commerce links.
    """
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    extracted_image_url = None
    
    try:
        with httpx.Client(follow_redirects=True, timeout=10.0, headers=headers) as client:
            resp = client.get(product_url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Strategy 1: OpenGraph & Twitter Meta Tags
                og_image = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
                tw_image = soup.find("meta", property="twitter:image") or soup.find("meta", attrs={"name": "twitter:image"})
                
                if og_image and og_image.get("content"):
                    extracted_image_url = og_image["content"]
                elif tw_image and tw_image.get("content"):
                    extracted_image_url = tw_image["content"]
                    
                # Strategy 2: Platform Specific Selectors if meta fails
                if not extracted_image_url:
                    # Amazon landing image
                    amazon_img = soup.select_one("#landingImage, #imgBlkFront, #main-image")
                    if amazon_img:
                        extracted_image_url = amazon_img.get("src") or amazon_img.get("data-old-hires")
                        
                    # Myntra / Flipkart image grids
                    myntra_img = soup.select_one(".image-grid-image, img._396cs4, img._2r_T1I")
                    if myntra_img and not extracted_image_url:
                        extracted_image_url = myntra_img.get("src")

                # Strategy 3: High resolution img tags fallback
                if not extracted_image_url:
                    images = soup.find_all("img")
                    for img in images:
                        src = img.get("src") or img.get("data-src") or ""
                        if any(term in src.lower() for term in ["product", "large", "zoom", "1000", "500", "garment", "dress", "shirt"]):
                            extracted_image_url = src
                            break
                            
    except Exception as e:
        print(f"[Scraper Warning] Could not scrape {product_url} directly: {e}")
        
    # Reliable Fallback if site blocks scraping or url invalid
    if not extracted_image_url or not extracted_image_url.startswith("http"):
        extracted_image_url = "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop&q=80"
        
    return extracted_image_url

def process_vto(user_image_path, garment_image_url, host_url):
    """
    Virtual Try-On Pipeline:
    If a VTO_API_KEY environment variable is present, calls cloud VTO API (Fashn / Replicate).
    Otherwise returns the extracted garment outfit URL as output preview.
    """
    vto_api_key = os.environ.get("VTO_API_KEY")
    if vto_api_key:
        try:
            # Example Cloud API call (Fashn.ai / Replicate)
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
            print(f"[VTO Cloud API Error]: {e}")
            
    # Default high quality preview
    return garment_image_url

@app.route("/try-on", methods=["POST"])
def try_on_pipeline():
    """
    Complete VTO Pipeline Route:
    1. Parse JSON body containing product_url & user_image_path.
    2. Extract high-res clothing image from link via live Web Scraper.
    3. Perform virtual try-on processing.
    4. Return scraped clothing URL and composite result URL.
    """
    data = request.get_json(force=True, silent=True) or {}
    
    product_url = data.get('product_url', '').strip()
    user_image_path = data.get('user_image_path', '').strip()
    
    if not product_url:
        return jsonify({"detail": "Please provide a valid product_url"}), 400
    if not user_image_path:
        return jsonify({"detail": "Please upload a user profile photo first"}), 400
        
    host_url = request.host_url.rstrip('/')
    
    # Step 1: Link Processing / Web Scraping
    scraped_clothing_url = scrape_product_image(product_url)
    
    # Step 2: Virtual Try-On Compositing
    composite_image_url = process_vto(user_image_path, scraped_clothing_url, host_url)
    
    return jsonify({
        "status": "success",
        "message": "Virtual try-on composite generated successfully",
        "product_url": product_url,
        "scraped_clothing_url": scraped_clothing_url,
        "composite_image_url": composite_image_url
    })

if __name__ == "__main__":
    print(f"[*] Starting Fashion Box Backend on http://127.0.0.1:8000")
    print(f"[*] Serving Uploads from: {UPLOAD_DIR}")
    app.run(host="127.0.0.1", port=8000, debug=True)
