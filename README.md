# fuck

AI-first command fixer for your shell/terminal CLI (bash, zsh, fish) with streamed explanations and Markdown rendering.

<img width="898" height="323" alt="AI shell command fixer screenshot" src="https://github.com/user-attachments/assets/5b90cb3a-364c-4a72-ace2-4af872b6cbf2" />

## English

Install:

```bash
uv tool install fuck-cli
# or
pip install fuck-cli
```

Setup (recommended):

```bash
fuck setup
# or
uvx fuck --setup
```

Usage:

```bash
# after a failed command
fuck
```

AI config: run `fuck setup` or set env vars like `FUCK_AI_URL`,
`FUCK_AI_TOKEN`, `FUCK_AI_MODEL`, `FUCK_AI_STREAM`, `FUCK_AI_MODE`.

Disclaimer: always review the suggested command before executing it.

## 中文

安装：

```bash
uv tool install fuck-cli
# 或
pip install fuck-cli
```

初始化（推荐）：

```bash
fuck setup
# 或
uvx fuck --setup
```

使用：

```bash
# 命令失败后
fuck
```

AI 配置：运行 `fuck setup`，或设置环境变量如 `FUCK_AI_URL`、
`FUCK_AI_TOKEN`、`FUCK_AI_MODEL`、`FUCK_AI_STREAM`、`FUCK_AI_MODE`。

免责声明：请在执行前确认修复命令的安全性与正确性。

## 日本語

インストール：

```bash
uv tool install fuck-cli
# または
pip install fuck-cli
```

セットアップ（推奨）：

```bash
fuck setup
# または
uvx fuck --setup
```

使い方：

```bash
# 失敗したコマンドの後に
fuck
```

AI 設定：`fuck setup` を使うか、`FUCK_AI_URL`、`FUCK_AI_TOKEN`、
`FUCK_AI_MODEL`、`FUCK_AI_STREAM`、`FUCK_AI_MODE` などの環境変数を設定します。

免責事項：実行前に提案コマンドを必ず確認してください。
