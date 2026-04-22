import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC 매니저 V2.5", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        data = conn.read(ttl=0)
        # 데이터 정제
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        # last_team 컬럼이 없으면 생성
        if 'last_team' not in data.columns:
            data['last_team'] = ""
        return data
    except Exception as e:
        st.error(f"⚠️ 시트 연결 실패: {e}")
        return pd.DataFrame(columns=['name', 'skill', 'stamina', 'last_team'])

df = load_data()

# 3. 사이드바: 명단 관리
with st.sidebar:
    st.title("⚙️ 명단 관리")
    with st.expander("👤 선수 등록/삭제", expanded=False):
        st.subheader("신규 선수")
        n_name = st.text_input("이름")
        c1, c2 = st.columns(2)
        n_skill = c1.slider("실력", 1, 20, 10)
        n_stam = c2.slider("체력", 1, 20, 10)
        n_last = st.selectbox("지난번 팀", ["", "A", "B"])
        
        if st.button("✅ 추가"):
            if n_name and n_name not in df['name'].values:
                new_row = pd.DataFrame([{"name": n_name, "skill": n_skill, "stamina": n_stam, "last_team": n_last}])
                conn.update(data=pd.concat([df, new_row], ignore_index=True))
                st.rerun()

        st.divider()
        if not df.empty:
            d_name = st.selectbox("삭제 대상", df["name"].tolist())
            if st.button("🗑️ 삭제"):
                conn.update(data=df[df["name"] != d_name])
                st.rerun()

# 4. 메인 화면
st.title("⚽ TERA FC 자동화 매니저 V2.5")
st.caption("실시간 밸런스 최적화 및 팀 중복 방지 알고리즘 가동 중")

if df.empty:
    st.info("📢 등록된 선수가 없습니다.")
else:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                is_on = st.toggle(f"**{row['name']}**", value=True, key=f"tgl_{row['name']}")
                if is_on:
                    cond = st.select_slider("상태", options=["심함", "경미", "정상"], value="정상", key=f"cond_{row['name']}", label_visibility="collapsed")
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({
                        "name": row['name'], 
                        "skill": row['skill'], 
                        "stamina": row['stamina'], 
                        "injury": inj_map[cond],
                        "last_team": row['last_team']
                    })

    st.divider()

    # --- 밸런스 & 중복 방지 알고리즘 ---
    def get_team_score(team):
        score = 0
        for p in team:
            s, t = p["skill"], p["stamina"]
            # 실력에 가중치 1.5배, 체력에 0.5배 적용 (실력 중심 밸런스)
            p_score = (s * 1.5) + (t * 0.5)
            # 부상 보정
            if p["injury"] == 1: p_score *= 0.85
            elif p["injury"] == 2: p_score *= 0.5
            score += p_score
        return score

    def get_repeat_penalty(team1, team2):
        """지난주에 같은 팀이었던 사람들이 이번에도 같은 팀인 경우 벌점 부여"""
        penalty = 0
        for team in [team1, team2]:
            last_a = sum(1 for p in team if p["last_team"] == "A")
            last_b = sum(1 for p in team if p["last_team"] == "B")
            # 한 팀에 지난번 같은 팀이었던 사람이 너무 몰리면 페널티
            penalty += (last_a ** 2) + (last_b ** 2)
        return penalty

    if st.button("🔥 팀 나누기 (밸런스 + 중복 방지)", type="primary"):
        if len(selected_players) < 4:
            st.error("🚨 최소 4명 이상의 참석자가 필요합니다.")
        else:
            with st.spinner("최적의 조합을 시뮬레이션 중..."):
                n = len(selected_players)
                all_combos = list(combinations(range(n), n // 2))
                # 5,000번 무작위 샘플링으로 정밀도 향상
                samples = random.sample(all_combos, min(len(all_combos), 5000))
                
                best_t1, best_t2 = None, None
                min_total_penalty = float('inf')

                for combo in samples:
                    t1 = [selected_players[i] for i in combo]
                    t2 = [selected_players[i] for i in range(n) if i not in combo]
                    
                    # 1. 전력 차이 계산 (낮을수록 좋음)
                    power_diff = abs(get_team_score(t1) - get_team_score(t2))
                    
                    # 2. 중복 방지 페널티 계산 (낮을수록 좋음)
                    repeat_penalty = get_repeat_penalty(t1, t2) * 0.5 # 가중치 조절 가능
                    
                    total_penalty = power_diff + repeat_penalty
                    
                    if total_penalty < min_total_penalty:
                        min_total_penalty = total_penalty
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

    # 가이드 안내
    st.markdown("---")
    st.subheader("📢 시스템 안내")
    ga1, ga2, ga3 = st.columns(3)
    ga1.markdown("#### ⚖️ 실력 중심 밸런스\n기술 점수가 전력에 더 크게 반영됩니다.")
    ga2.markdown("#### 🔄 중복 방지 적용\n지난 경기와 팀 구성이 최대한 바뀌도록 설계되었습니다.")
    ga3.markdown("#### 🟢🟡🔴 컨디션 보정\n부상 정도에 따라 전력 지수가 자동 하향 조정됩니다.")
