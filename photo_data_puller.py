"""Photo Data Puller

Analyze JPEG images for traits that suggest capture with a real-world camera lens.
Provides both a CLI and a Streamlit UI for quick drop-and-check workflows.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# Known device makers to match in EXIF payloads
KNOWN_MAKES = [
    # Smartphones
    "Apple",
    "Samsung",
    "Google",
    "Huawei",
    "Xiaomi",
    "Oppo",
    "Vivo",
    "OnePlus",
    "Realme",
    "Motorola",
    "Sony",
    "LG",
    "Nokia",
    "Asus",
    "Honor",
    "ZTE",
    "Meizu",
    "Lenovo",
    "Alcatel",
    "TCL",
    "HTC",
    "Micromax",
    "Infinix",
    "Tecno",
    # Cameras
    "Canon",
    "Nikon",
    "Fujifilm",
    "Olympus",
    "Panasonic",
    "Leica",
    "Pentax",
    "Sigma",
    "Hasselblad",
    "Ricoh",
    "Minolta",
    "Konica",
    "Casio",
    "Kodak",
    "Phase One",
    "Mamiya",
    "Yashica",
    "Contax",
    # Lenses
    "Zeiss",
    "Carl Zeiss",
    "Tamron",
    "Tokina",
    "Samyang",
    "Voigtlander",
    "Voigtländer",
    "Rokinon",
    "Laowa",
    "Yongnuo",
    "Leitz",
    # Other devices
    "DJI",
    "GoPro",
    "Insta360",
    "Blackmagic",
    "RED",
    "ARRI",
]

CAMERA_MAKES = {
    "Canon",
    "Nikon",
    "Fujifilm",
    "Olympus",
    "Panasonic",
    "Leica",
    "Pentax",
    "Sigma",
    "Hasselblad",
    "Ricoh",
    "Minolta",
    "Konica",
    "Casio",
    "Kodak",
    "Phase One",
    "Mamiya",
    "Yashica",
    "Contax",
}

EDIT_SOFTWARE_TAGS = [
    "Adobe",
    "Photoshop",
    "Lightroom",
    "GIMP",
    "Affinity",
    "Paint.NET",
    "Corel",
    "AfterShot",
    "DxO",
    "Capture One",
    "Pixelmator",
    "Acorn",
    "Krita",
    "PhotoDirector",
]


@dataclass
class PhotoVerdict:
    file: Path
    verdict: str
    score: int
    make: Optional[str]
    model: Optional[str]
    resolution: Optional[str]
    timestamp: Optional[str]
    orientation: Optional[str]
    gps_info_present: bool
    screenshot_detected: bool
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "file": str(self.file),
            "verdict": self.verdict,
            "score": self.score,
            "make": self.make,
            "model": self.model,
            "resolution": self.resolution,
            "timestamp": self.timestamp,
            "orientation": self.orientation,
            "gps_info_present": self.gps_info_present,
            "screenshot_detected": self.screenshot_detected,
            "reasons": self.reasons,
        }


def read_file_bytes(path: Path) -> bytes:
    return path.read_bytes()


def has_exif(data: bytes) -> bool:
    return b"Exif" in data[:4096]


def _find_in_ascii(data: bytes, search: Iterable[str]) -> Optional[str]:
    ascii_data = data.decode("latin-1", errors="ignore")
    for candidate in search:
        if candidate in ascii_data:
            return candidate
    return None


def extract_make_model(data: bytes) -> Tuple[Optional[str], Optional[str]]:
    try:
        idx = data.find(b"Exif")
        if idx == -1:
            return None, None
        ascii_data = data[idx : idx + 16000].decode("latin-1", errors="ignore")
        make = _find_in_ascii(ascii_data.encode("latin-1", errors="ignore"), KNOWN_MAKES)

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


def jpeg_quant_tables(data: bytes) -> int:
    tables = 0
    i = 0
    while i < len(data) - 1:
        if data[i] == 0xFF and data[i + 1] == 0xDB:
            try:
                length = struct.unpack(">H", data[i + 2 : i + 4])[0]
                tables += 1
                i += length
            except Exception:
                i += 1
        else:
            i += 1
    return tables


def jpeg_resolution(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    i = 0
    while i < len(data) - 9:
        if data[i] == 0xFF and data[i + 1] in [0xC0, 0xC2]:
            try:
                height = struct.unpack(">H", data[i + 5 : i + 7])[0]
                width = struct.unpack(">H", data[i + 7 : i + 9])[0]
                return width, height
            except Exception:
                return None, None
        i += 1
    return None, None


def size_resolution_check(
    data: bytes, width: Optional[int], height: Optional[int]
) -> Tuple[bool, Optional[str]]:
    size_mb = len(data) / (1024 * 1024)
    if size_mb < 0.1:
        return False, "File too small to be a natural camera photo"
    if size_mb > 20:
        return False, "Unusually large for a typical JPEG capture"
    if width and height:
        if width < 500 or height < 500:
            return False, "Resolution unusually low"
        if width > 12000 or height > 12000:
            return False, "Resolution unusually high (possible synthetic or scan)"
    return True, None


def detect_editing_tags(data: bytes) -> Optional[str]:
    try:
        ascii_data = data.decode("latin-1", errors="ignore")
        for tag in EDIT_SOFTWARE_TAGS:
            if tag in ascii_data:
                return tag
        return None
    except Exception:
        return None


def detect_screenshot(
    exif_present: bool, make: Optional[str], model: Optional[str], width: Optional[int], height: Optional[int]
) -> bool:
    if not width or not height:
        return False
    aspect = round(width / height, 2) if height > 0 else 0
    common_aspects = [1.33, 1.5, 1.6, 1.77, 2.0]
    if not exif_present and not make and not model:
        for ca in common_aspects:
            if abs(aspect - ca) < 0.05:
                return True
    return False


def extract_extra_metadata(data: bytes) -> Tuple[Optional[str], Optional[str], bool]:
    ascii_data = data.decode("latin-1", errors="ignore")

    timestamp = None
    ts_match = re.search(r"20\d{2}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}", ascii_data)
    if ts_match:
        timestamp = ts_match.group(0)

    orientation = None
    if "Orientation" in ascii_data:
        idx = ascii_data.find("Orientation")
        orientation = ascii_data[idx : idx + 30]

    gps_pattern = re.compile(r"[-+]?\d{1,3}\.\d+")
    gps_coords = []
    for match in gps_pattern.findall(ascii_data):
        try:
            val = float(match)
            if -180 <= val <= 180:
                gps_coords.append(val)
        except Exception:
            pass
    gps_info_present = bool(gps_coords)

    return timestamp, orientation, gps_info_present


def analyze_photo(path: Path) -> PhotoVerdict:
    data = read_file_bytes(path)
    reasons: List[str] = []
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
        reasons.append("No recognizable make/model detected")

    qtables = jpeg_quant_tables(data)
    if qtables > 0:
        score += 1
    else:
        reasons.append("No JPEG quantization tables found")

    width, height = jpeg_resolution(data)
    ok, msg = size_resolution_check(data, width, height)
    if ok:
        score += 1
    elif msg:
        reasons.append(msg)

    edit_tag = detect_editing_tags(data)
    if edit_tag:
        reasons.append(f"Editing software tag detected: {edit_tag}")
        score -= 1

    screenshot = detect_screenshot(exif_present, make, model, width, height)
    if screenshot:
        reasons.append("Pattern matches screenshot (no EXIF, common screen aspect ratio)")
        score -= 1

    timestamp, orientation, gps_info_present = extract_extra_metadata(data)
    if gps_info_present:
        reasons.append("GPS coordinates embedded (redacted in this report)")

    if screenshot:
        verdict = "Likely screenshot"
    elif make in CAMERA_MAKES:
        verdict = f"Likely standalone camera capture ({make})"
    elif make or model:
        verdict = f"Captured with {make or 'unknown make'} {model or ''}".strip()
    elif score >= 4:
        verdict = "Likely captured with a real-world camera"
    elif score == 3:
        verdict = "Possibly captured with a real-world camera"
    else:
        verdict = "Insufficient evidence for camera capture"

    resolution_str = f"{width}x{height}" if width and height else None

    return PhotoVerdict(
        file=path,
        verdict=verdict,
        score=score,
        make=make,
        model=model,
        resolution=resolution_str,
        timestamp=timestamp,
        orientation=orientation,
        gps_info_present=gps_info_present,
        screenshot_detected=screenshot,
        reasons=reasons,
    )


def run_cli(paths: List[Path]) -> None:
    results = [analyze_photo(p) for p in paths]
    for result in results:
        print("Photo Provenance Report")
        print("-----------------------")
        print(json.dumps(result.as_dict(), indent=2))
        print()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze JPEG photos to estimate whether they came from a real-world lens.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="One or more image paths to analyze",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_cli(args.paths)


if __name__ == "__main__":
    main()
