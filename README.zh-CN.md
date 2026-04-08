# chrome-apple-session-only-skill

English README: [README.md](README.md)

这是一个给 Codex 用的 Chrome Apple 登录清理 skill。目标不是永久禁掉 Apple，而是把 `apple.com` / `[*.]apple.com` / `appleid.apple.com` 设成当前会话可用、Chrome 全部关闭后自动清掉站点数据的 `session_only` 模式。

## 覆盖问题

- Chrome 里的 Apple 登录被旧 cookie 或旧站点数据污染
- 想先审计当前 profile，再决定是否真正修改
- 想在 Ubuntu 和 macOS 上都走同一套 Google Chrome workflow

## 当前状态

- Ubuntu 路径已实机验证
- macOS 已在真实 Mac 上完成 `audit -> apply --dry-run -> apply` 实机验证，验证日期为 2026-04-09
- 本次 macOS 验证使用 Google Chrome 146.0.7680.178，单一 `Default` profile，并成功创建备份、写入 `5/5` 条 Apple `session_only` 规则、将 Apple cookie 从 `6` 条降到 `0`
- 默认只覆盖 `apple.com` 家族，不包含 `icloud.com`
- Chrome 重启后的交互式 Apple 登录是否完全符合你的账户流，仍需要用户自己再做一次人工确认

## 主要内容

- `chrome-apple-session-only-skill/`: 可安装的 skill 包
- `chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py`: 审计/应用脚本
- `tests/test_chrome_apple_session_only.py`: 标准库单元测试
