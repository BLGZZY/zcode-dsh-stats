#!/bin/zsh
set -e
cd -- "${0:A:h}"
PYTHON="/opt/homebrew/bin/python3"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python3"; fi
"$PYTHON" install.py remove
print '\n加载入口已移除。完全退出并重新打开 ZCode 后生效。'
read -r '?按回车关闭此窗口…'
