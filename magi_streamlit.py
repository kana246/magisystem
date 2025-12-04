import os
import google.generativeai as genai
import streamlit as st
import json
import time
import random

# ページ設定
st.set_page_config(
    page_title="MAGI SYSTEM V3.1",
    page_icon="🔶",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# カスタムCSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&display=swap');
    
    * {
        font-family: 'Courier Prime', 'Courier New', monospace !important;
    }
    
    .stApp {
        background-color: #000000;
        color: #FF6600;
    }
    
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }
    
    h1, h2, h3, h4, h5, h6 {
        color: #FF6600 !important;
        letter-spacing: 2px;
    }
    
    .stTextArea textarea {
        background-color: #000000 !important;
        border: 1px solid #FF6600 !important;
        color: #FF6600 !important;
        border-radius: 0 !important;
    }
    
    .stTextArea textarea:focus {
        border-color: #FF6600 !important;
        box-shadow: 0 0 5px rgba(255, 102, 0, 0.5) !important;
    }
    
    .stButton button {
        background-color: #FF6600 !important;
        border: 1px solid #FF6600 !important;
        color: #000000 !important;
        font-weight: bold !important;
        border-radius: 0 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        width: 100%;
        padding: 0.75rem 1rem !important;
    }
    
    .stButton button:hover {
        background-color: #000000 !important;
        color: #FF6600 !important;
        box-shadow: 0 0 5px #FF6600 !important;
    }
    
    .title-box {
        background: #111111;
        border: 3px solid #FF6600;
        padding: 20px;
        margin-bottom: 30px;
    }
    
    .status-text {
        color: #FF6600;
        font-size: 12px;
        letter-spacing: 1px;
        margin: 5px 0;
    }
    
    div[data-testid="stMarkdownContainer"] p {
        color: #FF6600;
    }
    
    .stAlert {
        background-color: #111111;
        border: 1px solid #FF6600;
        color: #FF6600;
    }
</style>
""", unsafe_allow_html=True)

# セッション状態の初期化
if 'request_cache' not in st.session_state:
    st.session_state.request_cache = {}
if 'cache_expiry' not in st.session_state:
    st.session_state.cache_expiry = 300  # 5分
if 'request_count' not in st.session_state:
    st.session_state.request_count = 0
if 'last_request_time' not in st.session_state:
    st.session_state.last_request_time = None
if 'current_key_index' not in st.session_state:
    st.session_state.current_key_index = 0

# Gemini APIの設定
@st.cache_resource
def initialize_gemini():
    """Gemini APIを初期化（複数キー対応）"""
    # Streamlit Secretsから取得を試みる
    api_keys = []
    try:
        key_str = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
        if key_str:
            # カンマ区切りで複数キーをサポート
            api_keys = [k.strip() for k in key_str.split(",") if k.strip()]
    except:
        pass
    
    # 環境変数からも取得を試みる
    if not api_keys:
        key_str = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key_str:
            api_keys = [k.strip() for k in key_str.split(",") if k.strip()]
    
    if not api_keys:
        return [], [], "API Key not configured"
    
    try:
        # 最初のキーで初期化
        os.environ["GOOGLE_API_KEY"] = api_keys[0]
        genai.configure(api_key=api_keys[0])
        
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        
        candidate_models = [
            'gemini-2.0-flash-exp',      # 15 RPM, 1500 RPD - 最優先
            'gemini-flash-latest',        # 通常10-15 RPM
            'gemini-2.5-flash',          # 10 RPM, 250 RPD
            'gemini-pro-latest',
            'gemini-pro'                  # 避ける（5 RPM, 25 RPDのみ）
        ]
        
        model_name = None
        for candidate in candidate_models:
            full_name = f"models/{candidate}" if not candidate.startswith('models/') else candidate
            if full_name in available_models or candidate in available_models:
                model_name = candidate
                break
        
        if not model_name and available_models:
            model_name = available_models[0].replace('models/', '')
        elif not model_name:
            model_name = "gemini-2.0-flash-lite"
            
        return api_keys, available_models, model_name
    
    except Exception as e:
        return api_keys, [], f"Error: {str(e)}"

api_keys, available_models, MODEL_NAME = initialize_gemini()

def get_current_api_key():
    """現在のAPI Keyを取得（ローテーション対応）"""
    if not api_keys:
        return None
    return api_keys[st.session_state.current_key_index % len(api_keys)]

def rotate_api_key():
    """次のAPI Keyに切り替え"""
    if len(api_keys) > 1:
        st.session_state.current_key_index += 1
        new_key = get_current_api_key()
        genai.configure(api_key=new_key)
        return True
    return False

def get_cache_key(proposal_text, magi_type):
    """キャッシュキーを生成"""
    return f"{magi_type}:{hash(proposal_text)}"

def analyze_proposal(proposal_text, magi_type, max_retries=1):  # 3→1に削減
    """Gemini APIを使って提案を分析（リトライ機能付き）"""
    
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
【制約】子供(提案者)の些細な間違いは許容しますが、**安全を脅かす、あるいは非人道的な重大な倫理的誤り**に対しては、母親として**厳しく叱責し、断固として否決**してください。判断は常に普遍的な愛情と倫理に基づいてください。

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
【役割】個人の情念(愛憎)が判断の出発点となりますが、最終的には**実用性、即時の利益、実現の速さ、そして経済的な合理性**を最も重視して判断してください。感情的なバイアスは、実利的な結論を出すためのスパイスです。
【制約】机上の空論や、経済的に非合理的な提案は、**自身の利益**を損なうものとみなし、即座に否決してください。**「得られるものが少ない」**と感じた場合、容赦なく低スコアを与えてください。

提案を実用的・功利主義的な観点から評価し、以下のJSON形式でのみ回答してください：
{"decision": true/false, "reason": "判定理由を100文字以内の、実利と功利主義に基づいた言葉で", "score": 1-10}
JSON以外の文字は含めないでください。"""
        }
    }
    
    persona = magi_personas.get(magi_type)
    if not persona:
        return {"error": "Invalid MAGI type"}
    
    current_key = get_current_api_key()
    if not MODEL_NAME or not current_key:
        return {
            "magi": persona["name"],
            "decision": False,
            "reason": "ERROR: API KEY NOT SET.",
            "score": 0,
            "icon": persona["icon"],
            "color": persona["color"],
            "role": persona["role"]
        }

    # キャッシュチェック
    cache_key = get_cache_key(proposal_text, magi_type)
    current_time = time.time()
    
    if cache_key in st.session_state.request_cache:
        cached_data, timestamp = st.session_state.request_cache[cache_key]
        if current_time - timestamp < st.session_state.cache_expiry:
            return cached_data

    # ランダム遅延（制限を避けるため長めに）
    delay = random.uniform(5.0, 8.0)  # 2-4秒 → 5-8秒に変更
    time.sleep(delay)

    # リトライロジック
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            full_prompt = f"{persona['prompt']}\n\n提案内容: {proposal_text}"
            
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=100,  # さらに削減
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
            
            # キャッシュに保存
            st.session_state.request_cache[cache_key] = (result, current_time)
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            
            # 429エラーの場合、待機時間を増やしてリトライ
            if '429' in error_msg or 'quota' in error_msg.lower() or 'RESOURCE_EXHAUSTED' in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 3  # エクスポネンシャルバックオフ: 3秒, 6秒, 12秒
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        "magi": persona["name"],
                        "decision": False,
                        "reason": "ERROR: 429 QUOTA EXCEEDED. PLEASE WAIT A FEW MINUTES OR GET A NEW KEY",
                        "score": 0,
                        "icon": persona["icon"],
                        "color": persona["color"],
                        "role": persona["role"]
                    }
            
            # その他のエラー
            return {
                "magi": persona["name"],
                "decision": False,
                "reason": f"ERROR: {str(e)[:50]}",
                "score": 0,
                "icon": persona["icon"],
                "color": persona["color"],
                "role": persona["role"]
            }

def create_result_html(results, final_decision, approvals):
    """結果表示HTML"""
    
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

# UI
st.markdown("""
<div class="title-box">
    <h1 style="margin: 0; font-size: 28px; letter-spacing: 3px;">MAGI SYSTEM V3.1</h1>
    <p class="status-text" style="margin: 5px 0 0 0;">COMMAND: INITIALIZE DECISION-SUPPORT INTERFACE</p>
    <p class="status-text" style="margin: 5px 0 0 0;">STATUS: READY FOR INPUT (PROMPT $> )</p>
</div>
""", unsafe_allow_html=True)

# API Key設定状況の表示
if not api_key:
    st.error("""
    ⚠️ **API KEY NOT CONFIGURED**
    
    Please set your Gemini API Key in Streamlit Cloud Secrets:
    1. Click 'Manage app' (bottom right)
    2. Go to Settings → Secrets
    3. Add: `GEMINI_API_KEY = "your_key_here"`
    4. Get your key from: https://aistudio.google.com/apikey
    """)
    st.stop()
elif not isinstance(MODEL_NAME, str):
    st.warning(f"⚠️ Model initialization issue: {MODEL_NAME}")
else:
    st.success(f"✅ API configured | Model: {MODEL_NAME}")

# 入力エリア
proposal_text = st.text_area(
    "[ PROPOSAL INPUT ]",
    placeholder="Enter the subject for deliberation. (例: AIツールの全面採用)",
    height=150,
    key="proposal_input"
)

# 分析ボタン
if st.button("EXECUTE ANALYSIS [ENTER]", key="analyze_btn"):
    if not proposal_text or len(proposal_text.strip()) == 0:
        st.error("ERROR: PROPOSAL INPUT REQUIRED.")
    else:
        # レート制限チェック
        current_time = time.time()
        if st.session_state.last_request_time:
            time_since_last = current_time - st.session_state.last_request_time
            if time_since_last < 30:  # 30秒以内の連続実行を警告
                st.warning(f"⚠️ Please wait {30 - int(time_since_last)} seconds to avoid rate limits...")
                time.sleep(max(0, 30 - time_since_last))
        
        with st.spinner("ANALYZING... PLEASE WAIT... (This may take 20-30 seconds)"):
            # リクエストカウント増加
            st.session_state.request_count += 3
            st.session_state.last_request_time = time.time()
            
            # 3つのMAGIで分析
            results = {}
            progress_bar = st.progress(0)
            
            for idx, magi_type in enumerate(["casper", "balthasar", "melchior"]):
                results[magi_type] = analyze_proposal(proposal_text, magi_type)
                time.sleep(5.0)  # 2秒 → 5秒に変更
                progress_bar.progress((idx + 1) / 3)
            
            progress_bar.empty()
            
            # 最終判定
            decisions = [
                results["casper"].get("decision", False),
                results["balthasar"].get("decision", False),
                results["melchior"].get("decision", False)
            ]
            approvals = sum(decisions)
            final_decision = "approved" if approvals >= 2 else "rejected"
            
            # 結果表示
            st.markdown(create_result_html(results, final_decision, approvals), unsafe_allow_html=True)
            
            # 使用状況を表示
            st.info(f"📊 API Requests this session: {st.session_state.request_count} | Cached: {len(st.session_state.request_cache)}")

# フッター
st.markdown(f"""
<div style="margin-top: 30px; padding: 10px; background: #000000; border: 1px solid #FF6600; font-family: 'Courier New', monospace;">
    <p style="color: #FF6600; font-size: 12px; margin: 0; text-align: left;">
        > SYSTEM_MODEL: {MODEL_NAME if isinstance(MODEL_NAME, str) else 'NOT_CONFIGURED'} | ACCESS_LEVEL: SUPERUSER | CACHE: ENABLED
    </p>
</div>
""", unsafe_allow_html=True)
