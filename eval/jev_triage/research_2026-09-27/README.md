# Jev の実装の調べ(2026-09-27)

Grok(xAI の Grok CLI 1.0.3、モデル grok-4.7、Web 検索と X の検索)に4つの問いを投げた記録です。
`grok -p "<依頼>" --output-format json --reasoning-effort high --disallowed-tools "search_replace,write_file,run_terminal_command,todo_write"`
(ファイルの書き換えとコマンドは使わせていない)。4問で約1.37ドル。

| 問い | 依頼 | Grok の答え |
|---|---|---|
| 1. 実装のパターン(どこに置くか、LangGraph、閾値、監視) | q1_依頼.txt | r1_Grokの答え.md |
| 2. API とモデルの事実(版・形・制限・料金・保持) | q2_依頼.txt | r2_Grokの答え.md |
| 3. X とブログで実践者が言っていること(良い点・失敗・コツ) | q3_依頼.txt | r3_Grokの答え.md |
| 4. この用途(日本語の不適合報告書)での改善の勧め | q4_依頼.txt | r4_Grokの答え.md |

**注意**:Grok の答えは確かめる前のものです。出典の URL や数字には、開けなかったもの・確かめていないものがあります。
アプリに入れた改善の根拠は、公式ドキュメント(TypeSafe・OpenRouter)などで確かめたものだけです。
確かめた内容と、入れたこと・測った結果は `docs/11_報告書トリアージ_JevとLangGraph.md` の 9 章にあります。
