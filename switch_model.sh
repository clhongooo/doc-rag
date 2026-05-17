#!/bin/bash
# 切换 MLX 模型: ./switch_model.sh 8b 或 ./switch_model.sh 27b

HERMES_CONFIG="/Users/clhongooo/.hermes/config.yaml"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.local.qwen-mlx-server.plist"

case "${1:-}" in
  8b)  MODEL_PATH="/Users/clhongooo/Documents/models/Qwen3-8B-MLX-6bit/Qwen/Qwen3-8B-MLX-6bit" ;;
  27b) MODEL_PATH="/Users/clhongooo/Documents/models/Qwen3.6-27B-MLX-4bit" ;;
  *)
    echo "用法: ./switch_model.sh <8b|27b>"
    exit 1
    ;;
esac

echo "==> 切换到 ${1}: $MODEL_PATH"

# 1. 停服务
launchctl unload "$LAUNCHD_PLIST" 2>/dev/null
sleep 2
pkill -f "mlx_lm server" 2>/dev/null
sleep 1

# 2. 更新 plist (用 python，避免 sed 问题)
python3 -c "
import plistlib
with open('$LAUNCHD_PLIST', 'rb') as f:
    plist = plistlib.load(f)
args = plist['ProgramArguments']
for i, arg in enumerate(args):
    if arg == '--model':
        args[i+1] = '$MODEL_PATH'
        break
with open('$LAUNCHD_PLIST', 'wb') as f:
    plistlib.dump(plist, f)
print('  plist: OK')
"

# 3. 更新 config
sed -i '' "s|^  default: .*|  default: $MODEL_PATH|" "$HERMES_CONFIG"
echo "  config: OK"

# 4. 启动
launchctl load "$LAUNCHD_PLIST"
sleep 8

# 5. 验证
if curl -s http://127.0.0.1:8080/v1/models 2>/dev/null | grep -q "model"; then
  echo "==> ✓ 切换成功! 运行 /model 确认"
else
  echo "==> ⚠ 启动中，等几秒再试"
fi
