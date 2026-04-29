from flask import Flask, request, jsonify, make_response
from PIL import Image
import io, requests as req

# Deactivate PIL bomb detection for large scans
Image.MAX_IMAGE_PIXELS = None

app = Flask(__name__)

CLICKUP_TOKEN = 'pk_296503090_8Z5MEPU1UOPSAJQP6I56UXTKE1P5MQHG'


def autocrop(image_bytes, bg_tolerance=20, border=15, max_size=4000):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Resize if too large to avoid memory issues
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = min(max_size / w, max_size / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

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
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92)
        return out.getvalue()

    cropped = img.crop((left, top, right, bottom))
    out = io.BytesIO()
    cropped.save(out, format="JPEG", quality=92)
    return out.getvalue()


def fetch_and_crop(url):
    resp = req.get(url, timeout=30, headers={"User-Agent": "NahkaufBot/1.0"})
    if resp.status_code != 200:
        return None, f"Download failed: {resp.status_code}"
    return autocrop(resp.content), None


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "nahkauf-autocrop"})


@app.route("/crop", methods=["GET", "POST"])
def crop():
    """
    GET /crop?url=https://...              -> cropped JPEG
    GET /crop?task_id=XXX&index=0          -> fetch from ClickUp + crop
    POST /crop  {"url": "..."}             -> cropped JPEG
    """
    if request.method == "GET":
        url = request.args.get("url", "").strip()
        task_id = request.args.get("task_id", "").strip()
        index = int(request.args.get("index", "0"))
    else:
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        task_id = data.get("task_id", "").strip()
        index = int(data.get("index", 0))

    # Option A: direct URL
    if url:
        cropped, error = fetch_and_crop(url)
        if error:
            return error, 400

    # Option B: ClickUp task_id + attachment index
    elif task_id:
        r = req.get(
            f"https://api.clickup.com/api/v2/task/{task_id}?include_subtasks=true",
            headers={"Authorization": CLICKUP_TOKEN},
            timeout=15
        )
        if r.status_code != 200:
            return f"ClickUp API failed: {r.status_code}", 400

        attachments = r.json().get("attachments", [])
        if index >= len(attachments):
            return f"No attachment at index {index} (total: {len(attachments)})", 400

        att_url = attachments[index].get("url", "")
        if not att_url:
            return "No URL in attachment", 400

        cropped, error = fetch_and_crop(att_url)
        if error:
            return error, 400

    else:
        return "No url or task_id provided", 400

    response = make_response(cropped)
    response.headers["Content-Type"] = "image/jpeg"
    response.headers["Content-Disposition"] = "inline; filename=cropped.jpg"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
