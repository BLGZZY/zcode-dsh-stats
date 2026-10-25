#!/bin/zsh
set -e
cd -- "${0:A:h}"
PYTHON="/opt/homebrew/bin/python3"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python3"; fi
"$PYTHON" setup_auto.py enable
print '\n安装并启用更新后自动恢复。请在后台任务结束后，完全退出并重新打开官方 ZCode。'
read -r '?按回车关闭此窗口…'
