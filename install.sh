#!/bin/bash
# Script cài đặt/gỡ cài đặt hcmueFetch vào hệ thống

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_NAME="hcmueFetch"
DESKTOP_NAME="hcmue-fetch.desktop"
BIN_PATH="$HOME/.local/bin/$BIN_NAME"
APPS_DIR="$HOME/.local/share/applications"
DESKTOP_PATH="$APPS_DIR/$DESKTOP_NAME"

# Nếu truyền tham số 'uninstall' thì tiến hành gỡ
if [ "$1" == "uninstall" ]; then
    rm -f "$BIN_PATH"
    rm -f "$DESKTOP_PATH"
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$APPS_DIR" 2>/dev/null
    fi
    echo "✅ Đã gỡ cài đặt hcmueFetch khỏi hệ thống."
    exit 0
fi

# Tạo các thư mục nếu chưa có
mkdir -p "$HOME/.local/bin"
mkdir -p "$APPS_DIR"

# 1. Tạo executable script (bin)
cat <<EOF > "$BIN_PATH"
#!/bin/bash
cd "$APP_DIR"
./venv/bin/python main.py "\$@"
EOF
chmod +x "$BIN_PATH"
echo "Đã tạo lệnh chạy tại: $BIN_PATH"

# 2. Tạo file .desktop để hiện trong App Launcher
cat <<EOF > "$DESKTOP_PATH"
[Desktop Entry]
Type=Application
Name=HCMUE Fetch
Comment=Thu thập tin tức trường HCMUE
Exec=$BIN_PATH
Icon=utilities-terminal
Terminal=false
Categories=Utility;Education;
StartupNotify=true
EOF
echo "Đã tạo mục menu app tại: $DESKTOP_PATH"

# Cập nhật database desktop (nếu có update-desktop-database)
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APPS_DIR" 2>/dev/null
fi

echo ""
echo "✅ Cài đặt hoàn tất!"
echo "Bây giờ bạn có thể:"
echo "  1. Gõ 'hcmueFetch' trong terminal để mở GUI."
echo "  2. Gõ 'hcmueFetch run --count 10' để chạy CLI."
echo "  3. Mở menu app (Super key) và tìm 'HCMUE Fetch' để mở GUI."
echo ""
echo "Để gỡ cài đặt, chạy lệnh: ./install.sh uninstall"
