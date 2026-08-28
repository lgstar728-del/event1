import os
from datetime import date, timedelta

import folium
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from streamlit_folium import st_folium

load_dotenv()  # .env 파일의 환경변수를 불러옴

# ----------------------------------------
# 페이지 설정
# ----------------------------------------
st.set_page_config(
    page_title="나에게 딱 맞는 호텔 패키지 추천 이벤트",
    page_icon="🏨",
    layout="centered",
)

HOTEL_NAME = "○○ HOTEL & RESORT"  # TODO: 실제 호텔명으로 교체

# ----------------------------------------
# PRD 6장 톤앤매너
# ----------------------------------------
NAVY = "#0B1F3A"
GOLD = "#C6A15B"
WHITE = "#FFFFFF"

TONE_COLORS = "Navy(신뢰감·프리미엄), Gold(고급스러움·특별한 경험), White(깨끗하고 편안한 이미지)"
TONE_MOOD_KEYWORDS = "고급스러움, 편안함, 신뢰감, 프리미엄, 여행 감성"
TONE_PRINCIPLE = (
    "호텔의 프리미엄 이미지를 유지하되 무겁지 않게, 충분한 여백과 고품질 호텔 이미지를 활용해 "
    "여행에 대한 기대감을 높이는 감성적인 시각 경험을 강조. 문구는 친근하면서도 세련된 호텔 브랜드 어조 유지."
)

# 결과 카드(st-key-result_card)에 옅은 테두리 + 그림자를 적용
st.markdown(
    f"""
    <style>
    .st-key-result_card {{
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(11, 31, 58, 0.15);
        border: 1px solid {GOLD}55 !important;
        padding: 0.5rem 0.25rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------
# PRD 4.2 맞춤형 결과 생성: 추천 이유 매핑 테이블
# 선택 조합에 따라 추천 이유 문장이 달라지도록 항목별로 구성
# ----------------------------------------
PURPOSE_REASON = {
    "호캉스": "온전히 나만을 위한 휴식 시간을 보낼 수 있도록 구성했어요.",
    "커플여행": "둘만의 특별한 순간에 집중할 수 있도록 구성했어요.",
    "가족여행": "가족 모두가 편안하게 머물 수 있도록 구성했어요.",
    "비즈니스": "효율적인 일정과 편안한 휴식을 동시에 챙길 수 있도록 구성했어요.",
}

MOOD_REASON = {
    "럭셔리": "고급스러운 공간에서 특별한 대접을 받는 경험을 드려요.",
    "감성적": "감성 가득한 분위기 속에서 오래 기억될 순간을 선물해요.",
    "편안한": "군더더기 없이 편안하게 쉴 수 있는 공간을 제공해요.",
    "트렌디한": "지금 가장 화제가 되는 트렌디한 공간을 경험할 수 있어요.",
}

FACTOR_REASON = {
    "가격": "합리적인 가격으로 부담 없이 즐길 수 있어요.",
    "객실 전망": "탁 트인 전망을 자랑하는 객실을 우선 배정해드려요.",
    "청결": "철저한 위생 관리로 안심하고 머물 수 있어요.",
    "접근성": "주요 교통·관광 거점과 가까워 이동이 편리해요.",
    "서비스": "세심한 응대의 프리미엄 서비스를 경험할 수 있어요.",
}

BENEFIT_REASON = {
    "조식": "든든한 조식으로 하루를 시작할 수 있어요.",
    "객실 할인": "객실 요금 할인 혜택이 포함돼요.",
    "레이트 체크아웃": "여유로운 레이트 체크아웃으로 마지막까지 편안하게 즐길 수 있어요.",
    "부대시설 이용": "수영장, 스파 등 부대시설을 자유롭게 이용할 수 있어요.",
}


def build_reasons(purpose, benefits, factor, mood):
    """선택 조합을 바탕으로 추천 이유 문장 목록을 만든다."""
    reasons = [PURPOSE_REASON[purpose], MOOD_REASON[mood], FACTOR_REASON[factor]]
    reasons += [BENEFIT_REASON[b] for b in benefits]
    return reasons


def get_highlights(benefits, factor):
    """결과 화면에 보여줄 핵심 혜택 목록을 만든다."""
    return [factor] + benefits


def build_hashtags(purpose, benefits, factor, mood):
    """SNS 공유용 해시태그 목록을 만든다."""
    tags = [purpose, mood, factor] + benefits
    return [f"#{tag.replace(' ', '')}" for tag in tags]


# ----------------------------------------
# 패키지명 생성 (지도 팝업 등 결과 화면 전반에서 사용)
# ----------------------------------------
PURPOSE_NAME = {
    "호캉스": "호캉스",
    "커플여행": "커플 스테이",
    "가족여행": "패밀리 스테이",
    "비즈니스": "비즈니스 스테이",
}

MOOD_ADJ = {
    "럭셔리": "프리미엄",
    "감성적": "감성",
    "편안한": "릴렉스",
    "트렌디한": "트렌디",
}


def build_package_name(purpose, mood):
    return f"{MOOD_ADJ[mood]} {PURPOSE_NAME[purpose]} 패키지"


# ----------------------------------------
# 지도 기능: 지점 위치 데이터 (TODO: 실제 지점 주소/좌표로 교체)
# ----------------------------------------
HOTEL_BRANCHES = [
    {
        "id": "seoul",
        "name": f"{HOTEL_NAME} 서울 본점",
        "address": "서울특별시 중구 (예시 주소)",
        "lat": 37.5665,
        "lon": 126.9780,
    },
    {
        "id": "busan",
        "name": f"{HOTEL_NAME} 부산 해운대점",
        "address": "부산광역시 해운대구 (예시 주소)",
        "lat": 35.1587,
        "lon": 129.1604,
    },
    {
        "id": "jeju",
        "name": f"{HOTEL_NAME} 제주 서귀포점",
        "address": "제주특별자치도 서귀포시 (예시 주소)",
        "lat": 33.2541,
        "lon": 126.5601,
    },
    {
        "id": "gangneung",
        "name": f"{HOTEL_NAME} 강릉 경포점",
        "address": "강원특별자치도 강릉시 (예시 주소)",
        "lat": 37.8055,
        "lon": 128.9070,
    },
]

# 여행 목적에 따라 추천 지점이 달라지도록 구성 (TODO: 실제 추천 로직으로 교체)
RECOMMENDED_BRANCH_BY_PURPOSE = {
    "비즈니스": "seoul",
    "가족여행": "busan",
    "호캉스": "jeju",
    "커플여행": "gangneung",
}


def get_recommended_branch(purpose):
    branch_id = RECOMMENDED_BRANCH_BY_PURPOSE.get(purpose, HOTEL_BRANCHES[0]["id"])
    return next(b for b in HOTEL_BRANCHES if b["id"] == branch_id)


def build_hotel_map(recommended_branch, package_name):
    """OpenStreetMap 기반 지도(Folium)에 모든 지점을 Marker로 표시하고,
    추천 지점은 색상/아이콘을 다르게 해서 쉽게 식별되도록 한다.
    API 키가 필요 없는 기본 OpenStreetMap 타일을 사용한다.
    """
    m = folium.Map(
        location=[recommended_branch["lat"], recommended_branch["lon"]],
        zoom_start=7,
        tiles="OpenStreetMap",
    )

    for branch in HOTEL_BRANCHES:
        is_recommended = branch["id"] == recommended_branch["id"]

        popup_lines = [f"<b>{branch['name']}</b>", branch["address"]]
        if is_recommended:
            popup_lines.append(f"추천 패키지: {package_name}")
        popup_html = "<br>".join(popup_lines)

        folium.Marker(
            location=[branch["lat"], branch["lon"]],
            popup=folium.Popup(popup_html, max_width=250, show=is_recommended),
            tooltip=branch["name"],
            icon=folium.Icon(
                color="red" if is_recommended else "blue",
                icon="star" if is_recommended else "info-sign",
            ),
        ).add_to(m)

    return m


# ----------------------------------------
# PRD 5장 브랜드 요소: 기간 한정 할인쿠폰
# 여행 목적별로 쿠폰 혜택이 달라지도록 구성
# ----------------------------------------
COUPON_MAP = {
    "호캉스": ("HOCANCE10", "객실 10% 할인"),
    "커플여행": ("COUPLE15", "객실 15% 할인"),
    "가족여행": ("FAMILY20", "가족 3인 이상 20% 할인"),
    "비즈니스": ("BIZ05", "5% 할인 + 무료 조식"),
}
COUPON_VALID_DAYS = 7  # 쿠폰 유효기간(발급일로부터)


def get_coupon(purpose):
    code, desc = COUPON_MAP[purpose]
    expiry = date.today() + timedelta(days=COUPON_VALID_DAYS)
    return code, desc, expiry


# ----------------------------------------
# SNS 홍보 이미지 placeholder 생성
# TODO: 실제 서비스에서는 브랜드 사진 + 이미지 생성 API 등으로 교체 필요
# ----------------------------------------
def generate_sns_image(headline: str, subtext: str, width=800, height=450) -> Image.Image:
    navy_rgb = (11, 31, 58)
    gold_rgb = (198, 161, 91)
    white_rgb = (255, 255, 255)

    img = Image.new("RGB", (width, height), navy_rgb)
    draw = ImageDraw.Draw(img)

    try:
        font_headline = ImageFont.truetype("malgun.ttf", 40)
        font_sub = ImageFont.truetype("malgun.ttf", 22)
    except Exception:
        font_headline = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.rectangle([0, height - 12, width, height], fill=gold_rgb)
    draw.text((50, height // 2 - 50), headline, font=font_headline, fill=white_rgb)
    draw.text((50, height // 2 + 20), subtext, font=font_sub, fill=gold_rgb)

    return img


# ----------------------------------------
# 선택 값 + 톤앤매너를 결합한 프롬프트 생성
# ----------------------------------------
def build_prompt(purpose, benefits, factor, mood):
    return f"""[고객 선택 정보]
- 여행 목적: {purpose}
- 선호 혜택: {', '.join(benefits)}
- 숙박 시 중요요소: {factor}
- 선호 분위기: {mood}

[톤앤매너]
- 색상: {TONE_COLORS}
- 분위기 키워드: {TONE_MOOD_KEYWORDS}
- 디자인 원칙: {TONE_PRINCIPLE}

위 고객 선택 정보와 톤앤매너를 반영하여, 이 고객에게 어울리는 맞춤형 호텔 패키지명, 추천 이유, 광고 카피, SNS 홍보 이미지 컨셉을 제안해줘."""


# ----------------------------------------
# PRD 4.2 맞춤형 결과 생성: OpenAI를 이용한 이름 짓기
# ----------------------------------------
def get_openai_api_key():
    """`.env` 파일에서 OPENAI_API_KEY를 읽어온다.
    .env 파일이 없거나 키가 비어있으면 (None, 안내 메시지)를 반환한다.
    """
    if not os.path.exists(".env"):
        return None, (
            "`.env` 파일을 찾을 수 없습니다. 프로젝트 폴더에 `.env` 파일을 만들고 "
            "`OPENAI_API_KEY=발급받은_키` 형식으로 API 키를 추가해주세요."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, (
            "`.env` 파일은 있지만 `OPENAI_API_KEY` 값이 비어있습니다. "
            "`.env` 파일에 `OPENAI_API_KEY=발급받은_키`를 추가해주세요."
        )

    return api_key, None


def build_name_prompt(keywords: str) -> str:
    return (
        f"다음 제품 특징을 가진 신제품의 이름 후보 3개와 슬로건 1개를 만들어줘. "
        f"제품 특징: {keywords}. "
        f"이름 후보는 번호를 붙여서, 슬로건은 마지막 줄에 표시해줘."
    )


def call_openai_for_names(prompt: str, api_key: str) -> str:
    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ----------------------------------------
# '결과 보기' 버튼 클릭 시 실행될 함수
# TODO: 예약하기 / SNS 공유 버튼 연동 예정
# ----------------------------------------
def show_result(purpose, benefits, factor, mood):
    st.success("✅ '결과 보기' 버튼이 눌렸습니다.")

    highlights = get_highlights(benefits, factor)
    reasons = build_reasons(purpose, benefits, factor, mood)
    hashtags = build_hashtags(purpose, benefits, factor, mood)
    coupon_code, coupon_desc, coupon_expiry = get_coupon(purpose)
    package_name = build_package_name(purpose, mood)
    recommended_branch = get_recommended_branch(purpose)

    # ---- 결과 카드: 문구 + 이미지 + 브랜드 요소를 한 카드 안에 배치 ----
    with st.container(key="result_card", border=True):
        # 브랜드 요소: 호텔명/로고 + 완성 메시지
        st.markdown(f"### 🏨 {HOTEL_NAME}")
        st.markdown("**당신을 위한 특별한 호텔 패키지가 완성되었습니다.**")
        st.markdown(f"#### ✨ {package_name}")

        # SNS 홍보 이미지
        st.image(
            generate_sns_image(HOTEL_NAME, " · ".join(highlights)),
            use_container_width=True,
        )

        # 핵심 혜택
        st.markdown("**핵심 혜택**")
        st.write(" · ".join(highlights))

        # 추천 이유
        st.markdown("**추천 이유**")
        for reason in reasons:
            st.markdown(f"- {reason}")

        st.divider()

        # 지도: 추천 지점 + 전체 지점 Marker (OpenStreetMap, API 키 불필요)
        st.markdown("**📍 추천 호텔 위치**")
        hotel_map = build_hotel_map(recommended_branch, package_name)
        st_folium(hotel_map, use_container_width=True, height=420, key="hotel_map")
        st.caption(f"⭐ 추천 지점: {recommended_branch['name']} — {recommended_branch['address']}")

        st.divider()

        # 브랜드 요소: 기간 한정 할인쿠폰
        st.markdown("**🎟️ 기간 한정 할인쿠폰**")
        st.info(
            f"쿠폰 코드: **{coupon_code}**  \n"
            f"혜택: {coupon_desc}  \n"
            f"유효기간: {coupon_expiry.strftime('%Y-%m-%d')}까지"
        )

        # 브랜드 요소: 해시태그
        st.markdown("**해시태그**")
        st.write(" ".join(hashtags))

        st.divider()

        # 이름 지어줘 (AI 이름 후보 + 슬로건)
        keywords = ", ".join([purpose, *benefits, factor, mood])

        if st.button("이름 지어줘", key="name_button"):
            api_key, error_message = get_openai_api_key()

            if error_message:
                st.warning(error_message)
            else:
                name_prompt = build_name_prompt(keywords)
                with st.spinner("AI가 이름을 짓고 있어요..."):
                    try:
                        st.session_state["name_result"] = call_openai_for_names(name_prompt, api_key)
                    except Exception as e:
                        st.session_state["name_result"] = None
                        st.error(f"OpenAI API 호출 중 오류가 발생했습니다: {e}")

        if st.session_state.get("name_result"):
            st.markdown("#### 🤖 AI가 추천하는 이름")
            st.write(st.session_state["name_result"])

    # 프롬프트 확인용 (디버그용 - 브랜드 요소가 아니므로 카드 밖 접이식 영역에 배치)
    with st.expander("생성된 프롬프트 (확인용)"):
        st.code(build_prompt(purpose, benefits, factor, mood), language=None)


# ----------------------------------------
# Hero 영역
# ----------------------------------------
st.title("🏨 나에게 딱 맞는 호텔 패키지 추천 이벤트")
st.write("아래 4가지 질문에 답하고, 당신을 위한 맞춤형 호텔 패키지를 확인해보세요.")

st.divider()

# ----------------------------------------
# STEP 1. 선택
# ----------------------------------------
st.header("STEP 1. 나의 취향 선택하기")

# 1. 여행 목적 (단일선택)
st.subheader("1. 여행 목적")
travel_purpose = st.radio(
    "이번 여행의 목적은 무엇인가요?",
    options=["호캉스", "커플여행", "가족여행", "비즈니스"],
    index=None,
    horizontal=True,
)

# 2. 선호 혜택 (다중선택, 최대 2개)
st.subheader("2. 선호 혜택")
preferred_benefits = st.multiselect(
    "가장 원하는 혜택을 선택해주세요. (최대 2개)",
    options=["조식", "객실 할인", "레이트 체크아웃", "부대시설 이용"],
    max_selections=2,
)

# 3. 숙박 시 중요요소 (단일선택)
st.subheader("3. 숙박 시 중요요소")
important_factor = st.radio(
    "숙박할 때 가장 중요하게 생각하는 요소는 무엇인가요?",
    options=["가격", "객실 전망", "청결", "접근성", "서비스"],
    index=None,
    horizontal=True,
)

# 4. 선호 분위기 (단일선택)
st.subheader("4. 선호 분위기")
preferred_mood = st.radio(
    "선호하는 호텔 분위기는 무엇인가요?",
    options=["럭셔리", "감성적", "편안한", "트렌디한"],
    index=None,
    horizontal=True,
)

st.divider()

# ----------------------------------------
# STEP 2. 클릭
# ----------------------------------------
# show_result 내부에 '이름 지어줘' 버튼이 있어, 그 버튼을 누르면 화면이 다시
# 실행되며 이 블록을 다시 지나간다. 그때도 결과 화면이 계속 보이도록
# session_state에 결과 표시 여부를 저장해둔다.
if "show_result" not in st.session_state:
    st.session_state.show_result = False

if st.button("나에게 맞는 호텔 패키지 찾기", type="primary", use_container_width=True):
    missing = []
    if not travel_purpose:
        missing.append("여행 목적")
    if not preferred_benefits:
        missing.append("선호 혜택")
    if not important_factor:
        missing.append("숙박 시 중요요소")
    if not preferred_mood:
        missing.append("선호 분위기")

    if missing:
        st.warning(f"다음 항목을 선택해주세요: {', '.join(missing)}")
        st.session_state.show_result = False
    else:
        st.session_state.show_result = True

if st.session_state.show_result:
    show_result(travel_purpose, preferred_benefits, important_factor, preferred_mood)
