# ============================================================
# OddCodes Diagnostics Inc. – Smartphone Provenance Checker
# Filename: is_this_a_smartphone_photo.py
# Author: Laughlin Kennedy
# Purpose: Certify if an image is consistent with smartphone/camera source
# Copy right 2025 Oddcodes Diagnostics Inc.
# ============================================================

import sys, struct, os, json, re

KNOWN_MAKES = [
    # Smartphones
    "Apple", "Samsung", "Google", "Huawei", "Xiaomi", "Oppo", "Vivo", "OnePlus",
    "Realme", "Motorola", "Sony", "LG", "Nokia", "Asus", "Honor", "ZTE", "Meizu",
    "Lenovo", "Alcatel", "TCL", "HTC", "Micromax", "Infinix", "Tecno",

    # Cameras
    "Canon", "Nikon", "Fujifilm", "Olympus", "Panasonic", "Leica", "Pentax",
    "Sigma", "Hasselblad", "Ricoh", "Minolta", "Konica", "Casio", "Kodak",
    "Phase One", "Mamiya", "Yashica", "Contax",

    # Lenses
    "Zeiss", "Carl Zeiss", "Tamron", "Tokina", "Samyang", "Voigtlander",
    "Voigtländer", "Rokinon", "Laowa", "Yongnuo", "Leitz",

    # Other devices
    "DJI", "GoPro", "Insta360", "Blackmagic", "RED", "ARRI"
]

CAMERA_MAKES = {
    "Canon", "Nikon", "Fujifilm", "Olympus", "Panasonic", "Leica", "Pentax",
    "Sigma", "Hasselblad", "Ricoh", "Minolta", "Konica", "Casio", "Kodak",
    "Phase One", "Mamiya", "Yashica", "Contax"
}

EDIT_SOFTWARE_TAGS = [
    "Adobe", "Photoshop", "Lightroom", "GIMP", "Affinity", "Paint.NET",
    "Corel", "AfterShot", "DxO", "Capture One", "Pixelmator", "Acorn",
    "Krita", "PhotoDirector"
]

def read_file_bytes(path):
    with open(path, "rb") as f:
        return f.read()

def has_exif(data):
    return b"Exif" in data[:4096]

def extract_make_model(data):
    try:
        idx = data.find(b"Exif")
        if idx == -1:
            return None, None
        ascii_data = data[idx:idx+16000].decode("latin-1", errors="ignore")
        make = None
        for candidate in KNOWN_MAKES:
            if candidate in ascii_data:
                make = candidate
                break
        model = None
        if "iPhone" in ascii_data:
            model = "iPhone"
        elif "SM-" in ascii_data:
            model = "Samsung Galaxy"
        elif "Pixel" in ascii_data:
            model = "Pixel"
        elif "Mate" in ascii_data or "P20" in ascii_data or "P30" in ascii_data:
            model = "Huawei Phone"
        elif "MI " in ascii_data or "Redmi" in ascii_data:
            model = "Xiaomi Phone"
        return make, model
    except Exception:
        return None, None

def jpeg_quant_tables(data):
    tables = 0
    i = 0
    while i < len(data) - 1:
        if data[i] == 0xFF and data[i+1] == 0xDB:
            try:
                length = struct.unpack(">H", data[i+2:i+4])[0]
                tables += 1
                i += length
            except Exception:
                i += 1
        else:
            i += 1
    return tables

def jpeg_resolution(data):
    i = 0
    while i < len(data) - 9:
        if data[i] == 0xFF and data[i+1] in [0xC0, 0xC2]:
            try:
                height = struct.unpack(">H", data[i+5:i+7])[0]
                width  = struct.unpack(">H", data[i+7:i+9])[0]
                return width, height
            except Exception:
                return None, None
        i += 1
    return None, None

def size_resolution_check(path, data, width, height):
    size_mb = len(data) / (1024 * 1024)
    if size_mb < 0.1:
        return False, "File too small to be a natural smartphone photo"
    if size_mb > 20:
        return False, "Unusually large for smartphone JPEG"
    if width and height:
        if width < 500 or height < 500:
            return False, "Resolution unusually low"
        if width > 12000 or height > 12000:
            return False, "Resolution unusually high (likely synthetic or scan)"
    return True, None

def detect_editing_tags(data):
    try:
        ascii_data = data.decode("latin-1", errors="ignore")
        for tag in EDIT_SOFTWARE_TAGS:
            if tag in ascii_data:
                return tag
        return None
    except Exception:
        return None

def detect_screenshot(exif_present, make, model, width, height):
    if not width or not height:
        return False
    aspect = round(width / height, 2) if height > 0 else 0
    common_aspects = [1.33, 1.5, 1.6, 1.77, 2.0]
    if not exif_present and not make and not model:
        for ca in common_aspects:
            if abs(aspect - ca) < 0.05:
                return True
    return False

# --- New: Extract timestamp, GPS (redacted), orientation ---
def extract_extra_metadata(data):
    ascii_data = data.decode("latin-1", errors="ignore")

    # Timestamp (looks for 20xx:xx:xx xx:xx:xx)
    ts_match = re.search(r"20\d{2}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}", ascii_data)
    timestamp = ts_match.group(0) if ts_match else None

    # Orientation (very crude substring)
    orientation = None
    if "Orientation" in ascii_data:
        idx = ascii_data.find("Orientation")
        orientation = ascii_data[idx:idx+30]

    # GPS detection (redacted)
    gps_pattern = re.compile(r"[-+]?\d{1,3}\.\d+")
    gps_coords = []
    for match in gps_pattern.findall(ascii_data):
        try:
            val = float(match)
            if -180 <= val <= 180:
                gps_coords.append(val)
        except Exception:
            pass
    gps_info_present = True if gps_coords else False

    return timestamp, orientation, gps_info_present

def is_smartphone_photo(path):
    data = read_file_bytes(path)
    reasons = []
    score = 0

    exif_present = has_exif(data)
    if exif_present:
        score += 1
    else:
        reasons.append("Missing EXIF metadata")

    make, model = extract_make_model(data)
    if make or model:
        score += 1
    else:
        reasons.append("No recognizable make/model")

    qtables = jpeg_quant_tables(data)
    if qtables > 0:
        score += 1
    else:
        reasons.append("No JPEG quantization tables found")

    width, height = jpeg_resolution(data)
    ok, msg = size_resolution_check(path, data, width, height)
    if ok:
        score += 1
    else:
        if msg:
            reasons.append(msg)

    edit_tag = detect_editing_tags(data)
    if edit_tag:
        reasons.append(f"Editing software tag detected: {edit_tag}")
        score -= 1

    screenshot = detect_screenshot(exif_present, make, model, width, height)
    if screenshot:
        reasons.append("Pattern matches screenshot")
        score -= 1

    # Extra fields
    timestamp, orientation, gps_info_present = extract_extra_metadata(data)
    if gps_info_present:
        reasons.append("GPS coordinates embedded (privacy relevant, redacted)")

    # Final verdict
    if screenshot:
        verdict = "LIKELY SCREENSHOT"
    elif make in CAMERA_MAKES:
        verdict = f"LIKELY DSLR / professional camera ({make})"
    elif make or model:
        verdict = f"Captured with {make or 'Unknown'} {model or ''}".strip()
    elif score >= 4:
        verdict = "YES: Likely smartphone photo"
    elif score == 3:
        verdict = "MAYBE: Some smartphone traits, not conclusive"
    else:
        verdict = "NO: Not certified as smartphone photo"

    return {
        "file": path,
        "verdict": verdict,
        "score": score,
        "make": make,
        "model": model,
        "resolution": f"{width}x{height}" if width and height else None,
        "timestamp": timestamp,
        "orientation": orientation,
        "gps_info_present": gps_info_present,
        "screenshot_detected": screenshot,
        "reasons": reasons
    }

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python is_this_a_smartphone_photo.py <image.jpg>")
        sys.exit(1)

    path = sys.argv[1]
    result = is_smartphone_photo(path)

    print("OddCodes Smartphone Provenance Report")
    print("-------------------------------------")
    print(json.dumps(result, indent=2))
