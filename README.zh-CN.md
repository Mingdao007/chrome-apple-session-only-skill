# chrome-apple-session-only-skill

English README: [README.md](README.md)

这是一个给 Codex 用的 Google Chrome 会话清理 skill，专门用于 Apple 登录面的 `session_only` 清理。

它的目标不是永久禁掉站点，而是把目标站点改成当前会话可用、Chrome 全部关闭后自动清掉站点状态的 `session_only` 模式。

## 覆盖问题

- Chrome 里的 Apple 登录被旧 cookie 或旧站点数据污染
- 想先审计当前 profile，再决定是否真正修改
- 想在 Ubuntu 和 macOS 上都走同一套 Google Chrome workflow

## 支持范围

支持范围：

- `apple`
- `apple.com`
- `[*.]apple.com`
- `appleid.apple.com`

脚本不会静默扩展到这个 Apple 域名族之外。

## 当前状态

- Ubuntu 路径已实机验证
- macOS Apple target 已在真实 Mac 上完成 `audit -> apply --dry-run -> apply` 实机验证，验证日期为 2026-04-09
- 本次 macOS 验证使用 Google Chrome 146.0.7680.178，单一 `Default` profile
- Apple 路径已成功创建备份、写入 `5/5` 条 Apple `session_only` 规则、将 Apple cookie 从 `6` 条降到 `0`
- Chrome 重启后的交互式 Apple 登录是否完全符合你的账户流，仍需要用户自己再做一次人工确认

## 主要内容

- `chrome-apple-session-only-skill/`: 可安装的 skill 包
- `chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py`: 审计 / 应用脚本
- `chrome-apple-session-only-skill/references/platform-paths-and-safety.md`: 支持路径、target 范围与安全边界
- `tests/test_chrome_apple_session_only.py`: 标准库单元测试

## 安装

1. 把 `chrome-apple-session-only-skill/` 复制到 `${CODEX_HOME:-$HOME/.codex}/skills/`。
2. 重启 Codex，或者刷新本地 skills。
3. 通过 `$chrome-apple-session-only-skill` 调用这个 skill。

## 脚本用法

审计默认 Apple target：

```bash
python3 chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py audit
```

先预览 Apple 清理，不写入：

```bash
python3 chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py apply --dry-run
```

对指定 profile 做显式 Apple 审计：

```bash
python3 chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py audit --target apple --profile "Profile 2"
```

默认情况下，脚本会按操作系统解析 Chrome 根目录，只支持 `apple` 这一个 target，并从 `Local State` 里读取最近使用的 profile；如果拿不到，就回退到 `Default`。显式传 `--target apple` 仍然有效，但不是必须的。

## 安全模型

- `audit` 是只读的。
- `apply` 在检测到 Google Chrome 仍在运行时会拒绝修改。
- `apply` 每次正式写入前都会为 `Preferences` 和 `Cookies` 创建带时间戳的备份。
- 备份文件名会带 target，例如 `backup.apple-session-only.*`。
- `--dry-run` 只展示计划变更，不会真的修改 profile。

## 行为摘要

- 把 Apple 对应的 cookie 规则写成 Chrome `Preferences` 里的 `session_only` 项。
- 从 `Cookies` SQLite 数据库里删除 Apple 域名族的旧 cookie 行。
- 从 `Preferences` 里删除 Apple 域名族的可直接定位站点状态，例如 `site_engagement`、`media_engagement`。
- 只在文件名里安全编码了目标 host 的情况下，删除可直接识别的 Apple origin storage artifact。
- 这不是永久封禁 Apple；目标是“下次启动更干净”，不是“让登录失效”。

## 隐私边界

这个仓库只包含可移植的 skill 逻辑、元数据和测试，不包含私有记忆文件、本地个人路径、账号数据或抓取出的浏览器状态。
