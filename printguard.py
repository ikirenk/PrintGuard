import os
import io
import time
import json
import shutil
import datetime
import threading
import subprocess
import traceback
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter, Transformation
from flask import Flask, request, jsonify, Response, render_template_string, send_file

try:
    from playsound3 import playsound
except ImportError:
    def playsound(*args, **kwargs):
        pass

import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUND_FILE = os.environ.get("PRINTGUARD_SOUND_FILE", os.path.join(BASE_DIR, "a.mp3"))
DEFAULT_LANG = os.environ.get("PRINTGUARD_LANG", "en").strip().lower()
if DEFAULT_LANG not in ("en", "tr"):
    DEFAULT_LANG = "en"

MSG = {
    "en": {
        "ready": "Ready. Upload a PDF to begin.",
        "no_cam": "No camera feed",
        "nostrip_ok": "No-strip mode (Camera check skipped)",
        "anchors_missing": "Strip anchors ({missing}) not visible",
        "strip_narrow": "Strip width too narrow in camera",
        "strip_oob": "Strip boxes out of camera bounds",
        "low_contrast": "Low Black/White contrast ({contrast})",
        "parity_err": "Parity error or blank page ({bits})",
        "page_mismatch": "Page mismatch! Expected: P{expected}, Read: P{detected}",
        "missing_ink": "Missing/Empty Ink: {inks}",
        "page_verified": "Page {page} verified ({pos} Strip)!",
        "job_aborted": "Print job cancelled by user.",
        "printing_send": "Sending page {page} / {total} to CUPS ({user})...",
        "cups_err": "Page {page} CUPS Print Error: {err}",
        "printing_wait": "Printing page {page} / {total}",
        "verifying": "Verifying Page {page}: {reason}",
        "verified_ok": "Page {page} optically verified!",
        "paused_err": "PAUSED (Page {page}): {reason}. Check ink/paper and select Retry or Continue.",
        "debug_done": "DEBUG MODE: {total} pages prepared (Strip: {pos}, Mode: {mode}, PageNum: {pnum}). Download the PDF below.",
        "done_simplex": "Success! All {total} pages printed (simplex).",
        "done_all": "Success! All {total} pages printed.",
        "duplex_rev_odd_extra": " IMPORTANT: Odd pages exceed even pages by 1 (Page {last_odd} will be single-sided). Flip the output stack into the input tray and place 1 BLANK SHEET at the BOTTOM for Page {last_odd} (Page {first_odd} will print on the back of Page {last_even} first).",
        "duplex_rev_normal": " Place the output stack into the input tray for the 2nd side (Page {first_odd} will print on the back of top Page {last_even} first).",
        "duplex_rev_msg": "Batch {start}-{end}: Even pages ({evens}) completed! Next: odd pages ({odds}).{note} Click 'Continue' when ready.",
        "duplex_norm_odd_extra": " (NOTE: Last printed Page {last_odd} has a blank back; leave it in the output tray!)",
        "duplex_norm_msg": "Batch {start}-{end}: Odd pages ({odds}) completed! Flip the stack into the input tray for even pages ({evens}) (Page {first_even} will print on the back of Page {first_odd} first){note}. Click 'Continue' when ready.",
        "batch_done": "Batch {start}-{end} completed! Empty the output tray, load paper for next batch ({next_p}..), and click 'Continue'.",
        "worker_err": "Print worker error: {err}",
        "job_running": "A job is currently running (Status: {status})! Click 'Abort Job' first.",
        "bad_password": "Invalid password for user '{user}'!",
        "no_pdf": "No PDF file selected!",
        "job_started": "'{name}' uploaded, preparing and printing in background!",
        "server_err": "Server error: {err}",
        "start_err": "Start Error: {err}",
        "reset_bad_auth": "Invalid username or password!",
        "reset_no_perm": "This account is not authorized to reset counters!",
        "reset_ok": "All page counters have been reset!",
        "no_stamped_pdf": "No processed PDF has been generated yet.",
        "admin_bad_auth": "Admin username or password is incorrect!",
        "admin_no_perm": "This account is not authorized to add users!",
        "bad_username": "Username must be 2-32 chars (letters, digits, '_' or '-').",
        "user_exists": "User '{user}' already exists!",
        "empty_pass": "Password cannot be empty!",
        "user_added": "User '{disp} ({user})' added successfully!",
        "pw_bad_auth": "Username or current password is incorrect!",
        "pw_updated": "Password updated for '{user}'!",
        "mode_bw": "Grayscale",
        "mode_color": "Color (CMYK)",
        "yes": "Yes",
        "no": "No",
        "no_logs": "Log file not created yet ({path})"
    },
    "tr": {
        "ready": "Hazır. Başlamak için PDF yükleyin.",
        "no_cam": "Kamera görüntüsü yok",
        "nostrip_ok": "Şeritsiz mod (Kamera kontrolü atlandı)",
        "anchors_missing": "Şerit çapaları ({missing}) görünmüyor",
        "strip_narrow": "Şerit genişliği kamerada çok dar",
        "strip_oob": "Şerit kutuları kamera sınırları dışında",
        "low_contrast": "Düşük Siyah/Beyaz kontrastı ({contrast})",
        "parity_err": "Parity hatası veya boş sayfa ({bits})",
        "page_mismatch": "Sayfa uyuşmazlığı! Beklenen: P{expected}, Okunan: P{detected}",
        "missing_ink": "Eksik/Biten Mürekkep: {inks}",
        "page_verified": "Sayfa {page} doğrulandı ({pos} Şerit)!",
        "job_aborted": "Baskı işi kullanıcı tarafından iptal edildi.",
        "printing_send": "Sayfa {page} / {total} CUPS'a gönderiliyor ({user})...",
        "cups_err": "Sayfa {page} CUPS Baskı Hatası: {err}",
        "printing_wait": "Sayfa {page} / {total} basılıyor",
        "verifying": "Sayfa {page} Doğrulanıyor: {reason}",
        "verified_ok": "Sayfa {page} optik olarak doğrulandı!",
        "paused_err": "DURAKLATILDI (Sayfa {page}): {reason}. Mürekkebi/kağıdı kontrol edip Tekrar Dene veya Devam Et seçin.",
        "debug_done": "DEBUG MODU: {total} sayfa hazırlandı (Şerit: {pos}, Mod: {mode}, SayfaNo: {pnum}). Aşağıdan PDF'i indirebilirsiniz.",
        "done_simplex": "Başarılı! Tüm {total} sayfa tek taraflı olarak basıldı.",
        "done_all": "Başarılı! Tüm {total} sayfa basıldı.",
        "duplex_rev_odd_extra": " ⚠️ ÖNEMLİ: Tek sayfa sayısı çiftlerden 1 fazla (Sayfa {last_odd} tek başına kalacak). Çıktı tepsisindeki desteyi çevirip besleme tepsisine koyun ve Sayfa {last_odd} için destenin EN ALTINA 1 adet BOŞ KAĞIT ekleyin (İlk olarak Sayfa {last_even}'nin arkasına Sayfa {first_odd} basılacak).",
        "duplex_rev_normal": " Çıktı tepsisindeki desteyi alıp 2. yüz için besleme tepsisine yerleştirin (En üstteki Sayfa {last_even}'nin arkasına ilk olarak Sayfa {first_odd} basılacak).",
        "duplex_rev_msg": "Parti {start}-{end}: Çift sayfalar ({evens}) tamamlandı! Şimdi tek sayfalar ({odds}) sırasıyla basılacak.{note} Hazır olduğunda 'Devam Et'e tıklayın.",
        "duplex_norm_odd_extra": " (NOT: Son basılan Sayfa {last_odd} kağıdının arkası boştur, onu çıktı tepsisinde bırakın!)",
        "duplex_norm_msg": "Parti {start}-{end}: Tek sayfalar ({odds}) tamamlandı! Desteyi 2. yüz için çevirip giriş tepsisine koyun (İlk olarak Sayfa {first_odd}'in arkasına Sayfa {first_even} basılacak){note}. Şimdi çift sayfalar ({evens}) basılacak. Hazır olduğunda 'Devam Et'e tıklayın.",
        "batch_done": "Parti {start}-{end} tamamlandı! Çıktı tepsisini boşaltın ve sonraki parti ({next_p}..) için kağıt ekleyip 'Devam Et'e tıklayın.",
        "worker_err": "Baskı işçisinde hata: {err}",
        "job_running": "Şu anda çalışan bir iş var (Durum: {status})! Önce 'İşi İptal Et' butonuna basın.",
        "bad_password": "'{user}' kullanıcısı için şifre hatalı!",
        "no_pdf": "PDF dosyası seçilmedi!",
        "job_started": "'{name}' yüklendi, arka planda hazırlanıp basılıyor!",
        "server_err": "Sunucu hatası oluştu: {err}",
        "start_err": "Başlatma Hatası: {err}",
        "reset_bad_auth": "Hatalı kullanıcı adı veya şifre!",
        "reset_no_perm": "Bu hesabın sayaç sıfırlama yetkisi yok!",
        "reset_ok": "Tüm sayfa sayaçları başarıyla sıfırlandı!",
        "no_stamped_pdf": "Henüz işlenmiş bir PDF oluşturulmadı.",
        "admin_bad_auth": "Yetkili kullanıcı adı veya şifre hatalı!",
        "admin_no_perm": "Bu hesabın kullanıcı ekleme yetkisi yok!",
        "bad_username": "Kullanıcı adı 2-32 karakter olmalı ve yalnızca harf, rakam, '_' veya '-' içermelidir!",
        "user_exists": "'{user}' kullanıcısı zaten mevcut!",
        "empty_pass": "Şifre boş olamaz!",
        "user_added": "Kullanıcı '{disp} ({user})' başarıyla eklendi!",
        "pw_bad_auth": "Kullanıcı adı veya mevcut şifre hatalı!",
        "pw_updated": "'{user}' kullanıcısının şifresi başarıyla güncellendi!",
        "mode_bw": "Siyah-Beyaz (Grayscale)",
        "mode_color": "Renkli (CMYK)",
        "yes": "Var",
        "no": "Yok",
        "no_logs": "Log dosyası henüz oluşmadı ({path})"
    }
}

def tr_msg(key, lang=None, **kwargs):
    l = lang if lang in ("en", "tr") else DEFAULT_LANG
    tpl = MSG.get(l, MSG["en"]).get(key, MSG["en"].get(key, key))
    try:
        return tpl.format(**kwargs)
    except Exception:
        return tpl

def get_req_lang():
    l = (request.headers.get("X-Lang") or request.args.get("lang") or "").strip().lower()
    return l if l in ("en", "tr") else DEFAULT_LANG

def play_completion_sound():
    if SOUND_FILE and os.path.exists(SOUND_FILE):
        try:
            playsound(SOUND_FILE)
        except Exception:
            pass

app = Flask(__name__)

# ==========================================
# DİZİN SEÇİMİ (YAZMA İZNİ KORUMALI)
# ==========================================
DEFAULT_WORKSPACE = os.environ.get("PRINTGUARD_WORKSPACE", "/opt/printguard/printguard_workspace")
try:
    os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)
    test_file = os.path.join(DEFAULT_WORKSPACE, ".write_test")
    with open(test_file, "w") as tf:
        tf.write("ok")
    os.remove(test_file)
    WORKSPACE_DIR = os.path.abspath(DEFAULT_WORKSPACE)
except Exception:
    WORKSPACE_DIR = os.path.abspath("/tmp/printguard_workspace")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

ARCHIVE_BASE_DIR = os.path.join(WORKSPACE_DIR, "archives")
COUNTS_FILE = os.path.join(WORKSPACE_DIR, "page_counts.json")
MAIN_LOG_FILE = os.path.join(WORKSPACE_DIR, "printguard.log")
os.makedirs(ARCHIVE_BASE_DIR, exist_ok=True)

# ==========================================
# KULLANICI YAPILANDIRMASI (users.json)
# ==========================================
DEFAULT_USERS = {
    "admin": {
        "password": "admin",
        "can_reset": True,
        "display_name": "Admin"
    }
}

def _resolve_users_file():
    env_path = os.environ.get("PRINTGUARD_USERS_FILE")
    if env_path:
        return os.path.abspath(env_path)
    candidate = os.path.join(BASE_DIR, "users.json")
    if os.path.exists(candidate):
        return candidate
    try:
        test_path = os.path.join(BASE_DIR, ".users_write_test")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        return candidate
    except Exception:
        return os.path.join(WORKSPACE_DIR, "users.json")

USERS_FILE = _resolve_users_file()
users_lock = threading.Lock()

def save_users(users_data):
    with users_lock:
        parent = os.path.dirname(USERS_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)

def load_users():
    with users_lock:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and loaded:
                    normalized = {}
                    for uname, info in loaded.items():
                        if isinstance(info, dict) and "password" in info:
                            normalized[str(uname)] = {
                                "password": str(info["password"]),
                                "can_reset": bool(info.get("can_reset", False)),
                                "display_name": str(info.get("display_name") or uname)
                            }
                    if normalized:
                        return normalized
            except Exception as e:
                print(f"users.json okuma hatası: {e}", flush=True)

    default_copy = {k: dict(v) for k, v in DEFAULT_USERS.items()}
    try:
        save_users(default_copy)
        print(f"Varsayılan users.json oluşturuldu ({USERS_FILE}). Lütfen admin şifresini değiştirin!", flush=True)
    except Exception as e:
        print(f"Varsayılan users.json yazılamadı: {e}", flush=True)
    return default_copy

USERS = load_users()

# ==========================================
# DOSYA TABANLI KESİN LOGLAMA SİSTEMİ
# ==========================================
log_lock = threading.Lock()

def log_event(msg, level="INFO", job_log_path=None):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [{level.upper()}] {msg}\n"
    print(line, end="", flush=True)
    with log_lock:
        try:
            with open(MAIN_LOG_FILE, "a", encoding="utf-8") as mf:
                mf.write(line)
        except Exception as e:
            print(f"Ana log yazma hatası: {e}", flush=True)

        if job_log_path:
            try:
                with open(job_log_path, "a", encoding="utf-8") as jf:
                    jf.write(line)
            except Exception:
                pass

def get_recent_logs(max_lines=80):
    if not os.path.exists(MAIN_LOG_FILE):
        return [tr_msg("no_logs", path=MAIN_LOG_FILE)]
    try:
        with open(MAIN_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [l.rstrip("\r\n") for l in lines[-max_lines:]]
    except Exception as e:
        return [f"Log okuma hatası: {e}"]

log_event(f"PrintGuard başlatıldı. Çalışma dizini: {WORKSPACE_DIR}")

# ==========================================
# SAYFA SAYAÇ YÖNETİMİ
# ==========================================
counts_lock = threading.Lock()

def load_page_counts():
    with counts_lock:
        data = {"users": {}, "last_reset": "Henüz sıfırlanmadı"}
        if os.path.exists(COUNTS_FILE):
            try:
                with open(COUNTS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data["users"] = loaded.get("users", {})
                        data["last_reset"] = loaded.get("last_reset", "Henüz sıfırlanmadı")
            except Exception:
                pass
        with users_lock:
            user_keys = list(USERS.keys())
        for u in user_keys:
            if u not in data["users"]:
                data["users"][u] = 0
        return data

def save_page_counts(data):
    with counts_lock:
        try:
            with open(COUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_event(f"Sayaç kaydetme hatası: {e}", level="ERROR")

def increment_user_page_count(username, pages=1):
    data = load_page_counts()
    with counts_lock:
        data["users"][username] = data["users"].get(username, 0) + pages
    save_page_counts(data)

save_page_counts(load_page_counts())

# ==========================================
# ARUCO 4x4 FIDUCIAL INITIALIZATION
# ==========================================
ARUCO_DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
USE_NEW_ARUCO_API = hasattr(cv2.aruco, "ArucoDetector")

if USE_NEW_ARUCO_API:
    ARUCO_PARAMS = cv2.aruco.DetectorParameters()
    ARUCO_PARAMS.minMarkerPerimeterRate = 0.012
    ARUCO_DETECTOR = cv2.aruco.ArucoDetector(ARUCO_DICT, ARUCO_PARAMS)
else:
    ARUCO_PARAMS = cv2.aruco.DetectorParameters_create()
    ARUCO_PARAMS.minMarkerPerimeterRate = 0.012

def detect_aruco_markers(gray_img):
    if USE_NEW_ARUCO_API:
        return ARUCO_DETECTOR.detectMarkers(gray_img)
    return cv2.aruco.detectMarkers(gray_img, ARUCO_DICT, parameters=ARUCO_PARAMS)

def generate_aruco_pil(marker_id, side_px=160):
    if hasattr(cv2.aruco, "generateImageMarker"):
        img = cv2.aruco.generateImageMarker(ARUCO_DICT, marker_id, side_px)
    else:
        img = np.zeros((side_px, side_px), dtype=np.uint8)
        cv2.aruco.drawMarker(ARUCO_DICT, marker_id, side_px, img, 1)
    bordered = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    return Image.fromarray(bordered).convert("RGB")

# ==========================================
# GLOBAL STATE & CONFIGURATION
# ==========================================
class PrintState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "IDLE"
        self.lang = DEFAULT_LANG
        self.message = tr_msg("ready", self.lang)
        self.current_user = ""
        self.pdf_path = None
        self.stamped_pdf_path = None
        self.job_archive_dir = None
        self.job_log_path = None

        self.total_pages = 0
        self.current_page = 0
        self.batch_size = 20
        self.printer_name = ""
        self.black_only = False
        self.add_page_numbers = True
        self.debug_mode = False
        self.strip_position = "top"
        self.duplex_mode = "duplex_reverse"
        self.settle_delay = 12.0
        self.verify_timeout = 90.0
        self.zoom_factor = 1.0
        self.manual_line = None

        self.last_qr = None
        self.last_bits_str = "----------"
        self.cmyk_status = {"C": False, "M": False, "Y": False, "K": False}
        self.cmyk_scores = {"C": 0.0, "M": 0.0, "Y": 0.0, "K": 0.0}

        self.action_event = threading.Event()
        self.abort_requested = False
        self.user_command = None
        self.annotated_frame = None

state = PrintState()

def get_cups_printers():
    try:
        res = subprocess.run(["lpstat", "-a"], capture_output=True, text=True, check=False)
        return [line.split()[0] for line in res.stdout.splitlines() if line.split()]
    except Exception:
        return []

def cancel_all_cups_jobs(printer_name=""):
    try:
        if printer_name and printer_name.strip():
            subprocess.run(["cancel", "-a", printer_name.strip()], capture_output=True, check=False)
        else:
            subprocess.run(["cancel", "-a"], capture_output=True, check=False)
    except Exception:
        pass

# ==========================================
# CAMERA VERIFIER
# ==========================================
NUM_SLOTS = 15

def get_slot_t(slot_idx):
    return 0.09 + slot_idx * (0.82 / (NUM_SLOTS - 1))

class CameraVerifier:
    def __init__(self, cam_index=0):
        self.cap = cv2.VideoCapture(cam_index, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(cam_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.running = True
        self.raw_frame = None
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while self.running:
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.raw_frame = frame
                else:
                    time.sleep(0.1)
            else:
                time.sleep(0.5)

    def _get_zoomed_frame(self):
        if self.raw_frame is None:
            return None
        frame = self.raw_frame.copy()
        z = float(state.zoom_factor)
        if z > 1.05:
            h, w = frame.shape[:2]
            nh, nw = int(h / z), int(w / z)
            y1, x1 = (h - nh) // 2, (w - nw) // 2
            cropped = frame[y1:y1 + nh, x1:x1 + nw]
            frame = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
        return frame

    def analyze_frame(self, expected_page_num=None):
        frame = self._get_zoomed_frame()
        if frame is None:
            return False, tr_msg("no_cam", state.lang), {}

        vis = frame.copy()
        h_img, w_img = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if state.strip_position == "none":
            cv2.putText(vis, "[NO-STRIP MODE] Camera verification disabled (Delay only)",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            state.annotated_frame = vis
            return True, tr_msg("nostrip_ok", state.lang), {}

        p_start = None
        p_end = None
        lock_mode = "AUTO-ANCHOR"

        if state.manual_line and len(state.manual_line) == 2:
            p1, p2 = state.manual_line
            p_start = np.array([p1[0] * w_img, p1[1] * h_img], dtype=np.float32)
            p_end = np.array([p2[0] * w_img, p2[1] * h_img], dtype=np.float32)
            lock_mode = "MANUAL-LINE LOCK"
        else:
            corners, ids, _ = detect_aruco_markers(gray)
            if ids is not None and len(ids) > 0:
                cv2.aruco.drawDetectedMarkers(vis, corners, ids)
                for c, mid in zip(corners, ids.flatten()):
                    pts = c[0]
                    center = np.mean(pts, axis=0)
                    if int(mid) == 900:
                        p_start = center
                    elif int(mid) == 901:
                        p_end = center

        mode_label = "BLACK-ONLY" if state.black_only else "CMYK COLOR"
        pos_label = state.strip_position.upper()

        if p_start is None or p_end is None:
            missing = "900 & 901" if (p_start is None and p_end is None) else ("900" if p_start is None else "901")
            cv2.putText(vis, f"[{mode_label} | {pos_label}] Waiting for Anchors ({missing}) or Click 2 Points...",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 165, 255), 2)
            state.annotated_frame = vis
            return False, tr_msg("anchors_missing", state.lang, missing=missing), {}

        cv2.line(vis, (int(p_start[0]), int(p_start[1])), (int(p_end[0]), int(p_end[1])), (255, 200, 0), 2)

        vec = p_end - p_start
        span_px = float(np.linalg.norm(vec))
        if span_px < 60:
            state.annotated_frame = vis
            return False, tr_msg("strip_narrow", state.lang), {}

        box_r = max(3, int(span_px * 0.016))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        def sample_patch(slot_idx):
            t = get_slot_t(slot_idx)
            pt = p_start + vec * t
            cx, cy = int(pt[0]), int(pt[1])
            x1, y1 = max(0, cx - box_r), max(0, cy - box_r)
            x2, y2 = min(w_img, cx + box_r), min(h_img, cy + box_r)
            return cx, cy, x1, y1, x2, y2, hsv[y1:y2, x1:x2], gray[y1:y2, x1:x2]

        _, _, kx1, ky1, kx2, ky2, k_hsv, k_gray = sample_patch(3)
        _, _, wx1, wy1, wx2, wy2, w_hsv, w_gray = sample_patch(4)

        if k_gray.size == 0 or w_gray.size == 0:
            state.annotated_frame = vis
            return False, tr_msg("strip_oob", state.lang), {}

        black_luma = float(np.median(k_gray))
        white_luma = float(np.median(w_gray))
        luma_contrast = white_luma - black_luma

        cv2.rectangle(vis, (wx1, wy1), (wx2, wy2), (255, 255, 0), 1)
        cv2.putText(vis, "W", (wx1, wy1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)

        bit_thresh = (white_luma + black_luma) / 2.0

        cmyk_keys = ["C", "M", "Y", "K"]
        results = {}
        scores = {}

        for idx, color_key in enumerate(cmyk_keys):
            cx, cy, x1, y1, x2, y2, roi_hsv, roi_gray = sample_patch(idx)
            if state.black_only and color_key in ("C", "M", "Y"):
                passed, ratio = self._check_black_relative(roi_gray, white_luma)
                results[color_key] = True
                scores[color_key] = round(ratio * 100, 1)
                cv2.rectangle(vis, (x1, y1), (x2, y2), (180, 180, 180), 1)
            else:
                if color_key == "K":
                    passed, ratio = self._check_black_relative(roi_gray, white_luma)
                else:
                    passed, ratio = self._check_color_hsv(roi_hsv, color_key)
                results[color_key] = passed
                scores[color_key] = round(ratio * 100, 1)
                b_col = (0, 255, 0) if passed else (0, 0, 255)
                cv2.rectangle(vis, (x1, y1), (x2, y2), b_col, 2)
                cv2.putText(vis, f"{color_key}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, b_col, 2)

        bits = []
        for bit_idx in range(10):
            slot_i = 5 + bit_idx
            cx, cy, x1, y1, x2, y2, _, roi_gray = sample_patch(slot_i)
            patch_luma = float(np.median(roi_gray)) if roi_gray.size > 0 else 255.0
            bit_val = 1 if (luma_contrast > 25 and patch_luma < bit_thresh) else 0
            bits.append(bit_val)

            b_col = (0, 255, 128) if bit_val == 1 else (180, 180, 180)
            cv2.rectangle(vis, (x1, y1), (x2, y2), b_col, 2 if bit_val == 1 else 1)
            cv2.putText(vis, str(bit_val), (x1 + 2, y2 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, b_col, 2)

        data_bits = bits[:9]
        parity_bit = bits[9]
        bits_str = "".join(str(b) for b in data_bits) + f"|P:{parity_bit}"
        state.last_bits_str = bits_str

        decoded_mod = 0
        for b in data_bits:
            decoded_mod = (decoded_mod << 1) | b

        parity_ok = (sum(data_bits) % 2) == parity_bit
        contrast_ok = luma_contrast >= 28.0

        if expected_page_num is not None and decoded_mod > 0:
            base_mult = ((expected_page_num - 1) // 511) * 511
            detected_page = base_mult + decoded_mod
        else:
            detected_page = decoded_mod

        header_col = (0, 255, 0) if (parity_ok and contrast_ok and detected_page > 0) else (0, 165, 255)
        cv2.putText(
            vis,
            f"[{lock_mode}] Bits: {bits_str} -> Page {detected_page} (Contrast:{int(luma_contrast)})",
            (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.65, header_col, 2
        )

        state.annotated_frame = vis
        state.cmyk_status = results
        state.cmyk_scores = scores

        if not contrast_ok:
            return False, tr_msg("low_contrast", state.lang, contrast=int(luma_contrast)), results

        if not parity_ok or detected_page == 0:
            return False, tr_msg("parity_err", state.lang, bits=bits_str), results

        state.last_qr = detected_page

        if expected_page_num is not None and detected_page != expected_page_num:
            return False, tr_msg("page_mismatch", state.lang, expected=expected_page_num, detected=detected_page), results

        active_channels = ["K"] if state.black_only else ["C", "M", "Y", "K"]
        missing_inks = [k for k in active_channels if not results.get(k, False)]
        if missing_inks:
            return False, tr_msg("missing_ink", state.lang, inks=", ".join(missing_inks)), results

        return True, tr_msg("page_verified", state.lang, page=detected_page, pos=pos_label), results

    @staticmethod
    def _check_black_relative(roi_gray, white_luma):
        if roi_gray.size == 0 or white_luma < 40:
            return False, 0.0
        dark_thresh = white_luma * 0.65
        dark_pixels = np.count_nonzero(roi_gray < dark_thresh)
        ratio = float(dark_pixels) / roi_gray.size
        return ratio >= 0.40, ratio

    @staticmethod
    def _check_color_hsv(roi_hsv, color_key):
        if color_key == "C":
            mask = cv2.inRange(roi_hsv, (75, 40, 45), (122, 255, 255))
        elif color_key == "M":
            m1 = cv2.inRange(roi_hsv, (132, 40, 45), (180, 255, 255))
            m2 = cv2.inRange(roi_hsv, (0, 40, 45), (14, 255, 255))
            mask = cv2.bitwise_or(m1, m2)
        elif color_key == "Y":
            mask = cv2.inRange(roi_hsv, (14, 45, 65), (48, 255, 255))
        else:
            return False, 0.0

        ratio = float(np.count_nonzero(mask)) / mask.size
        return ratio >= 0.35, ratio


verifier = CameraVerifier(int(os.environ.get("PRINTGUARD_CAMERA_INDEX", "0")))

# ==========================================
# PURE PIL + PYPDF STAMPER & PAGE NUMBERING
# ==========================================
def build_strip_overlay_pdf_page(width_pt, height_pt, pnum, total, black_only=False, strip_position="top"):
    strip_h_pt = 58.0
    scale = 2.5
    img_w = max(400, int(width_pt * scale))
    img_h = max(80, int(strip_h_pt * scale))

    strip_img = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(strip_img)

    cy = int(img_h * 0.52)
    m_size = int(44.0 * scale)
    cx_left = int(36.0 * scale)
    cx_right = img_w - int(36.0 * scale)
    span = cx_right - cx_left

    left_pil = generate_aruco_pil(900, side_px=m_size - 20).resize((m_size, m_size), Image.NEAREST)
    right_pil = generate_aruco_pil(901, side_px=m_size - 20).resize((m_size, m_size), Image.NEAREST)
    strip_img.paste(left_pil, (cx_left - m_size // 2, cy - m_size // 2))
    strip_img.paste(right_pil, (cx_right - m_size // 2, cy - m_size // 2))

    block_w = int((span * 0.82 / (NUM_SLOTS - 1)) * 0.78)
    block_h = int(34.0 * scale)

    cmyk_colors = [
        (0, 0, 0) if black_only else (0, 191, 255),
        (0, 0, 0) if black_only else (242, 0, 140),
        (0, 0, 0) if black_only else (255, 235, 0),
        (0, 0, 0),
    ]

    for s_idx, rgb in enumerate(cmyk_colors):
        px = int(cx_left + span * get_slot_t(s_idx))
        x0, y0 = px - block_w // 2, cy - block_h // 2
        x1, y1 = px + block_w // 2, cy + block_h // 2
        draw.rectangle([x0, y0, x1, y1], fill=rgb, outline=rgb)

    px_w = int(cx_left + span * get_slot_t(4))
    wx0, wy0 = px_w - block_w // 2, cy - block_h // 2
    wx1, wy1 = px_w + block_w // 2, cy + block_h // 2
    draw.rectangle([wx0, wy0, wx1, wy1], fill=(255, 255, 255), outline=(190, 190, 190), width=2)

    encoded_num = ((pnum - 1) % 511) + 1
    data_bits = [(encoded_num >> (8 - b)) & 1 for b in range(9)]
    parity_bit = sum(data_bits) % 2
    all_bits = data_bits + [parity_bit]

    for b_idx, bit_val in enumerate(all_bits):
        slot_i = 5 + b_idx
        px = int(cx_left + span * get_slot_t(slot_i))
        bx0, by0 = px - block_w // 2, cy - block_h // 2
        bx1, by1 = px + block_w // 2, cy + block_h // 2
        if bit_val == 1:
            draw.rectangle([bx0, by0, bx1, by1], fill=(0, 0, 0), outline=(0, 0, 0))
        else:
            draw.rectangle([bx0, by0, bx1, by1], fill=(255, 255, 255), outline=(200, 200, 200), width=2)

    buf = io.BytesIO()
    strip_img.save(buf, format="PDF", resolution=72.0 * scale)
    buf.seek(0)
    strip_pdf_page = PdfReader(buf).pages[0]

    writer = PdfWriter()
    full_overlay = writer.add_blank_page(width=width_pt, height=height_pt)
    ty = (height_pt - strip_h_pt) if strip_position == "top" else 0.0
    full_overlay.merge_transformed_page(strip_pdf_page, Transformation().translate(tx=0.0, ty=ty))
    return full_overlay

def build_page_number_overlay(width_pt, height_pt, pnum, total, strip_position="top"):
    """Sağ alt köşeye küçük sayfa numarası (Örn: 3 / 24) ekler."""
    box_w_pt = 85.0
    box_h_pt = 18.0
    scale = 2.5
    img_w = int(box_w_pt * scale)
    img_h = int(box_h_pt * scale)

    img = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    text = f"{pnum} / {total}"

    font = None
    for fp in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
    ]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, int(9.5 * scale))
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * int(6 * scale), int(10 * scale)

    tx_px = max(2, img_w - tw - int(6 * scale))
    ty_px = max(1, (img_h - th) // 2 - int(1 * scale))
    draw.text((tx_px, ty_px), text, fill=(60, 60, 60), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=72.0 * scale)
    buf.seek(0)
    num_pdf_page = PdfReader(buf).pages[0]

    writer = PdfWriter()
    full_overlay = writer.add_blank_page(width=width_pt, height=height_pt)

    tx_pt = max(0.0, width_pt - box_w_pt - 10.0)
    # Eğer kontrol şeridi alttaysa sayfa numarasını şeridin hemen üstüne koy
    ty_pt = 62.0 if strip_position == "bottom" else 6.0

    full_overlay.merge_transformed_page(num_pdf_page, Transformation().translate(tx=tx_pt, ty=ty_pt))
    return full_overlay

def stamp_pdf_with_markers(input_pdf, output_pdf, black_only=False, strip_position="top", add_page_numbers=False):
    reader = PdfReader(input_pdf)
    total = len(reader.pages)

    # Şerit yoksa ve sayfa numarası da istenmiyorsa doğrudan kopyala
    if strip_position == "none" and not add_page_numbers:
        shutil.copyfile(input_pdf, output_pdf)
        return total

    writer = PdfWriter()
    strip_h = 58.0 if strip_position != "none" else 0.0

    for idx, src_page in enumerate(reader.pages):
        pnum = idx + 1

        # 1. PDF'in kendi /Rotate etiketi varsa içeriğe aktar ve sıfırla
        rot = int(src_page.get("/Rotate", 0) or 0) % 360
        if rot != 0:
            try:
                src_page.transfer_rotation_to_content()
            except Exception:
                pass

        # MediaBox sol-alt (llx, lly) sıfırdan farklıysa sıfıra hizala
        llx = float(src_page.mediabox.left)
        lly = float(src_page.mediabox.bottom)
        w = float(src_page.mediabox.width)
        h = float(src_page.mediabox.height)

        base_transform = Transformation().translate(tx=-llx, ty=-lly)

        # 2. YATAY (LANDSCAPE) SAYFA DÜZELTMESİ:
        # Sayfa yataysa (w > h) ve kontrol şeridi aktifse, yazıcı kağıdı çevirdiğinde
        # şeridin yan kenarda çıkmasını önlemek için sayfayı Dikey (Portrait) forma çeviriyoruz.
        if w > h and strip_position != "none":
            target_w, target_h = h, w  # Dikey boyutlar (dar kenar üstte)
            avail_w = target_w
            avail_h = target_h - strip_h

            # 90 derece saat yönünün tersine döndürünce yeni genişlik=h, yeni yükseklik=w olur
            scale = min(avail_w / h, avail_h / w)
            scaled_w = h * scale
            scaled_h = w * scale

            tx = (avail_w - scaled_w) / 2.0
            ty_base = 0.0 if strip_position == "top" else strip_h
            ty = ty_base + (avail_h - scaled_h) / 2.0

            # (0,0) etrafında +90 derece döndürünce sayfa [-h, 0] x [0, w] aralığına düşer.
            # tx=+h ile pozitif bölgeye [0, h] x [0, w] taşıyıp ölçekliyoruz:
            transform = (
                base_transform
                .rotate(90)
                .translate(tx=h, ty=0)
                .scale(sx=scale, sy=scale)
                .translate(tx=tx, ty=ty)
            )
            new_page = writer.add_blank_page(width=target_w, height=target_h)
            new_page.merge_transformed_page(src_page, transform)
            out_w, out_h = target_w, target_h
        else:
            # Normal Dikey (Portrait) sayfa veya şeritsiz yatay sayfa
            out_w, out_h = w, h
            new_page = writer.add_blank_page(width=out_w, height=out_h)
            scale_y = (out_h - strip_h) / out_h
            ty_content = 0.0 if strip_position in ("top", "none") else strip_h

            transform = (
                base_transform
                .scale(sx=1.0, sy=scale_y)
                .translate(tx=0.0, ty=ty_content)
            )
            new_page.merge_transformed_page(src_page, transform)

        # 3. Kontrol şeridini (üst veya alt) ekle
        if strip_position != "none":
            overlay_page = build_strip_overlay_pdf_page(out_w, out_h, pnum, total, black_only, strip_position)
            new_page.merge_page(overlay_page)

        # 4. Sağ alta küçük sayfa numarası ekle
        if add_page_numbers:
            num_overlay = build_page_number_overlay(out_w, out_h, pnum, total, strip_position)
            new_page.merge_page(num_overlay)

    with open(output_pdf, "wb") as f_out:
        writer.write(f_out)
    return total

# ==========================================
# PRINT & DUPLEX ORCHESTRATION WORKER
# ==========================================
def send_page_to_cups(stamped_pdf_path, page_num, printer_name="", black_only=False):
    single_page_pdf = os.path.join(WORKSPACE_DIR, f"active_page_{page_num}.pdf")
    reader = PdfReader(stamped_pdf_path)
    writer = PdfWriter()
    writer.add_page(reader.pages[page_num - 1])
    with open(single_page_pdf, "wb") as f_out:
        writer.write(f_out)

    cmd = ["lp"]
    if printer_name.strip():
        cmd.extend(["-d", printer_name.strip()])
    if black_only:
        cmd.extend([
            "-o", "ColorModel=Gray",
            "-o", "ColorModel=KGray",
            "-o", "print-color-mode=monochrome",
            "-o", "ColorMode=Mono"
        ])
    cmd.extend(["-o", "fit-to-page", single_page_pdf])

    log_event(f"CUPS komutu çalıştırılıyor (Sayfa {page_num}): {' '.join(cmd)}", job_log_path=state.job_log_path)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err_detail = (res.stderr or res.stdout or "Bilinmeyen lp hatası").strip()
        avail = ", ".join(get_cups_printers()) or "Bulunamadı"
        raise RuntimeError(f"{err_detail} (Mevcut CUPS yazıcıları: {avail})")
    else:
        increment = 1
        if state.duplex_mode != "simplex":
            # Her (1,2), (3,4) çifti tek yaprak kağıt harcar; sayımı tek sayfalarda (+1) yapıyoruz
            increment = 1 if (page_num % 2 == 1) else 0

        if increment > 0:
            increment_user_page_count(state.current_user, increment)
            log_event(f"Sayaç güncellendi: {state.current_user} için +{increment} yaprak eklendi (Sayfa {page_num}).", job_log_path=state.job_log_path)

        out_msg = (res.stdout or "").strip()
        log_event(f"CUPS yanıtı (Sayfa {page_num}): {out_msg}", job_log_path=state.job_log_path)

def save_verification_snapshot(page_num, status_tag):
    if not state.job_archive_dir:
        return
    frame = state.annotated_frame if state.annotated_frame is not None else verifier._get_zoomed_frame()
    if frame is not None:
        ts = datetime.datetime.now().strftime("%H%M%S")
        fname = f"page_{page_num:03d}_{status_tag}_{ts}.jpg"
        fpath = os.path.join(state.job_archive_dir, fname)
        try:
            cv2.imwrite(fpath, frame)
            log_event(f"Kamera kontrol resmi kaydedildi: {fname}", job_log_path=state.job_log_path)
        except Exception as e:
            log_event(f"Kamera resmi kaydedilemedi: {e}", level="WARNING", job_log_path=state.job_log_path)

def interruptible_sleep(seconds, custom_msg_prefix=None):
    end_t = time.time() + seconds
    while time.time() < end_t:
        if state.abort_requested:
            return False
        if custom_msg_prefix:
            rem = max(0, int(round(end_t - time.time())))
            state.message = f"{custom_msg_prefix} (CUPS bekleme süresi: {rem} sn kaldı...)"
        time.sleep(0.25)
    return True

def wait_for_user_action():
    state.action_event.clear()
    while not state.action_event.is_set():
        if state.abort_requested:
            return "ABORT"
        time.sleep(0.2)
    return state.user_command

def print_and_verify_single_page(page_num):
    while True:
        if state.abort_requested:
            return False

        state.current_page = page_num
        state.status = "PRINTING"
        state.message = tr_msg("printing_send", state.lang, page=page_num, total=state.total_pages, user=state.current_user)
        log_event(state.message, job_log_path=state.job_log_path)

        try:
            send_page_to_cups(state.stamped_pdf_path, page_num, state.printer_name, state.black_only)
        except Exception as e:
            state.status = "PAUSED_ERROR"
            state.message = tr_msg("cups_err", state.lang, page=page_num, err=e)
            log_event(state.message, level="ERROR", job_log_path=state.job_log_path)
            cmd = wait_for_user_action()
            if cmd == "ABORT":
                return False
            elif cmd == "CONTINUE":
                return True
            continue

        # Şeritsiz modda da CUPS kuyruğunun şişmemesi için settle_delay kadar bekle
        wait_prefix = tr_msg("printing_wait", state.lang, page=page_num, total=state.total_pages)
        if not interruptible_sleep(state.settle_delay, custom_msg_prefix=wait_prefix):
            return False

        if state.strip_position == "none":
            verifier.analyze_frame(expected_page_num=page_num)
            save_verification_snapshot(page_num, "nostrip_printed")
            log_event(f"Sayfa {page_num} (Şeritsiz Mod) bekleme süresi ({state.settle_delay} sn) tamamlandı.", job_log_path=state.job_log_path)
            return True

        state.status = "VERIFYING"
        start_t = time.time()
        verified = False
        last_reason = tr_msg("no_cam", state.lang)

        while time.time() - start_t < state.verify_timeout:
            if state.abort_requested:
                return False
            ok, reason, _ = verifier.analyze_frame(expected_page_num=page_num)
            last_reason = reason
            state.message = tr_msg("verifying", state.lang, page=page_num, reason=reason)
            if ok:
                verified = True
                break
            time.sleep(0.4)

        if verified:
            save_verification_snapshot(page_num, "verified")
            state.message = tr_msg("verified_ok", state.lang, page=page_num)
            log_event(f"Sayfa {page_num} doğrulandı.", job_log_path=state.job_log_path)
            time.sleep(0.5)
            return True

        save_verification_snapshot(page_num, "failed")
        state.status = "PAUSED_ERROR"
        state.message = tr_msg("paused_err", state.lang, page=page_num, reason=last_reason)
        log_event(state.message, level="WARNING", job_log_path=state.job_log_path)

        cmd = wait_for_user_action()
        if cmd == "ABORT":
            return False
        elif cmd == "CONTINUE":
            save_verification_snapshot(page_num, "manual_skip")
            log_event(f"Sayfa {page_num} manuel onaylandı.", job_log_path=state.job_log_path)
            return True
        elif cmd == "RETRY":
            log_event(f"Sayfa {page_num} tekrar basılıyor (RETRY).", job_log_path=state.job_log_path)
            continue

def print_job_worker():
    try:
        log_event(
            f"PDF damgalama/hazırlama başlıyor... Şerit={state.strip_position}, SiyahBeyaz={state.black_only}, SayfaNo={state.add_page_numbers}",
            job_log_path=state.job_log_path
        )
        total = stamp_pdf_with_markers(
            state.pdf_path,
            state.stamped_pdf_path,
            black_only=state.black_only,
            strip_position=state.strip_position,
            add_page_numbers=state.add_page_numbers
        )
        state.total_pages = total
        log_event(f"PDF hazırlandı: Toplam {total} sayfa.", job_log_path=state.job_log_path)

        if state.debug_mode:
            state.status = "COMPLETED"
            pos_str = state.strip_position.upper()
            mode_str = tr_msg("mode_bw", state.lang) if state.black_only else tr_msg("mode_color", state.lang)
            pnum_str = tr_msg("yes", state.lang) if state.add_page_numbers else tr_msg("no", state.lang)
            state.message = tr_msg("debug_done", state.lang, total=total, pos=pos_str, mode=mode_str, pnum=pnum_str)
            log_event(state.message, job_log_path=state.job_log_path)
            return

        log_event(
            f"Baskı döngüsü başladı: Kullanıcı={state.current_user}, Toplam Sayfa={total}, Mod={state.duplex_mode}",
            job_log_path=state.job_log_path
        )

        # 1. TEK TARAFLI (SIMPLEX) MOD
        if state.duplex_mode == "simplex":
            for p in range(1, total + 1):
                if not print_and_verify_single_page(p):
                    state.status = "IDLE"
                    state.message = tr_msg("job_aborted", state.lang)
                    log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                    return
            state.status = "COMPLETED"
            state.message = tr_msg("done_simplex", state.lang, total=total)
            play_completion_sound()
            log_event(state.message, job_log_path=state.job_log_path)
            return

        # 2. ÇİFT TARAFLI (DUPLEX) MODLAR
        sheets_per_batch = max(1, state.batch_size)
        pages_per_batch = sheets_per_batch * 2

        for batch_start in range(1, total + 1, pages_per_batch):
            batch_end = min(total, batch_start + pages_per_batch - 1)
            odd_pages = [p for p in range(batch_start, batch_end + 1) if p % 2 == 1]
            even_pages = [p for p in range(batch_start, batch_end + 1) if p % 2 == 0]

            if state.duplex_mode == "duplex_reverse":
                # TERS ÇİFTLER MODU: ÖNCE ÇİFT SAYFALAR (TERSTEN: 10, 8, 6, 4, 2), SONRA TEK SAYFALAR (1, 3, 5, 7, 9)
                even_pages_rev = list(reversed(even_pages))

                if even_pages_rev:
                    for p in even_pages_rev:
                        if not print_and_verify_single_page(p):
                            state.status = "IDLE"
                            state.message = tr_msg("job_aborted", state.lang)
                            log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                            return

                    odd_str = ", ".join(str(x) for x in odd_pages)
                    even_str = ", ".join(str(x) for x in even_pages_rev)

                    if len(odd_pages) > len(even_pages_rev):
                        extra_note = tr_msg(
                            "duplex_rev_odd_extra", state.lang,
                            last_odd=odd_pages[-1], first_odd=odd_pages[0], last_even=even_pages_rev[-1]
                        )
                    else:
                        extra_note = tr_msg(
                            "duplex_rev_normal", state.lang,
                            first_odd=odd_pages[0], last_even=even_pages_rev[-1]
                        )

                    state.status = "PAUSED_DUPLEX"
                    state.message = tr_msg(
                        "duplex_rev_msg", state.lang,
                        start=batch_start, end=batch_end, evens=even_str, odds=odd_str, note=extra_note
                    )
                    log_event(state.message, job_log_path=state.job_log_path)

                    if wait_for_user_action() == "ABORT":
                        state.status = "IDLE"
                        state.message = tr_msg("job_aborted", state.lang)
                        log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                        return

                for p in odd_pages:
                    if not print_and_verify_single_page(p):
                        state.status = "IDLE"
                        state.message = tr_msg("job_aborted", state.lang)
                        log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                        return

            else:
                # KLASİK DÜZ ÇİFTLER MODU: ÖNCE TEKLER (1, 3, 5..), SONRA ÇİFTLER (2, 4, 6..)
                for p in odd_pages:
                    if not print_and_verify_single_page(p):
                        state.status = "IDLE"
                        state.message = tr_msg("job_aborted", state.lang)
                        log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                        return

                if even_pages:
                    odd_str = ", ".join(str(x) for x in odd_pages)
                    even_str = ", ".join(str(x) for x in even_pages)
                    extra_note = ""
                    if len(odd_pages) > len(even_pages):
                        extra_note = tr_msg("duplex_norm_odd_extra", state.lang, last_odd=odd_pages[-1])

                    state.status = "PAUSED_DUPLEX"
                    state.message = tr_msg(
                        "duplex_norm_msg", state.lang,
                        start=batch_start, end=batch_end, odds=odd_str, evens=even_str,
                        first_odd=odd_pages[0], first_even=even_pages[0], note=extra_note
                    )
                    log_event(state.message, job_log_path=state.job_log_path)

                    if wait_for_user_action() == "ABORT":
                        state.status = "IDLE"
                        state.message = tr_msg("job_aborted", state.lang)
                        log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                        return

                    for p in even_pages:
                        if not print_and_verify_single_page(p):
                            state.status = "IDLE"
                            state.message = tr_msg("job_aborted", state.lang)
                            log_event(state.message, level="WARNING", job_log_path=state.job_log_path)
                            return

            if batch_end < total:
                state.status = "PAUSED_DUPLEX"
                state.message = tr_msg("batch_done", state.lang, start=batch_start, end=batch_end, next_p=batch_end + 1)
                log_event(state.message, job_log_path=state.job_log_path)
                if wait_for_user_action() == "ABORT":
                    state.status = "IDLE"
                    state.message = tr_msg("job_aborted", state.lang)
                    return

        state.status = "COMPLETED"
        state.message = tr_msg("done_all", state.lang, total=total)
        play_completion_sound()
        log_event(state.message, job_log_path=state.job_log_path)
    except Exception as e:
        err_trace = traceback.format_exc()
        state.status = "IDLE"
        state.message = tr_msg("worker_err", state.lang, err=e)
        log_event(f"Worker Hatası: {e}\n{err_trace}", level="ERROR", job_log_path=state.job_log_path)

# ==========================================
# FLASK WEB UI & API ENDPOINTS
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>PrintGuard - Print & Optical Verification Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: system-ui, sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
        .grid { display: grid; grid-template-columns: 1.05fr 0.95fr; gap: 20px; max-width: 1320px; margin: auto; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        .card { background: #1e1e1e; padding: 20px; border-radius: 10px; border: 1px solid #333; margin-bottom: 20px; }
        h2, h3 { margin-top: 0; color: #fff; }
        .header-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
        .lang-switch { display: flex; gap: 6px; }
        .lang-btn { background: #2b2b2b; color: #ccc; border: 1px solid #444; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 0.82rem; }
        .lang-btn.active { background: #3a86ff; color: #fff; border-color: #3a86ff; }
        .status-banner { padding: 15px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; font-size: 1.02rem; line-height: 1.45; }
        .st-IDLE, .st-COMPLETED { background: #1b4332; color: #74c69d; }
        .st-PRINTING, .st-VERIFYING { background: #023e8a; color: #90e0ef; }
        .st-PAUSED_ERROR { background: #641220; color: #ffccd5; animation: pulse 1.5s infinite; }
        .st-PAUSED_DUPLEX { background: #7f4f24; color: #ffe5d9; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.65; } 100% { opacity: 1; } }
        .cmyk-row { display: flex; gap: 10px; margin: 15px 0; }
        .ink-badge { flex: 1; padding: 10px; border-radius: 6px; text-align: center; font-weight: bold; }
        .btn { padding: 10px 15px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 0.92rem; margin-right: 6px; margin-bottom: 8px; display: inline-block; text-decoration: none; }
        .btn-primary { background: #3a86ff; color: #fff; }
        .btn-primary:disabled { background: #555; cursor: wait; }
        .btn-success { background: #2b9348; color: #fff; }
        .btn-warn { background: #f77f00; color: #fff; }
        .btn-danger { background: #d62828; color: #fff; }
        .btn-debug { background: #8338ec; color: #fff; }
        .btn-zoom { background: #333; color: #fff; padding: 6px 11px; font-size: 0.85rem; }
        input[type="file"], input[type="number"], input[type="text"], input[type="password"], select {
            background: #2b2b2b; color: #fff; border: 1px solid #444; padding: 9px;
            border-radius: 4px; width: 100%; box-sizing: border-box; margin-bottom: 12px;
        }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .checkbox-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; background: #262626; padding: 10px; border-radius: 6px; border: 1px solid #383838; }
        .checkbox-row input { width: 18px; height: 18px; margin: 0; cursor: pointer; }
        .checkbox-row label { cursor: pointer; font-weight: 500; }
        img.cam { width: 100%; border-radius: 8px; border: 2px solid #444; cursor: crosshair; }
        .mono { font-family: monospace; background: #2b2b2b; padding: 3px 7px; border-radius: 4px; color: #80ffdb; }
        .user-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .user-table th, .user-table td { border: 1px solid #383838; padding: 8px 10px; text-align: left; }
        .user-table th { background: #262626; }
        .log-box { background: #0d0d0d; color: #9ef01a; font-family: monospace; font-size: 0.8rem; padding: 10px; border-radius: 6px; height: 220px; overflow-y: auto; border: 1px solid #333; white-space: pre-wrap; }
        #clientDebugBox { display:none; padding:12px; border-radius:6px; margin-bottom:12px; font-weight:bold; background:#3b2f00; color:#ffd166; border:1px solid #ffd166; }
    </style>
</head>
<body>
<div class="grid">
    <div>
        <div class="card">
            <div class="header-row">
                <h2 style="margin:0;" data-i18n="title_panel">🖨️ PrintGuard Control Panel</h2>
                <div class="lang-switch">
                    <button type="button" id="langBtnEn" class="lang-btn" onclick="setLanguage('en')">🇬🇧 EN</button>
                    <button type="button" id="langBtnTr" class="lang-btn" onclick="setLanguage('tr')">🇹🇷 TR</button>
                </div>
            </div>
            <div id="statusBanner" class="status-banner st-IDLE" data-i18n="loading">Loading...</div>
            <p>
                <strong data-i18n="lbl_active_user">Active User:</strong> <span id="curUser" class="mono">-</span> |
                <strong data-i18n="lbl_progress">Progress:</strong> <span data-i18n="lbl_page">Page</span> <span id="curPage">0</span> / <span id="totPage">0</span> |
                <strong data-i18n="lbl_read_page">Read Page:</strong> <span id="lastQr">-</span> |
                <strong data-i18n="lbl_bits">Bits:</strong> <span id="lastBits" class="mono">----------</span>
            </p>

            <div class="cmyk-row">
                <div id="badgeC" class="ink-badge" style="background:#00b4d8; color:#000;">C: <span id="scC">0%</span></div>
                <div id="badgeM" class="ink-badge" style="background:#f72585; color:#fff;">M: <span id="scM">0%</span></div>
                <div id="badgeY" class="ink-badge" style="background:#ffbe0b; color:#000;">Y: <span id="scY">0%</span></div>
                <div id="badgeK" class="ink-badge" style="background:#333; color:#fff; border:1px solid #666;">K: <span id="scK">0%</span></div>
            </div>

            <div id="debugDownloadBox" style="display:none; margin: 15px 0;">
                <a href="/api/download_stamped" target="_blank" class="btn btn-debug" data-i18n="btn_download_pdf">📥 View / Download Processed PDF</a>
            </div>

            <div id="actionControls" style="margin: 18px 0; display:none; padding: 12px; background: #262626; border-radius: 8px; border: 1px solid #444;">
                <button id="btnRetry" type="button" class="btn btn-warn" onclick="sendCmd('RETRY')" data-i18n="btn_retry">🔄 Retry This Page</button>
                <button id="btnContinue" type="button" class="btn btn-success" onclick="sendCmd('CONTINUE')" data-i18n="btn_continue">✅ Approve / Continue</button>
                <button id="btnAbort" type="button" class="btn btn-danger" onclick="sendCmd('ABORT')" data-i18n="btn_abort">🛑 Abort Job</button>
            </div>

            <hr style="border-color:#333; margin: 20px 0;">
            <h3 data-i18n="hdr_new_job">Start New Print Job</h3>

            <div id="clientDebugBox"></div>

            <form id="uploadForm" onsubmit="return false;">
                <div class="form-row">
                    <div>
                        <label data-i18n="lbl_select_user">👤 Select User:</label>
                        <select id="f_username" name="username">
                            {% for u, info in users.items() %}
                            <option value="{{ u }}">{{ info.display_name }} ({{ u }})</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label data-i18n="lbl_password">🔑 Password:</label>
                        <input id="f_password" type="password" name="password" placeholder="Enter your password" data-i18n-placeholder="ph_password">
                    </div>
                </div>

                <label data-i18n="lbl_select_pdf">📄 Select PDF File:</label>
                <input id="f_pdf" type="file" name="pdf" accept=".pdf">

                <label data-i18n="lbl_duplex_mode">🔄 Print Mode (Duplex Ordering / Simplex):</label>
                <select id="f_duplex_mode" name="duplex_mode">
                    <option value="duplex_reverse" selected data-i18n="opt_duplex_rev">🔁 Duplex - Reverse Evens First: 10,8,6,4,2 ➔ 1,3,5,7,9</option>
                    <option value="duplex_normal" data-i18n="opt_duplex_norm">🔁 Duplex - Normal Order: 1,3,5,7,9 ➔ 2,4,6,8,10</option>
                    <option value="simplex" data-i18n="opt_simplex">📄 Simplex (Single-Sided): 1, 2, 3, 4, 5...</option>
                </select>

                <label data-i18n="lbl_strip_pos">📏 Verification Strip Position:</label>
                <select id="f_strip_position" name="strip_position">
                    <option value="bottom" data-i18n="opt_strip_bottom">⬇️ Bottom Strip</option>
                    <option value="top" selected data-i18n="opt_strip_top">⬆️ Top Strip (Auto-rotates landscape PDFs)</option>
                    <option value="none" data-i18n="opt_strip_none">🚫 No Strip (Skip Camera Check - Delay Only)</option>
                </select>

                <div class="checkbox-row">
                    <input type="checkbox" id="addPageNumbers" name="add_page_numbers" value="1" checked>
                    <label for="addPageNumbers" data-i18n="chk_page_nums">🔢 Add Small Page Number at Bottom-Right (e.g. 1 / 20)</label>
                </div>

                <div class="checkbox-row">
                    <input type="checkbox" id="blackOnly" name="black_only" value="1">
                    <label for="blackOnly" data-i18n="chk_black_only">⬛ Black-Only Mode (Force CUPS Grayscale + Black Strip)</label>
                </div>

                <div class="checkbox-row">
                    <input type="checkbox" id="debugMode" name="debug_mode" value="1">
                    <label for="debugMode" data-i18n="chk_debug_mode">🔍 Debug Mode: Prepare PDF Only (Do not send to printer)</label>
                </div>

                <div class="form-row">
                    <div>
                        <label data-i18n="lbl_printer">🖨️ CUPS Printer Queue:</label>
                        <select id="f_printer_name" name="printer_name">
                            <option value="" data-i18n="opt_default_printer">-- System Default Printer --</option>
                            {% for p in printers %}
                            <option value="{{ p }}">{{ p }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label data-i18n="lbl_batch_size">📚 Batch Size (Sheets per flip):</label>
                        <input id="f_batch_size" type="number" name="batch_size" value="20" min="1" max="200">
                    </div>
                </div>

                <label data-i18n="lbl_settle_delay">⏱️ Paper Settle Delay (seconds before camera check / next page):</label>
                <input id="f_settle_delay" type="number" name="settle_delay" value="20" min="2" max="120">

                <button id="submitBtn" type="button" onclick="startPrintJob()" class="btn btn-primary" style="width:100%; padding:12px; font-size:1rem;" data-i18n="btn_start">🚀 Prepare PDF & Start Printing</button>
            </form>
        </div>
    </div>

    <div>
        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap;">
                <h2 style="margin:0;" data-i18n="hdr_cam">📷 Live Camera & Optical Check</h2>
                <div>
                    <button type="button" class="btn btn-zoom" onclick="clearManualLine()" data-i18n="btn_auto_anchor">🎯 Auto Anchor</button>
                    <button type="button" class="btn btn-zoom" onclick="setZoom(1.0)">1x</button>
                    <button type="button" class="btn btn-zoom" onclick="setZoom(1.8)">1.8x</button>
                    <button type="button" class="btn btn-zoom" onclick="setZoom(2.5)">2.5x</button>
                </div>
            </div>
            <img id="camImg" class="cam" src="/video_feed" alt="Camera Stream" title="For manual line lock, click 900 (CMYK end) then 901 (Binary end)." data-i18n-title="cam_title">
        </div>

        <div class="card">
            <h3 data-i18n="hdr_counters">📊 Monthly User Page Counter</h3>
            <p style="font-size:0.88rem; color:#aaa; margin-top:0;"><span data-i18n="lbl_last_reset">Last Reset:</span> <span id="lastResetText" class="mono">-</span></p>
            <table class="user-table">
                <thead>
                    <tr>
                        <th data-i18n="th_user">User</th>
                        <th data-i18n="th_pages">Printed Pages</th>
                    </tr>
                </thead>
                <tbody id="userCountsBody"></tbody>
            </table>

            <div style="margin-top: 15px; background: #262626; padding: 12px; border-radius: 6px; border: 1px solid #383838;">
                <strong data-i18n="hdr_reset_counters">🔄 Reset Monthly Counters (Admin Only):</strong>
                <div class="form-row" style="margin-top:8px;">
                    <select id="resetUser">
                        {% for u, info in users.items() %}
                        {% if info.can_reset %}
                        <option value="{{ u }}">{{ info.display_name }} ({{ u }})</option>
                        {% endif %}
                        {% endfor %}
                    </select>
                    <input type="password" id="resetPass" placeholder="Admin password..." data-i18n-placeholder="ph_admin_pass">
                </div>
                <button type="button" class="btn btn-danger" onclick="resetCounters()" style="margin-bottom:0;" data-i18n="btn_reset_all">🗑️ Reset All Counters</button>
            </div>
        </div>

        <div class="card">
            <h3 data-i18n="hdr_user_mgmt">👥 User Management</h3>
            <div style="background: #262626; padding: 12px; border-radius: 6px; border: 1px solid #383838; margin-bottom: 14px;">
                <strong data-i18n="hdr_change_pw">🔑 Change Password:</strong>
                <div class="form-row" style="margin-top:8px;">
                    <select id="pwUser">
                        {% for u, info in users.items() %}
                        <option value="{{ u }}">{{ info.display_name }} ({{ u }})</option>
                        {% endfor %}
                    </select>
                    <input type="password" id="pwCurrent" placeholder="Current password..." data-i18n-placeholder="ph_cur_pass">
                </div>
                <input type="password" id="pwNew" placeholder="New password..." data-i18n-placeholder="ph_new_pass">
                <button type="button" class="btn btn-warn" onclick="changePassword()" style="margin-bottom:0;" data-i18n="btn_update_pw">🔑 Update Password</button>
            </div>

            <div style="background: #262626; padding: 12px; border-radius: 6px; border: 1px solid #383838;">
                <strong data-i18n="hdr_add_user">➕ Add New User (Admin Only):</strong>
                <div class="form-row" style="margin-top:8px;">
                    <select id="adminAuthUser">
                        {% for u, info in users.items() %}
                        {% if info.can_reset %}
                        <option value="{{ u }}">{{ info.display_name }} ({{ u }})</option>
                        {% endif %}
                        {% endfor %}
                    </select>
                    <input type="password" id="adminAuthPass" placeholder="Admin password..." data-i18n-placeholder="ph_admin_pass">
                </div>
                <div class="form-row">
                    <input type="text" id="newUsername" placeholder="Username (e.g. alice)" data-i18n-placeholder="ph_new_username">
                    <input type="text" id="newDisplayName" placeholder="Display name (e.g. Alice)" data-i18n-placeholder="ph_new_disp">
                </div>
                <input type="password" id="newUserPass" placeholder="New user password..." data-i18n-placeholder="ph_new_user_pass">
                <div class="checkbox-row">
                    <input type="checkbox" id="newUserCanReset">
                    <label for="newUserCanReset" data-i18n="chk_admin_perm">Admin privileges (can reset counters and add users)</label>
                </div>
                <button type="button" class="btn btn-primary" onclick="addUser()" style="margin-bottom:0;" data-i18n="btn_add_user">➕ Add User</button>
            </div>
        </div>

        <div class="card">
            <h3 data-i18n="hdr_logs">📝 System Logs</h3>
            <div id="logBox" class="log-box" data-i18n="logs_loading">Loading logs...</div>
        </div>
    </div>
</div>

<script>
const I18N = {
    en: {
        page_title: "PrintGuard - Print & Optical Verification Server",
        title_panel: "🖨️ PrintGuard Control Panel",
        loading: "Loading...",
        lbl_active_user: "Active User:",
        lbl_progress: "Progress:",
        lbl_page: "Page",
        lbl_read_page: "Read Page:",
        lbl_bits: "Bits:",
        btn_download_pdf: "📥 View / Download Processed PDF",
        btn_retry: "🔄 Retry This Page",
        btn_continue: "✅ Approve / Continue",
        btn_abort: "🛑 Abort Job",
        hdr_new_job: "Start New Print Job",
        lbl_select_user: "👤 Select User:",
        lbl_password: "🔑 Password:",
        ph_password: "Enter your password",
        lbl_select_pdf: "📄 Select PDF File:",
        lbl_duplex_mode: "🔄 Print Mode (Duplex Ordering / Simplex):",
        opt_duplex_rev: "🔁 Duplex - Reverse Evens First: 10,8,6,4,2 ➔ 1,3,5,7,9",
        opt_duplex_norm: "🔁 Duplex - Normal Order: 1,3,5,7,9 ➔ 2,4,6,8,10",
        opt_simplex: "📄 Simplex (Single-Sided): 1, 2, 3, 4, 5...",
        lbl_strip_pos: "📏 Verification Strip Position:",
        opt_strip_bottom: "⬇️ Bottom Strip",
        opt_strip_top: "⬆️ Top Strip (Auto-rotates landscape PDFs)",
        opt_strip_none: "🚫 No Strip (Skip Camera Check - Delay Only)",
        chk_page_nums: "🔢 Add Small Page Number at Bottom-Right (e.g. 1 / 20)",
        chk_black_only: "⬛ Black-Only Mode (Force CUPS Grayscale + Black Strip)",
        chk_debug_mode: "🔍 Debug Mode: Prepare PDF Only (Do not send to printer)",
        lbl_printer: "🖨️ CUPS Printer Queue:",
        opt_default_printer: "-- System Default Printer --",
        lbl_batch_size: "📚 Batch Size (Sheets per flip):",
        lbl_settle_delay: "⏱️ Paper Settle Delay (seconds before camera check / next page):",
        btn_start: "🚀 Prepare PDF & Start Printing",
        hdr_cam: "📷 Live Camera & Optical Check",
        btn_auto_anchor: "🎯 Auto Anchor",
        cam_title: "For manual line lock, click 900 (CMYK end) then 901 (Binary end).",
        hdr_counters: "📊 Monthly User Page Counter",
        lbl_last_reset: "Last Reset:",
        th_user: "User",
        th_pages: "Printed Pages",
        hdr_reset_counters: "🔄 Reset Monthly Counters (Admin Only):",
        ph_admin_pass: "Admin password...",
        btn_reset_all: "🗑️ Reset All Counters",
        hdr_user_mgmt: "👥 User Management",
        hdr_change_pw: "🔑 Change Password:",
        ph_cur_pass: "Current password...",
        ph_new_pass: "New password...",
        btn_update_pw: "🔑 Update Password",
        hdr_add_user: "➕ Add New User (Admin Only):",
        ph_new_username: "Username (e.g. alice)",
        ph_new_disp: "Display name (e.g. Alice)",
        ph_new_user_pass: "New user password...",
        chk_admin_perm: "Admin privileges (can reset counters and add users)",
        btn_add_user: "➕ Add User",
        hdr_logs: "📝 System Logs",
        logs_loading: "Loading logs...",
        none: "None",
        pages_unit: "pages",
        alert_reset_pass: "Please enter the admin password!",
        confirm_reset: "Are you sure you want to reset monthly page counters for all users?",
        alert_pw_fields: "Please enter current and new password!",
        alert_add_fields: "Admin password, username, and new password are required!",
        err_no_pass: "❌ Please enter your password!",
        err_no_pdf: "❌ Please select a PDF file!",
        btn_sending: "⏳ Sending to Server...",
        msg_uploading: "⏳ 1/2: Uploading PDF and settings to server...",
        err_non_json: "❌ Server returned non-JSON error: ",
        err_prefix: "❌ Error: ",
        err_unknown: "Unknown error",
        ok_started: "Job started!",
        err_conn: "❌ Connection Error: "
    },
    tr: {
        page_title: "PrintGuard - Baskı & Optik Kontrol Sunucusu",
        title_panel: "🖨️ PrintGuard Kontrol Paneli",
        loading: "Yükleniyor...",
        lbl_active_user: "Aktif Kullanıcı:",
        lbl_progress: "İlerleme:",
        lbl_page: "Sayfa",
        lbl_read_page: "Okunan Sayfa:",
        lbl_bits: "Bitler:",
        btn_download_pdf: "📥 İşlenmiş PDF'i Görüntüle / İndir",
        btn_retry: "🔄 Bu Sayfayı Tekrar Bas",
        btn_continue: "✅ Onayla / Sonrakine Geç",
        btn_abort: "🛑 İşi İptal Et (Abort Job)",
        hdr_new_job: "Yeni Baskı İşi Başlat",
        lbl_select_user: "👤 Kullanıcı Seçin:",
        lbl_password: "🔑 Şifre:",
        ph_password: "Şifrenizi girin",
        lbl_select_pdf: "📄 PDF Dosyası Seçin:",
        lbl_duplex_mode: "🔄 Yazdırma Modu (Çift Taraflı Sıralama / Tek Taraflı):",
        opt_duplex_rev: "🔁 Çift Taraflı - Ters Çiftler Önce: 10,8,6,4,2 ➔ 1,3,5,7,9",
        opt_duplex_norm: "🔁 Çift Taraflı - Düz Çiftler: 1,3,5,7,9 ➔ 2,4,6,8,10 (Klasik Sıralama)",
        opt_simplex: "📄 Tek Taraflı (Simplex): 1, 2, 3, 4, 5... (Çevirme Yok)",
        lbl_strip_pos: "📏 Kontrol Çizgisi (Strip) Seçeneği:",
        opt_strip_bottom: "⬇️ Sayfanın Altında (Bottom Strip)",
        opt_strip_top: "⬆️ Sayfanın Üstünde (Top Strip - Yatay PDF'leri Otomatik Dikeyleştirir)",
        opt_strip_none: "🚫 Kontrol Çizgisi Yok (Kamera Doğrulamasız - Sadece Süre Beklemeli)",
        chk_page_nums: "🔢 Sağ Alta Küçük Sayfa Numarası Ekle (Örn: 1 / 20)",
        chk_black_only: "⬛ Siyah-Beyaz Modu (CUPS Grayscale zorlar + Şeridi siyah basar)",
        chk_debug_mode: "🔍 Debug Modu: Sadece PDF'i hazırla (Yazıcıya gönderme)",
        lbl_printer: "🖨️ CUPS Yazıcı Kuyruğu:",
        opt_default_printer: "-- Sistem Varsayılan Yazıcısı --",
        lbl_batch_size: "📚 Parti Boyutu (Kaç yaprakta bir çevrilsin):",
        lbl_settle_delay: "⏱️ Kağıt Çıkış Bekleme Süresi (Kamera kontrolü veya şeritsiz sonraki sayfa öncesi saniye):",
        btn_start: "🚀 PDF'i Hazırla ve Baskıyı Başlat",
        hdr_cam: "📷 Canlı Kamera & Optik Kontrol",
        btn_auto_anchor: "🎯 Otomatik Çapa",
        cam_title: "Manuel çizgi kilidi için önce 900 (CMYK ucu) sonra 901 (Binary ucu) noktasına tıklayın.",
        hdr_counters: "📊 Kullanıcı Aylık Sayfa Sayacı",
        lbl_last_reset: "Son Sıfırlama:",
        th_user: "Kullanıcı",
        th_pages: "Basılan Sayfa",
        hdr_reset_counters: "🔄 Aylık Sayaç Sıfırlama (Sadece Yetkili Hesap):",
        ph_admin_pass: "Yetkili şifresi...",
        btn_reset_all: "🗑️ Tüm Sayaçları Sıfırla",
        hdr_user_mgmt: "👥 Kullanıcı Yönetimi",
        hdr_change_pw: "🔑 Şifre Değiştir:",
        ph_cur_pass: "Mevcut şifre...",
        ph_new_pass: "Yeni şifre...",
        btn_update_pw: "🔑 Şifreyi Güncelle",
        hdr_add_user: "➕ Yeni Kullanıcı Ekle (Yetkili Hesap):",
        ph_new_username: "Kullanıcı adı (örn: ali)",
        ph_new_disp: "Görünen ad (örn: Ali)",
        ph_new_user_pass: "Yeni kullanıcı şifresi...",
        chk_admin_perm: "Yetkili hesap (Sayaç sıfırlama ve kullanıcı ekleme yetkisi)",
        btn_add_user: "➕ Kullanıcı Ekle",
        hdr_logs: "📝 Detaylı Sistem Logları",
        logs_loading: "Loglar yükleniyor...",
        none: "Yok",
        pages_unit: "sayfa",
        alert_reset_pass: "Lütfen yetkili şifresini girin!",
        confirm_reset: "Tüm kullanıcıların aylık sayfa sayaçlarını sıfırlamak istediğinize emin misiniz?",
        alert_pw_fields: "Lütfen mevcut ve yeni şifreyi girin!",
        alert_add_fields: "Yetkili şifresi, kullanıcı adı ve yeni şifre zorunludur!",
        err_no_pass: "❌ Lütfen şifrenizi girin!",
        err_no_pdf: "❌ Lütfen bir PDF dosyası seçin!",
        btn_sending: "⏳ Sunucuya Gönderiliyor...",
        msg_uploading: "⏳ 1/2: PDF dosyası ve ayarlar sunucuya yükleniyor...",
        err_non_json: "❌ Sunucu JSON yerine hata döndürdü: ",
        err_prefix: "❌ Hata: ",
        err_unknown: "Bilinmeyen hata",
        ok_started: "İş başarıyla başlatıldı!",
        err_conn: "❌ Bağlantı Hatası: "
    }
};

let currentLang = localStorage.getItem('pg_lang') || '{{ default_lang }}';
if (!I18N[currentLang]) currentLang = 'en';

function t(key) {
    return (I18N[currentLang] && I18N[currentLang][key]) || I18N.en[key] || key;
}

function setLanguage(lang) {
    if (!I18N[lang]) return;
    currentLang = lang;
    localStorage.setItem('pg_lang', lang);
    document.title = t('page_title');
    document.getElementById('langBtnEn').classList.toggle('active', lang === 'en');
    document.getElementById('langBtnTr').classList.toggle('active', lang === 'tr');

    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.innerText = t(el.getAttribute('data-i18n'));
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        el.title = t(el.getAttribute('data-i18n-title'));
    });
    pollStatus();
}

function showClientMsg(msg, isError=false) {
    const box = document.getElementById('clientDebugBox');
    box.style.display = 'block';
    box.style.background = isError ? '#641220' : '#1b4332';
    box.style.color = isError ? '#ffccd5' : '#74c69d';
    box.style.borderColor = isError ? '#ff4d6d' : '#52b788';
    box.innerText = msg;
}

let clickPts = [];
const camImg = document.getElementById('camImg');
camImg.addEventListener('click', async (e) => {
    const rect = camImg.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    clickPts.push([nx, ny]);
    if (clickPts.length === 2) {
        await fetch('/api/manual_line', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({points: clickPts})
        });
        clickPts = [];
    }
});

async function clearManualLine() {
    clickPts = [];
    await fetch('/api/manual_line', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({points: null})
    });
}

async function setZoom(z) {
    await fetch('/api/zoom', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({zoom: z})
    });
}

async function pollStatus() {
    try {
        const res = await fetch('/api/status?t=' + Date.now());
        if (!res.ok) return;
        const d = await res.json();
        const b = document.getElementById('statusBanner');
        b.className = 'status-banner st-' + d.status;
        b.innerText = `[${d.status}] ${d.message}`;
        document.getElementById('curUser').innerText = d.current_user || '-';
        document.getElementById('curPage').innerText = d.current_page;
        document.getElementById('totPage').innerText = d.total_pages;
        document.getElementById('lastQr').innerText = d.last_qr || t('none');
        document.getElementById('lastBits').innerText = d.last_bits_str || '----------';

        document.getElementById('scC').innerText = d.cmyk_scores.C + '%';
        document.getElementById('scM').innerText = d.cmyk_scores.M + '%';
        document.getElementById('scY').innerText = d.cmyk_scores.Y + '%';
        document.getElementById('scK').innerText = d.cmyk_scores.K + '%';

        const cmyOpacity = (d.black_only || d.strip_position === 'none') ? '0.2' : '1.0';
        document.getElementById('badgeC').style.opacity = cmyOpacity;
        document.getElementById('badgeM').style.opacity = cmyOpacity;
        document.getElementById('badgeY').style.opacity = cmyOpacity;

        document.getElementById('debugDownloadBox').style.display = d.has_stamped_pdf ? 'block' : 'none';

        const ctrl = document.getElementById('actionControls');
        const isRunning = ['PRINTING', 'VERIFYING', 'PAUSED_ERROR', 'PAUSED_DUPLEX'].includes(d.status);
        const isPaused = d.status.startsWith('PAUSED');
        ctrl.style.display = isRunning ? 'block' : 'none';
        document.getElementById('btnRetry').style.display = (d.status === 'PAUSED_ERROR') ? 'inline-block' : 'none';
        document.getElementById('btnContinue').style.display = isPaused ? 'inline-block' : 'none';

        if (d.users_meta) {
            syncUserDropdowns(d.users_meta);
        }

        if (d.page_counts && d.page_counts.users) {
            document.getElementById('lastResetText').innerText = d.page_counts.last_reset || '-';
            const tbody = document.getElementById('userCountsBody');
            tbody.innerHTML = '';
            const dispMap = d.user_display_names || {};
            for (const [u, count] of Object.entries(d.page_counts.users)) {
                const disp = dispMap[u] || u;
                tbody.innerHTML += `<tr><td><strong>${disp}</strong> <span class="mono">(${u})</span></td><td><strong>${count}</strong> ${t('pages_unit')}</td></tr>`;
            }
        }

        const logBox = document.getElementById('logBox');
        const wasAtBottom = (logBox.scrollHeight - logBox.clientHeight) <= (logBox.scrollTop + 30);
        logBox.innerText = (d.recent_logs || []).join('\\n');
        if (wasAtBottom) {
            logBox.scrollTop = logBox.scrollHeight;
        }
    } catch (e) {
        console.error("pollStatus error:", e);
    }
}
setInterval(pollStatus, 1000);
pollStatus();

function syncUserDropdowns(usersMeta) {
    const allIds = ['f_username', 'pwUser'];
    const adminIds = ['resetUser', 'adminAuthUser'];

    const fillSelect = (id, adminOnly) => {
        const sel = document.getElementById(id);
        if (!sel) return;
        const prev = sel.value;
        const entries = Object.entries(usersMeta).filter(([_, info]) => !adminOnly || info.can_reset);
        const signature = entries.map(([u, info]) => `${u}:${info.display_name}:${info.can_reset}`).join('|');
        if (sel.dataset.sig === signature) return;
        sel.dataset.sig = signature;
        sel.innerHTML = '';
        for (const [u, info] of entries) {
            const opt = document.createElement('option');
            opt.value = u;
            opt.text = `${info.display_name} (${u})`;
            sel.appendChild(opt);
        }
        if (entries.some(([u]) => u === prev)) {
            sel.value = prev;
        }
    };

    allIds.forEach(id => fillSelect(id, false));
    adminIds.forEach(id => fillSelect(id, true));
}

async function changePassword() {
    const username = document.getElementById('pwUser').value;
    const current_password = document.getElementById('pwCurrent').value;
    const new_password = document.getElementById('pwNew').value;
    if (!current_password || !new_password) {
        alert(t('alert_pw_fields'));
        return;
    }
    const res = await fetch('/api/users/change_password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Lang': currentLang},
        body: JSON.stringify({username, current_password, new_password})
    });
    const out = await res.json();
    alert(out.message);
    if (res.ok) {
        document.getElementById('pwCurrent').value = '';
        document.getElementById('pwNew').value = '';
        pollStatus();
    }
}

async function addUser() {
    const admin_username = document.getElementById('adminAuthUser').value;
    const admin_password = document.getElementById('adminAuthPass').value;
    const new_username = document.getElementById('newUsername').value.trim();
    const display_name = document.getElementById('newDisplayName').value.trim();
    const new_password = document.getElementById('newUserPass').value;
    const can_reset = document.getElementById('newUserCanReset').checked;

    if (!admin_password || !new_username || !new_password) {
        alert(t('alert_add_fields'));
        return;
    }
    const res = await fetch('/api/users/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Lang': currentLang},
        body: JSON.stringify({admin_username, admin_password, new_username, display_name, new_password, can_reset})
    });
    const out = await res.json();
    alert(out.message);
    if (res.ok) {
        document.getElementById('adminAuthPass').value = '';
        document.getElementById('newUsername').value = '';
        document.getElementById('newDisplayName').value = '';
        document.getElementById('newUserPass').value = '';
        document.getElementById('newUserCanReset').checked = false;
        pollStatus();
    }
}

async function sendCmd(action) {
    await fetch('/api/action', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Lang': currentLang},
        body: JSON.stringify({action})
    });
    pollStatus();
}

async function resetCounters() {
    const username = document.getElementById('resetUser').value;
    const password = document.getElementById('resetPass').value;
    if (!password) {
        alert(t('alert_reset_pass'));
        return;
    }
    if (!confirm(t('confirm_reset'))) {
        return;
    }
    const res = await fetch('/api/reset_counts', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Lang': currentLang},
        body: JSON.stringify({username, password})
    });
    const out = await res.json();
    alert(out.message);
    if (res.ok) {
        document.getElementById('resetPass').value = '';
        pollStatus();
    }
}

async function startPrintJob() {
    const fileInput = document.getElementById('f_pdf');
    const passInput = document.getElementById('f_password');

    if (!passInput.value) {
        showClientMsg(t('err_no_pass'), true);
        return;
    }
    if (!fileInput.files || fileInput.files.length === 0) {
        showClientMsg(t('err_no_pdf'), true);
        return;
    }

    const btn = document.getElementById('submitBtn');
    const origText = btn.innerText;
    btn.disabled = true;
    btn.innerText = t('btn_sending');
    showClientMsg(t('msg_uploading'), false);

    try {
        const formElement = document.getElementById('uploadForm');
        const formData = new FormData(formElement);

        const res = await fetch('/api/start', {
            method: 'POST',
            headers: {'X-Lang': currentLang},
            body: formData
        });
        const text = await res.text();
        let out = {};
        try {
            out = JSON.parse(text);
        } catch (err) {
            showClientMsg(t('err_non_json') + text.substring(0, 250), true);
            return;
        }

        if (!res.ok) {
            showClientMsg(t('err_prefix') + (out.message || t('err_unknown')), true);
        } else {
            showClientMsg("✅ " + (out.message || t('ok_started')), false);
        }
    } catch (err) {
        showClientMsg(t('err_conn') + err, true);
    } finally {
        btn.disabled = false;
        btn.innerText = origText;
        pollStatus();
    }
}

setLanguage(currentLang);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    with users_lock:
        users_snapshot = {u: dict(info) for u, info in USERS.items()}
    return render_template_string(
        HTML_TEMPLATE,
        printers=get_cups_printers(),
        users=users_snapshot,
        workspace_dir=WORKSPACE_DIR,
        default_lang=DEFAULT_LANG
    )

@app.route("/api/zoom", methods=["POST"])
def api_zoom():
    data = request.json or {}
    state.zoom_factor = float(data.get("zoom", 1.0))
    return jsonify({"ok": True, "zoom": state.zoom_factor})

@app.route("/api/manual_line", methods=["POST"])
def api_manual_line():
    data = request.json or {}
    state.manual_line = data.get("points")
    return jsonify({"ok": True})

@app.route("/api/status")
def api_status():
    if state.status in ("IDLE", "PAUSED_ERROR", "PAUSED_DUPLEX", "COMPLETED"):
        verifier.analyze_frame(expected_page_num=state.current_page or None)
    with users_lock:
        users_snapshot = {u: dict(info) for u, info in USERS.items()}
    return jsonify({
        "status": state.status,
        "message": state.message,
        "current_user": state.current_user,
        "current_page": state.current_page,
        "total_pages": state.total_pages,
        "last_qr": state.last_qr,
        "last_bits_str": state.last_bits_str,
        "black_only": state.black_only,
        "add_page_numbers": state.add_page_numbers,
        "strip_position": state.strip_position,
        "duplex_mode": state.duplex_mode,
        "cmyk_status": state.cmyk_status,
        "cmyk_scores": state.cmyk_scores,
        "has_stamped_pdf": bool(state.stamped_pdf_path and os.path.exists(state.stamped_pdf_path)),
        "page_counts": load_page_counts(),
        "user_display_names": {u: info["display_name"] for u, info in users_snapshot.items()},
        "users_meta": {
            u: {"display_name": info["display_name"], "can_reset": bool(info.get("can_reset", False))}
            for u, info in users_snapshot.items()
        },
        "recent_logs": get_recent_logs(80)
    })

@app.route("/api/users/add", methods=["POST"])
def api_users_add():
    lang = get_req_lang()
    data = request.json or {}
    admin_username = (data.get("admin_username") or "").strip()
    admin_password = (data.get("admin_password") or "").strip()
    new_username = (data.get("new_username") or "").strip()
    display_name = (data.get("display_name") or "").strip() or new_username
    new_password = (data.get("new_password") or "").strip()
    can_reset = bool(data.get("can_reset", False))

    with users_lock:
        admin_info = USERS.get(admin_username)
        if not admin_info or admin_info["password"] != admin_password:
            log_event(f"Başarısız kullanıcı ekleme denemesi (Yetkili: {admin_username})", level="WARNING")
            return jsonify({"message": tr_msg("admin_bad_auth", lang)}), 403
        if not admin_info.get("can_reset", False):
            return jsonify({"message": tr_msg("admin_no_perm", lang)}), 403
        if not re.match(r"^[A-Za-z0-9_-]{2,32}$", new_username):
            return jsonify({"message": tr_msg("bad_username", lang)}), 400
        if new_username in USERS:
            return jsonify({"message": tr_msg("user_exists", lang, user=new_username)}), 409
        if not new_password:
            return jsonify({"message": tr_msg("empty_pass", lang)}), 400

        USERS[new_username] = {
            "password": new_password,
            "can_reset": can_reset,
            "display_name": display_name
        }
        snapshot = {u: dict(info) for u, info in USERS.items()}

    save_users(snapshot)
    save_page_counts(load_page_counts())
    log_event(f"Yeni kullanıcı eklendi: '{new_username}' (Ad: {display_name}, Yetkili: {can_reset}) - Ekleyen: {admin_username}")
    return jsonify({"message": tr_msg("user_added", lang, disp=display_name, user=new_username)})

@app.route("/api/users/change_password", methods=["POST"])
def api_users_change_password():
    lang = get_req_lang()
    data = request.json or {}
    username = (data.get("username") or "").strip()
    current_password = (data.get("current_password") or "").strip()
    new_password = (data.get("new_password") or "").strip()

    if not new_password:
        return jsonify({"message": tr_msg("empty_pass", lang)}), 400

    with users_lock:
        user_info = USERS.get(username)
        if not user_info or user_info["password"] != current_password:
            log_event(f"Başarısız şifre değiştirme denemesi (Kullanıcı: {username})", level="WARNING")
            return jsonify({"message": tr_msg("pw_bad_auth", lang)}), 403
        USERS[username]["password"] = new_password
        snapshot = {u: dict(info) for u, info in USERS.items()}

    save_users(snapshot)
    log_event(f"Kullanıcı şifresi güncellendi: '{username}'")
    return jsonify({"message": tr_msg("pw_updated", lang, user=username)})

@app.route("/api/reset_counts", methods=["POST"])
def api_reset_counts():
    lang = get_req_lang()
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    with users_lock:
        user_info = dict(USERS.get(username) or {})
        user_keys = list(USERS.keys())

    if not user_info or user_info.get("password") != password:
        log_event(f"Başarısız sayaç sıfırlama denemesi (Kullanıcı: {username})", level="WARNING")
        return jsonify({"message": tr_msg("reset_bad_auth", lang)}), 403

    if not user_info.get("can_reset", False):
        log_event(f"Yetkisiz sayaç sıfırlama denemesi (Kullanıcı: {username})", level="WARNING")
        return jsonify({"message": tr_msg("reset_no_perm", lang)}), 403

    old_counts = load_page_counts()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = {
        "users": {u: 0 for u in user_keys},
        "last_reset": f"{now_str} ({username})"
    }
    save_page_counts(new_data)
    log_event(f"Aylık sayfa sayaçları '{username}' tarafından sıfırlandı. Eski değerler: {old_counts['users']}")
    return jsonify({"message": tr_msg("reset_ok", lang)})

@app.route("/api/download_stamped")
def api_download_stamped():
    lang = get_req_lang()
    if not state.stamped_pdf_path or not os.path.exists(state.stamped_pdf_path):
        return tr_msg("no_stamped_pdf", lang), 404
    return send_file(state.stamped_pdf_path, as_attachment=False, download_name="printguard_output.pdf")

@app.route("/api/start", methods=["POST"])
def api_start():
    lang = get_req_lang()
    log_event("/api/start isteği alındı.")
    try:
        if state.status not in ("IDLE", "COMPLETED"):
            msg = tr_msg("job_running", lang, status=state.status)
            log_event(msg, level="WARNING")
            return jsonify({"message": msg}), 400

        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        with users_lock:
            user_info = dict(USERS.get(username) or {})

        if not user_info or user_info.get("password") != password:
            log_event(f"Hatalı şifre girişi! Kullanıcı='{username}', GirilenŞifreUzunluğu={len(password)}", level="WARNING")
            return jsonify({"message": tr_msg("bad_password", lang, user=username)}), 401

        f = request.files.get("pdf")
        if not f or not f.filename:
            log_event("PDF dosyası yüklenmedi!", level="WARNING")
            return jsonify({"message": tr_msg("no_pdf", lang)}), 400

        try:
            state.batch_size = max(1, int(request.form.get("batch_size") or 20))
        except ValueError:
            state.batch_size = 20

        try:
            state.settle_delay = max(1.0, float(request.form.get("settle_delay") or 20.0))
        except ValueError:
            state.settle_delay = 20.0

        state.lang = lang
        state.current_user = username
        state.printer_name = (request.form.get("printer_name") or "").strip()
        state.black_only = request.form.get("black_only") == "1"
        state.add_page_numbers = request.form.get("add_page_numbers") == "1"
        state.debug_mode = request.form.get("debug_mode") == "1"
        state.strip_position = (request.form.get("strip_position") or "bottom").strip().lower()
        state.duplex_mode = (request.form.get("duplex_mode") or "duplex_reverse").strip().lower()
        state.abort_requested = False
        state.user_command = None
        state.action_event.clear()

        ts_folder = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + f"_{username}"
        job_dir = os.path.join(ARCHIVE_BASE_DIR, ts_folder)
        os.makedirs(job_dir, exist_ok=True)
        state.job_archive_dir = job_dir
        state.job_log_path = os.path.join(job_dir, "job_details.log")

        raw_path = os.path.join(job_dir, "original_input.pdf")
        stamped_path = os.path.join(job_dir, "processed_output.pdf")
        f.save(raw_path)

        state.pdf_path = raw_path
        state.stamped_pdf_path = stamped_path
        state.current_page = 0
        state.total_pages = 0
        state.status = "PRINTING"
        state.message = tr_msg("job_started", lang, name=f.filename)

        log_event(f"PDF kaydedildi ({raw_path}). Arka plan baskı işçisi (worker) başlatılıyor...", job_log_path=state.job_log_path)

        threading.Thread(target=print_job_worker, daemon=True).start()
        return jsonify({"message": tr_msg("job_started", lang, name=f.filename)})

    except Exception as e:
        err_trace = traceback.format_exc()
        state.status = "IDLE"
        state.message = tr_msg("start_err", lang, err=e)
        log_event(f"/api/start Hatası: {e}\n{err_trace}", level="ERROR")
        return jsonify({"message": tr_msg("server_err", lang, err=e)}), 500

@app.route("/api/action", methods=["POST"])
def api_action():
    lang = get_req_lang()
    data = request.json or {}
    action = data.get("action")
    state.user_command = action
    if action == "ABORT":
        state.abort_requested = True
        cancel_all_cups_jobs(state.printer_name)
        state.status = "IDLE"
        state.message = tr_msg("job_aborted", lang)
        log_event("Kullanıcı ACİL İPTAL (ABORT) butonuna bastı! CUPS kuyruğu temizlendi.", level="WARNING", job_log_path=state.job_log_path)
    state.action_event.set()
    return jsonify({"ok": True})

def gen_mjpeg():
    while True:
        frame = state.annotated_frame if state.annotated_frame is not None else verifier._get_zoomed_frame()
        if frame is not None:
            ret, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
        time.sleep(0.15)

@app.route("/video_feed")
def video_feed():
    return Response(gen_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    host = os.environ.get("PRINTGUARD_HOST", "0.0.0.0")
    port = int(os.environ.get("PRINTGUARD_PORT", "5000"))
    app.run(host=host, port=port, threaded=True)
