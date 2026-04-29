from flask import Flask, request, jsonify
from PIL import Image
import io, base64, requests as req

app = Flask(__name__)

def autocrop(image_bytes, bg_tolerance=20, border=15):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pixels = img.load()
    w, h = img.size

    def is_bg(r, g, b):
        return r > 255 - bg_tolerance and g > 255 - bg_tolerance and b > 255 - bg_tolerance

    top = 0
    for y in range(h):
        if any(not is_bg(*pixels[x, y]) for x in range(0, w, 3)):
            top = max(0, y - border)
            break

    bottom = h
    for y in range(h - 1, -1, -1):
        if any(not is_bg(*pixels[x, y]) for x in range(0, w, 3)):
            bottom = min(h, y + border + 1)
            break

    left = 0
    for x in range(w):
        if any(not is_bg(*pixels[x, y]) for y in range(0, h, 3)):
            left = max(0, x - border)
            break

    right = w
    for x in range(w - 1, -1, -1):
        if any(not is_bg(*pixels[x, y]) for y in range(0, h, 3)):
            right = min(w, x + border + 1)
            break

    if left >= right or top >= bottom:
        return image_bytes

    cropped = img.crop((left, top, right, bottom))
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=95)
    return out.getvalue()


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "nahkauf-autocrop"})


@app.route("/crop", methods=["POST"])
def crop():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    resp = req.get(url, timeout=30, headers={"User-Agent": "NahkaufBot/1.0"})
    if resp.status_code != 200:
        return jsonify({"error": f"Download failed: {resp.status_code}"}), 400

    cropped = autocrop(resp.content)
    return jsonify({
        "data": base64.b64encode(cropped).decode(),
        "content_type": "image/jpeg",
        "size": len(cropped)
    })

@app.route("/crop-binary", methods=["GET"])
def crop_binary():
    """
    GET /crop-binary?url=https://...
    Gibt gecroptes JPEG direkt als Binary zurück.
    Make.com http:ActionGetFile kann das direkt als Datei nutzen.
    """
    url = request.args.get("url", "").strip()
    if not url:
        return "No URL provided", 400

    resp = req.get(url, timeout=30, headers={"User-Agent": "NahkaufBot/1.0"})
    if resp.status_code != 200:
        return f"Download failed: {resp.status_code}", 400

    cropped = autocrop(resp.content)
    return cropped, 200, {
        "Content-Type": "image/jpeg",
        "Content-Disposition": "inline; filename=cropped.jpg"
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
