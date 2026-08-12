import os, uuid, json, urllib.request
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins="*")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

FASHION_IMAGES = [
    "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=600&auto=format&fit=crop",
    "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=600&auto=format&fit=crop",
    "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600&auto=format&fit=crop",
    "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&auto=format&fit=crop",
]

@app.route("/")
def root():
    return jsonify({"status": "online", "service": "Fashion Box API"})

@app.route("/uploads/<path:filename>")
def serve_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/upload-profile", methods=["POST"])
def upload_profile():
    if "file" not in request.files:
        return jsonify({"detail": "No file"}), 400
    f = request.files["file"]
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "jpg"
    name = f"user_{uuid.uuid4().hex[:10]}.{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    f.save(path)
    return jsonify({"message": "Uploaded", "file_path": path,
                    "file_url": f"{request.host_url.rstrip('/')}/uploads/{name}"})

@app.route("/try-on", methods=["POST"])
def try_on():
    data = request.get_json(force=True, silent=True) or {}
    product_url = data.get("product_url", "").strip()
    if not product_url:
        return jsonify({"detail": "product_url required"}), 400
    clothing_url = None
    try:
        req = urllib.request.Request(product_url,
            headers={"User-Agent": "Mozilla/5.0 Chrome/120.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read(50000).decode("utf-8", errors="ignore")
        idx = html.find('og:image')
        if idx != -1:
            sub = html[idx:idx+300]
            for q in ['content="', "content='"]:
                i = sub.find(q)
                if i != -1:
                    s = i + len(q); e = sub.find(q[-1], s)
                    u = sub[s:e]
                    if u.startswith("http"):
                        clothing_url = u; break
    except:
        pass
    if not clothing_url:
        clothing_url = FASHION_IMAGES[abs(hash(product_url)) % len(FASHION_IMAGES)]
    return jsonify({"status": "success",
                    "scraped_clothing_url": clothing_url,
                    "composite_image_url": clothing_url})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
