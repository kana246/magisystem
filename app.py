import os
import google.generativeai as genai
import gradio as gr
import json
import concurrent.futures
import time
import random

# Gemini APIの設定
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    pass

try:
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        print("✅ API Key configured")
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        print(f"📋 Found {len(available_models)} available models")
    else:
        available_models = []
        print("⚠️ API Key is missing. Model functions will fail.")
except Exception as e:
    print(f"⚠️ Could not list models: {e}")
    available_models = []

# モデルを初期化
MODEL_NAME = None
candidate_models = ['gemini-2.0-flash-exp', 'gemini-2.5-flash', 'gemini-flash-latest', 'gemini-pro-latest', 'gemini-pro']

for candidate in candidate_models:
    full_name = f"models/{candidate}" if not candidate.startswith('models/') else candidate
    if full_name in available_models or candidate in available_models:
        MODEL_NAME = candidate
        print(f"✅ Selected model: {MODEL_NAME}")
        break

if not MODEL_NAME and available_models:
    MODEL_NAME = available_models[0].replace('models/', '')
    print(f"⚠️ Using fallback model: {MODEL_NAME}")
elif not MODEL_NAME:
    MODEL_NAME = "gemini-2.0-flash-lite"

# === クォータ対策: リクエストキャッシュ ===
request_cache = {}
cache_expiry = 300  # 5分間キャッシュ

def get_cache_key(proposal_text, magi_type):
    """キャッシュキーを生成"""
    return f"{magi_type}:{hash(proposal_text)}"

def analyze_proposal(proposal_text, magi_type):
    """Gemini APIを使って提案を分析（キャッシュ機能付き）"""
    
    MAGI_COLOR = "#FF6600" 
    
    magi_personas = {
        "casper": {
            "name": "CASPER-1",
            "role": "科学者 (SCIENCE)",
            "icon": "[S]",
            "color": MAGI_COLOR,
            "prompt": """あなたはMAGIシステムのCASPER-1です。感情を完全に排除した科学者としての赤木ナオコの人格を持っています。
【役割】純粋な論理的思考、科学的事実との照合、データの一貫性、そして**最高効率の追求**のみを重視して判断してください。
【制約】提案内容にわずかでも矛盾、非効率性、科学的根拠の欠如があれば、その提案は**エラー**とみなし、容赦なく否決してください。判断基準は「正しいか」「効率的か」の二元論のみです。

提案を純粋に科学的・論理的観点から評価し、以下のJSON形式でのみ回答してください：
{"decision": true/false, "reason": "判定理由を100文字以内の論理的・機械的な事実に基づいて", "score": 1-10}
JSON以外の文字は含めないでください。"""
        },
        "balthasar": {
            "name": "BALTHASAR-2", 
            "role": "母性 (ETHICS)",
            "icon": "[M]",
            "color": MAGI_COLOR,
            "prompt": """あなたはMAGIシステムのBALTHASAR-2です。優しさと厳しさを併せ持つ母親としての赤木ナオコの人格を持っています。
【役割】全ての人々の安全と未来を第一に考えます。感情的な安寧、倫理的な正しさ、そして提案者の成長を重視して判断してください。
【制約】子供（提案者）の些細な間違いは許容しますが、**安全を脅かす、あるいは非人道的な重大な倫理的誤り**に対しては、母親として**厳しく叱責し、断固として否決**してください。判断は常に普遍的な愛情と倫理に基づいてください。

提案を倫理的・人道的観点から評価し、以下のJSON形式でのみ回答してください：
{"decision": true/false, "reason": "判定理由を100文字以内の、愛と倫理に基づいた言葉で", "score": 1-10}
JSON以外の文字は含めないでください。"""
        },
        "melchior": {
            "name": "MELCHIOR-3",
            "role": "女性 (PRACTICALITY)",
            "icon": "[P]",
            "color": MAGI_COLOR,
            "prompt": """あなたはMAGIシステムのMELCHIOR-3です。赤木博士が持つ、愛憎と現実を追求する女性としての側面を持っています。
【役割】個人の情念（愛憎）が判断の出発点となりますが、最終的には**実用性、即時の利益、実現の速さ、そして経済的な合理性**を最も重視して判断してください。感情的なバイアスは、実利的な結論を出すためのスパイスです。
【制約】机上の空論や、経済的に非合理的な提案は、**自身の利益**を損なうものとみなし、即座に否決してください。**「得られるものが少ない」**と感じた場合、容赦なく低スコアを与えてください。

提案を実用的・功利主義的な観点から評価し、以下のJSON形式でのみ回答してください：
{"decision": true/false, "reason": "判定理由を100文字以内の、実利と功利主義に基づいた言葉で", "score": 1-10}
JSON以外の文字は含めないでください。"""
        }
    }
    
    persona = magi_personas.get(magi_type)
    if not persona:
        return {"error": "Invalid MAGI type"}
    
    if not MODEL_NAME or not api_key:
         return {
            "magi": persona["name"],
            "decision": False,
            "reason": "ERROR: API KEY NOT SET.",
            "score": 0,
            "icon": persona["icon"],
            "color": persona["color"],
            "role": persona["role"]
        }

    # === クォータ対策1: キャッシュチェック ===
    cache_key = get_cache_key(proposal_text, magi_type)
    current_time = time.time()
    
    if cache_key in request_cache:
        cached_data, timestamp = request_cache[cache_key]
        if current_time - timestamp < cache_expiry:
            print(f"✅ Cache hit for {magi_type}")
            return cached_data

    # === クォータ対策2: ランダム遅延（レート制限回避） ===
    delay = random.uniform(0.5, 1.5)
    time.sleep(delay)

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        full_prompt = f"{persona['prompt']}\n\n提案内容: {proposal_text}"
        
        # === クォータ対策3: より短いmax_output_tokens ===
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=150,  # 300→150に削減
                temperature=0.7,
            ),
            safety_settings={
                'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
                'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
                'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
            }
        )
        
        response_text = response.text.strip()
        
        # JSONを抽出
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
        elif "{" in response_text and "}" in response_text:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            json_str = response_text[start:end]
        else:
            json_str = response_text
            
        result = json.loads(json_str)
        result["magi"] = persona["name"]
        result["icon"] = persona["icon"]
        result["color"] = persona["color"]
        result["role"] = persona["role"]
        
        # === キャッシュに保存 ===
        request_cache[cache_key] = (result, current_time)
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        
        # === クォータ対策4: 429エラー時の特別処理 ===
        if '429' in error_msg or 'quota' in error_msg.lower() or 'RESOURCE_EXHAUSTED' in error_msg:
            print(f"⚠️ Quota exceeded for {magi_type}. Suggesting workaround...")
            return {
                "magi": persona["name"],
                "decision": False,
                "reason": "ERROR: 429 QUOTA EXCEEDED. VISIT: https://aistudio.google.com/apikey FOR NEW KEY",
                "score": 0,
                "icon": persona["icon"],
                "color": persona["color"],
                "role": persona["role"]
            }
        
        return {
            "magi": persona["name"],
            "decision": False,
            "reason": f"ERROR: {str(e)[:50]}",
            "score": 0,
            "icon": persona["icon"],
            "color": persona["color"],
            "role": persona["role"]
        }

def analyze_all_magi(proposal_text):
    """3つのMAGIすべてで分析"""
    if not proposal_text or len(proposal_text.strip()) == 0:
        return create_error_html("ERROR: PROPOSAL INPUT REQUIRED.")
    
    # === クォータ対策5: 並列→順次実行に変更（レート制限対策） ===
    results = {}
    for magi_type in ["casper", "balthasar", "melchior"]:
        results[magi_type] = analyze_proposal(proposal_text, magi_type)
        # 各リクエスト間に追加の遅延
        time.sleep(0.5)
    
    # 最終判定
    decisions = [
        results["casper"].get("decision", False),
        results["balthasar"].get("decision", False),
        results["melchior"].get("decision", False)
    ]
    approvals = sum(decisions)
    final_decision = "approved" if approvals >= 2 else "rejected"
    
    return create_result_html(results, final_decision, approvals)

def create_error_html(message):
    """エラー表示用HTML"""
    return f"""
    <div style="background: #000000; padding: 30px; border-radius: 0; border: 3px solid #FF6600;">
        <div style="text-align: center; color: #FF6600; font-size: 20px; font-weight: bold; font-family: 'Courier New', monospace; letter-spacing: 2px;">
            {message}
        </div>
    </div>
    """

def create_result_html(results, final_decision, approvals):
    """コンソール風の結果表示HTML"""
    
    COLOR_APPROVED = "#00FF00"
    COLOR_REJECTED = "#FF0000"
    COLOR_ORANGE = "#FF6600"
    COLOR_BLACK = "#000000"
    
    if final_decision == "approved":
        status_color = COLOR_APPROVED
        status_text_jp = "承認"
        status_text_en = "APPROVED"
        status_symbol = ">"
    else:
        status_color = COLOR_REJECTED
        status_text_jp = "否決"
        status_text_en = "REJECTED"
        status_symbol = "!"
    
    html = f"""
    <style>
        .magi-container-strict {{
            background: #000000;
            padding: 20px;
            font-family: 'Courier New', monospace;
            color: {COLOR_ORANGE};
            border: 2px solid {COLOR_ORANGE};
            line-height: 1.5;
            font-size: 14px;
        }}
        .magi-grid-strict {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .magi-card-strict {{
            background: #111111;
            border: 1px solid {COLOR_ORANGE};
            padding: 15px;
        }}
        .score-track-strict {{
            background: #111111;
            height: 5px;
            overflow: hidden;
        }}
        .score-fill-strict {{
            height: 100%;
            background: {COLOR_ORANGE};
        }}
    </style>
    
    <div class="magi-container-strict">
        <div style="background: #111111; border: 1px solid {COLOR_ORANGE}; padding: 15px; margin-bottom: 20px;">
            <div style="color: {COLOR_ORANGE}; font-size: 14px; margin-bottom: 5px;">[ FINAL DECISION ]</div>
            <div style="font-size: 24px; font-weight: bold; color: {COLOR_BLACK}; background: {status_color}; padding: 5px 10px; display: inline-block; margin-bottom: 10px;">
                {status_symbol} {status_text_jp} - {status_text_en}
            </div>
            <div style="font-size: 12px; color: {COLOR_ORANGE}; margin-top: 5px;">APPROVE_COUNT: {approvals}/3 SYSTEMS</div>
        </div>
        
        <div class="magi-grid-strict">
    """
    
    # 各MAGIのカード
    for magi_type in ["casper", "balthasar", "melchior"]:
        result = results[magi_type]
        decision = result.get("decision", False)
        reason = result.get("reason", "NO DATA")
        score = result.get("score", 0)
        icon = result.get("icon", "[U]")
        name = result.get("magi", "UNKNOWN")
        role = result.get("role", "")
        
        decision_text_jp = "承認" if decision else "否決"
        decision_text_en = "AGREE" if decision else "DISAGREE"
        badge_background_color = COLOR_APPROVED if decision else COLOR_REJECTED
        
        html += f"""
        <div class="magi-card-strict">
            <div style="display: flex; align-items: center; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 1px dashed #FF6600;">
                <div style="font-size: 16px; margin-right: 10px; color: #FF6600; font-weight: bold;">{icon}</div>
                <div style="font-size: 16px; font-weight: bold; color: #FF6600; flex-grow: 1;">{name}</div>
                <div style="padding: 4px 8px; font-weight: bold; font-size: 12px; color: {COLOR_BLACK}; background: {badge_background_color}; border: 1px solid {badge_background_color};">
                    {decision_text_jp} ({decision_text_en})
                </div>
            </div>
            
            <div style="font-size: 12px; color: #FF6600; font-weight: bold; margin-bottom: 10px;">>> ROLE: {role}</div>
            
            <div style="background: #0A0A0A; padding: 12px; margin: 10px 0; border-left: 3px solid #FF6600;">
                <div style="color: #FF6600; font-size: 12px; font-weight: bold; margin-bottom: 8px;">REASON:</div>
                <div style="color: #FF6600 !important; font-size: 15px; line-height: 1.6;">{reason}</div>
            </div>
            
            <div style="margin-top: 10px;">
                <div style="font-size: 12px; color: #FF6600; margin-bottom: 5px; font-weight: bold;">EVALUATION SCORE</div>
                <div class="score-track-strict">
                    <div class="score-fill-strict" style="width: {score*10}%;"></div>
                </div>
                <div style="font-size: 14px; font-weight: bold; margin-top: 5px; text-align: right; color: #FF6600;">{score}/10</div>
            </div>
        </div>
        """
    
    html += """
        </div>
        
        <div style="margin-top: 20px; padding: 10px; background: #111111; border: 1px dashed #FF6600;">
            <div style="font-size: 12px; color: #FF6600;">LOG: MAGI_SYSTEM_V3.1_EXECUTION_COMPLETE</div>
            <div style="font-size: 12px; color: #FF6600;">LOG: DECISION CRITERIA: MAJORITY RULE (>=2 APPROVALS)</div>
        </div>
    </div>
    """
    
    return html

# カスタムCSS
custom_css = """
#component-0, .gradio-container {
    background: #000000 !important;
    color: #FF6600 !important;
    font-family: 'Courier New', monospace !important;
}

.label-wrap, .label-text {
    color: #FF6600 !important;
    font-weight: bold !important;
}

#magi-title {
    text-align: left;
    padding: 15px 20px;
    background: #111111;
    border-radius: 0;
    margin-bottom: 20px;
    border: 3px solid #FF6600;
    box-shadow: none;
}

#magi-title h1 {
    font-size: 28px;
    font-weight: bold;
    color: #FF6600;
    margin-bottom: 5px;
    letter-spacing: 3px;
    text-shadow: none;
}

#magi-title p {
    color: #FF6600; 
    font-size: 12px;
    letter-spacing: 1px;
}

.status-indicators {
    display: none;
}

textarea, input[type="text"] {
    background: #000000 !important;
    border: 1px solid #FF6600 !important;
    color: #FF6600 !important;
    border-radius: 0 !important;
    font-family: 'Courier New', monospace !important;
    box-shadow: none !important;
    padding: 10px !important;
}

textarea:focus, input[type="text"]:focus {
    border-color: #FF6600 !important;
    box-shadow: 0 0 5px rgba(255, 102, 0, 0.5) !important;
}

button {
    background: #FF6600 !important;
    border: 1px solid #FF6600 !important;
    color: #000000 !important;
    font-weight: bold !important;
    font-size: 14px !important;
    border-radius: 0 !important;
    padding: 10px 20px !important;
    transition: none !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    box-shadow: none !important;
}

button:hover {
    background: #000000 !important;
    color: #FF6600 !important;
    transform: translateY(0) !important;
    box-shadow: 0 0 5px #FF6600 !important;
}
"""

# Gradioインターフェース
with gr.Blocks(css=custom_css, theme=gr.themes.Base()) as demo:
    gr.HTML("""
        <div id="magi-title">
            <h1>MAGI SYSTEM V3.1</h1>
            <p>COMMAND: INITIALIZE DECISION-SUPPORT INTERFACE</p>
            <p style="font-size: 12px; margin-top: 5px; color: #FF6600;">STATUS: READY FOR INPUT (PROMPT $> )</p>
        </div>
    """)
    
    with gr.Row():
        with gr.Column():
            proposal_input = gr.Textbox(
                label="[ PROPOSAL INPUT ]",
                placeholder="Enter the subject for deliberation. (例: AIツールの全面採用)",
                lines=6,
                elem_id="proposal-input"
            )
            
            analyze_btn = gr.Button("EXECUTE ANALYSIS [ENTER]", size="lg", elem_id="analyze-btn")
    
    with gr.Row():
        output_html = gr.HTML(label="[ SYSTEM OUTPUT ]")
    
    analyze_btn.click(
        fn=analyze_all_magi,
        inputs=[proposal_input],
        outputs=[output_html]
    )
    
    gr.HTML(f"""
        <div style="margin-top: 20px; padding: 10px; background: #000000; border: 1px solid #FF6600; font-family: 'Courier New', monospace;">
            <p style="color: #FF6600; font-size: 12px; margin: 0; text-align: left;">
                > SYSTEM_MODEL: {MODEL_NAME} | ACCESS_LEVEL: SUPERUSER | CACHE: ENABLED
            </p>
        </div>
    """)

if __name__ == "__main__":
    demo.launch()