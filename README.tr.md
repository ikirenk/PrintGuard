# 🖨️ PrintGuard

[🇬🇧 English](README.md) | **🇹🇷 Türkçe**

**PrintGuard**, CUPS tabanlı ağ/USB yazıcıları bir web arayüzü üzerinden yöneten, her basılan sayfayı **USB kamera + ArUco 4x4 + CMYK + ikili (binary) sayfa kodu** ile optik olarak doğrulayan, çift taraflı (duplex) parti baskısını kolaylaştıran ve kullanıcı bazlı sayfa sayacı tutan hafif bir Flask sunucusudur.

> **🐧 DietPi Üzerinde Test Edilmiştir:** Bu proje **DietPi** (Debian tabanlı hafif Linux dağıtımı) üzerinde CUPS ve USB kamera ile test edilmiştir. Raspberry Pi, Orange Pi ve benzeri tek kartlı bilgisayarlarda (SBC) düşük kaynak tüketimiyle 7/24 çalışacak şekilde tasarlanmıştır.

---

## ✨ Özellikler

- **Web Kontrol Paneli:** PDF yükleme, yazıcı seçimi, siyah-beyaz/renkli mod, sayfa numarası ekleme ve canlı kamera yayını (`/video_feed`).
- **Optik Baskı Doğrulama:** Sayfanın üstüne veya altına eklenen ArUco (900/901) işaretçileri, CMYK mürekkep yamaları ve 15-bit sayfa numarası şeridi kamera ile okunarak baskının hatasız çıktığı doğrulanır; mürekkep bitmesi veya kağıt sıkışmasında otomatik duraklar.
- **Akıllı Çift Taraflı (Duplex) Parti Yönetimi:** Çift taraflı yazıcısı olmayan cihazlarda ters çiftler (`10,8,6,4,2 -> 1,3,5,7,9`) veya düz çiftler sıralamasıyla adım adım yönlendirme yapar.
- **Kullanıcı Yönetimi ve Sayfa Sayacı:** `users.json` dosyası ve web panelindeki **Kullanıcı Yönetimi** kartı üzerinden kullanıcı ekleme, şifre değiştirme ve aylık sayfa sayacı takibi/sıfırlama.
- **Tailscale Uyumlu:** Varsayılan olarak `0.0.0.0:5000` adresini dinler; ek yönlendirme (port forwarding) olmadan Tailscale ağı üzerinden güvenle erişilebilir.

---

## 🌐 Tailscale ile Kullanım

PrintGuard varsayılan olarak tüm ağ arayüzlerinde (`0.0.0.0:5000`) çalışır ve `tailscaled.service` ile uyumludur.

1. Cihazınızda Tailscale kurulu ve aktifse, aynı Tailnet'teki herhangi bir telefon veya bilgisayardan şu adresle erişebilirsiniz:
   ```text
   http://<tailscale-ip>:5000
   ```
   veya MagicDNS açıksa:
   ```text
   http://<cihaz-adi>:5000
   ```
2. İsteğe bağlı olarak Tailscale üzerinden HTTPS ile yayınlamak için:
   ```bash
   tailscale serve --bg 5000
   ```

---

## 🚀 Kurulum (DietPi / Debian)

### 1. Sistem Paketlerini Kurun
```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv cups libgl1 libglib2.0-0
```
*(İsteğe bağlı: ARM cihazlarda OpenCV derlemesini hızlandırmak için `sudo apt install -y python3-opencv` kullanabilirsiniz.)*

### 2. Projeyi `/opt/printguard` Dizinine Alın
```bash
sudo mkdir -p /opt/printguard
sudo git clone <REPO_URL> /opt/printguard
cd /opt/printguard
```

### 3. Sanal Ortam (venv) ve Bağımlılıkları Kurun
```bash
sudo python3 -m venv /opt/printguard/venv
sudo /opt/printguard/venv/bin/pip install --upgrade pip
sudo /opt/printguard/venv/bin/pip install -r /opt/printguard/requirements.txt
```

### 4. Kullanıcı Yapılandırması (`users.json`)
İsterseniz örnek dosyayı kopyalayıp düzenleyebilirsiniz:
```bash
sudo cp /opt/printguard/users.example.json /opt/printguard/users.json
sudo nano /opt/printguard/users.json
```
Eğer `users.json` oluşturmazsanız, ilk çalıştırmada otomatik olarak varsayılan yönetici hesabı oluşturulur:
- **Kullanıcı adı:** `admin`
- **Şifre:** `admin`

> ⚠️ **Güvenlik Notu:** İlk girişten sonra web panelindeki **Kullanıcı Yönetimi -> Şifre Değiştir** bölümünden `admin` şifresini mutlaka değiştirin. `users.json` dosyası `.gitignore` içinde hariç tutulmuştur.

---

## ⚙️ Sistem Servisi (systemd) Olarak Kurulum

Projeyle birlikte gelen [`printguard.service`](printguard.service) dosyasını kullanarak PrintGuard'ı sistem açılışında otomatik başlayan bir servis haline getirebilirsiniz:

```bash
# Servis dosyasını systemd dizinine kopyalayın
sudo cp /opt/printguard/printguard.service /etc/systemd/system/printguard.service

# systemd yapılandırmasını yenileyin
sudo systemctl daemon-reload

# Servisi başlangıca ekleyin ve hemen başlatın
sudo systemctl enable --now printguard
```

### Faydalı Servis Komutları
```bash
# Servis durumunu kontrol et
sudo systemctl status printguard

# Canlı logları izle
sudo journalctl -u printguard -f

# Servisi yeniden başlat
sudo systemctl restart printguard

# Servisi durdur
sudo systemctl stop printguard
```

---

## 🔧 Ortam Değişkenleri (Opsiyonel)

`printguard.service` içinde veya terminalden aşağıdaki ortam değişkenlerini özelleştirebilirsiniz:

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `PRINTGUARD_HOST` | `0.0.0.0` | Dinlenecek IP adresi |
| `PRINTGUARD_PORT` | `5000` | Web arayüzü portu |
| `PRINTGUARD_LANG` | `en` | Varsayılan arayüz ve sunucu dili (`en` veya `tr`) |
| `PRINTGUARD_CAMERA_INDEX` | `0` | OpenCV kamera indeksi (`/dev/video0`) |
| `PRINTGUARD_WORKSPACE` | `/opt/printguard/printguard_workspace` | Arşiv, sayaç ve log dizini |
| `PRINTGUARD_USERS_FILE` | `/opt/printguard/users.json` | Kullanıcı yapılandırma dosyası |
| `PRINTGUARD_SOUND_FILE` | `/opt/printguard/a.mp3` | Baskı bitince çalınacak ses dosyası (varsa) |

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
