---
title: MAGI System
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
---

# 🤖 MAGI System - Decision Support AI

エヴァンゲリオンのMAGIシステムを再現した、AI意思決定支援システムです。

## 🌟 特徴

- **3つの異なる視点**: CASPER(科学者)、BALTHASAR(母)、MELCHIOR(女性)
- **多角的分析**: 科学的・倫理的・実用的観点から提案を評価
- **自動判定**: 3つのうち2つ以上が賛成で承認

## 🚀 セットアップ

### 環境変数の設定

Spaceの設定で以下のシークレットを追加してください:

```
GEMINI_API_KEY=your_gemini_api_key_here
```

Gemini API Keyは [Google AI Studio](https://aistudio.google.com/app/apikey) で取得できます。

## 📡 API使用方法

### Python

```python
import requests

response = requests.post(
    "https://your-space-url.hf.space/api/predict",
    json={"data": ["新プロジェクトに予算を投じるべきか", None]}
)
print(response.json())
```

### JavaScript

```javascript
fetch("https://your-space-url.hf.space/api/predict", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({data: ["新プロジェクトに予算を投じるべきか", null]})
})
.then(res => res.json())
.then(data => console.log(data));
```

## 🎯 各MAGIの判定基準

- **CASPER-1**: 論理的思考、科学的根拠、データの正確性
- **BALTHASAR-2**: 人間性、倫理、安全性、感情への配慮
- **MELCHIOR-3**: 実用性、社会的影響、現実的な実現可能性

## 💡 使用例

### 会議での意思決定
- 予算配分の決定
- 新規プロジェクトの承認/却下
- ポリシー変更の判断

### ビジネス判断
- 投資判断
- 採用決定
- 戦略的方向性の決定

## 🔧 トラブルシューティング

### エラー: "No module named 'google.generativeai'"
- `requirements.txt` が正しくアップロードされているか確認

### エラー: "API Key not found"
- SpaceのSettingsでGEMINI_API_KEYが設定されているか確認

### 応答が返ってこない
- Gemini APIのクォータ制限を確認
- APIキーが有効か確認

## 📄 ライセンス

MIT License

## 🙏 クレジット

- Powered by Google Gemini API
- Inspired by NERV MAGI System from Evangelion