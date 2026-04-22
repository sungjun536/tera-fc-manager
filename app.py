import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC Team 매니저", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 데이터 로드 함수 (캐시 적용으로 429 에러 방지)
@st.cache_data(ttl=60) # 1분 동안 데이터를 캐싱합니다.
def load_data():
    try:
        # API 호출 (ttl=0은 내부 라이브러리 캐시를 무시하기 위함)
        data = conn.read(ttl=0)
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        
        # 필수 컬럼 확인 및 타입 변환
        for col in ['skill', 'stamina', 'last_team', 'is_present']:
            if col not in data.columns:
                data[col] = ""
        
        data = data.fillna("").astype(str)
        data['skill'] = pd.to_numeric(data['skill'], errors='coerce').fillna(10)
        data['stamina'] = pd.to_numeric(data['stamina'], errors='coerce').fillna(10)
        
        return data
    except Exception as e:
        if "429" in str(e):
            st.error("🚀 구글 API 한도 초과! 1분만 기다렸다가 새로고침해 주세요.")
        else:
            st.error(f"⚠️ 연결 실패: {e}")
        return pd.DataFrame()

# 세션 상태에 데이터 저장 (새로고침 전까지 유지)
if 'master_df' not in st.session_state:
    st.session_state.master_df = load_data()

df = st.session_state.master_df

# 4. 사이드바: 명단 관리
with st.sidebar:
    st.title("⚙️ 명단 관리")
    if st.button("🔄 데이터 강제 새로고침"):
        st.cache_data.clear()
        st.session_state.master_df = load_data()
        st.rerun()

    with st.expander("👤 선수 등록/삭제"):
        n_name = st.text_input("이름")
        c1, c2 = st.columns(2)
        n_skill = c1.slider("실력", 1, 20, 10)
        n_stam = c2.slider("체력", 1, 20, 10)
        if st.button("✅ 선수 추가"):
            if n_name and n_name not in df['name'].values:
                new_row = pd.DataFrame([{"name": n_name, "skill": n_skill, "stamina": n_stam, "last_team": "", "is_present": "TRUE"}])
                conn.update(data=pd.concat([df, new_row], ignore_index=True))
                st.cache_data.clear()
                st.session_state.master_df = load_data()
                st.rerun()

# 5. 메인 화면
st.title("⚽ TERA FC TEAM 매니저_우사랑멍청이")
st.caption("API 최적화 버전: 참석 정보는 하단 저장 버튼을 누를 때 시트에 반영됩니다.")

if df.empty:
    st.info("📢 데이터를 불러오는 중이거나 명단이 비어있습니다.")
else:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    
    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                # [수정] 시트 값이 없거나 처음 시작할 때 기본값을 TRUE(참석)로 설정
                # 시트의 is_present가 명시적으로 'FALSE'일 때만 False로 인식
                is_present_val = str(row['is_present']).upper()
                default_toggle = False if is_present_val == "FALSE" else True
                
                is_on = st.toggle(f"**{row['name']}**", value=default_toggle, key=f"tgl_{row['name']}")
                
                if is_on:
                    cond = st.select_slider("상태", options=["심함", "경미", "정상"], value="정상", key=f"cond_{row['name']}", label_visibility="collapsed")
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({
                        "name": row['name'], 
                        "skill": float(row['skill']), 
                        "stamina": float(row['stamina']), 
                        "injury": inj_map[cond],
                        "last_team": str(row['last_team'])
                    })

    # API 호출을 줄이기 위한 명시적 저장 버튼
    if st.button("💾 현재 참석 명단 시트에 저장"):
        with st.spinner("구글 시트에 동기화 중..."):
            sync_df = df.copy()
            for i, row in sync_df.iterrows():
                # 화면의 현재 토글 상태를 수집
                tgl_state = st.session_state[f"tgl_{row['name']}"]
                sync_df.at[i, 'is_present'] = str(tgl_state).upper()
            conn.update(data=sync_df)
            st.cache_data.clear()
            st.success("시트 저장 완료!")

    st.divider()

    # --- 팀 나누기 로직 ---
    def get_team_score(team):
        score = 0
        for p in team:
            p_score = (p["skill"] * 1.5) + (p["stamina"] * 0.5)
            if p["injury"] == 1: p_score *= 0.85
            elif p["injury"] == 2: p_score *= 0.5
            score += p_score
        return score

    def get_repeat_penalty(t1, t2):
        penalty = 0
        for team in [t1, t2]:
            last_a = sum(1 for p in team if str(p["last_team"]).upper() == "A")
            last_b = sum(1 for p in team if str(p["last_team"]).upper() == "B")
            penalty += (last_a ** 2) + (last_b ** 2)
        return penalty

    if st.button("🔥 최적 밸런스 팀 나누기", type="primary"):
        if len(selected_players) < 2:
            st.error("🚨 참석자를 선택해 주세요.")
        else:
            with st.spinner("중복 방지 및 밸런스 시뮬레이션 중..."):
                n = len(selected_players)
                all_combos = list(combinations(range(n), n // 2))
                samples = random.sample(all_combos, min(len(all_combos), 5000))
                
                best_t1, best_t2 = None, None
                min_total_penalty = float('inf')

                for combo in samples:
                    t1 = [selected_players[i] for i in combo]
                    t2 = [selected_players[i] for i in range(n) if i not in combo]
                    diff = abs(get_team_score(t1) - get_team_score(t2))
                    penalty = get_repeat_penalty(t1, t2) * 0.5
                    if (diff + penalty) < min_total_penalty:
                        min_total_penalty = diff + penalty
                        best_t1, best_t2 = t1, t2

                # 결과 출력
                c1, c2 = st.columns(2)
                with c1:
                    st.info(f"### 🔵 A팀 ({len(best_t1)}명)")
                    for p in best_t1:
                        icon = "🟢" if p['injury']==0 else "🟡" if p['injury']==1 else "🔴"
                        st.write(f"{icon} **{p['name']}**")
                with c2:
                    st.warning(f"### 🟠 B팀 ({len(best_t2)}명)")
                    for p in best_t2:
                        icon = "🟢" if p['injury']==0 else "🟡" if p['injury']==1 else "🔴"
                        st.write(f"{icon} **{p['name']}**")

                # 결과 시트 자동 저장
                final_df = df.copy()
                t1_names = [p['name'] for p in best_t1]
                t2_names = [p['name'] for p in best_t2]
                for idx, row in final_df.iterrows():
                    if row['name'] in t1_names: final_df.at[idx, 'last_team'] = "A"
                    elif row['name'] in t2_names: final_df.at[idx, 'last_team'] = "B"
                
                conn.update(data=final_df)
                st.cache_data.clear()
                st.success("✅ 팀 구성 결과가 시트에 저장되었습니다.")
