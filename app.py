import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC 매니저 V2.7", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        data = conn.read(ttl=0)
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        # 필수 컬럼 자동 생성 (없을 경우 대비)
        for col in ['skill', 'stamina', 'last_team', 'is_present']:
            if col not in data.columns:
                data[col] = "" if col in ['last_team', 'is_present'] else 10
        return data
    except Exception as e:
        st.error(f"⚠️ 연결 실패: {e}")
        return pd.DataFrame(columns=['name', 'skill', 'stamina', 'last_team', 'is_present'])

df = load_data()

# 3. 사이드바: 명단 관리
with st.sidebar:
    st.title("⚙️ 명단 관리")
    with st.expander("👤 선수 등록/삭제", expanded=False):
        n_name = st.text_input("이름")
        c1, c2 = st.columns(2)
        n_skill = c1.slider("실력", 1, 20, 10)
        n_stam = c2.slider("체력", 1, 20, 10)
        if st.button("✅ 선수 추가"):
            if n_name and n_name not in df['name'].values:
                new_row = pd.DataFrame([{"name": n_name, "skill": n_skill, "stamina": n_stam, "last_team": "", "is_present": "TRUE"}])
                conn.update(data=pd.concat([df, new_row], ignore_index=True))
                st.rerun()

        st.divider()
        if not df.empty:
            d_name = st.selectbox("삭제 대상", df["name"].tolist())
            if st.button("🗑️ 삭제"):
                conn.update(data=df[df["name"] != d_name])
                st.rerun()

# 4. 메인 화면
st.title("⚽ TERA FC 매니저 V2.7")
st.caption("참석 정보와 팀 결과가 구글 시트에 실시간 기록됩니다.")

if df.empty:
    st.info("📢 등록된 선수가 없습니다.")
else:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    
    # 참석 여부 실시간 동기화
    updated_df = df.copy()
    needs_update = False

    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                # 시트의 TRUE/FALSE 값을 읽어서 토글 상태 결정
                current_val = True if str(row['is_present']).upper() == "TRUE" else False
                is_on = st.toggle(f"**{row['name']}**", value=current_val, key=f"tgl_{row['name']}")
                
                # 토글이 바뀌면 즉시 시트 업데이트
                if is_on != current_val:
                    updated_df.at[i, 'is_present'] = str(is_on).upper()
                    needs_update = True

                if is_on:
                    cond = st.select_slider("상태", options=["심함", "경미", "정상"], value="정상", key=f"cond_{row['name']}", label_visibility="collapsed")
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({**row.to_dict(), "injury": inj_map[cond]})

    if needs_update:
        conn.update(data=updated_df)
        st.rerun()

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

    if st.button("🔥 팀 나누기 (시트에 결과 기록)", type="primary"):
        if len(selected_players) < 2:
            st.error("🚨 참석자를 선택해 주세요.")
        else:
            with st.spinner("밸런스와 중복 방지를 계산 중..."):
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

                # --- 중요: 결과를 시트에 영구 기록 ---
                final_df = df.copy()
                t1_names = [p['name'] for p in best_t1]
                t2_names = [p['name'] for p in best_t2]
                
                for idx, row in final_df.iterrows():
                    if row['name'] in t1_names:
                        final_df.at[idx, 'last_team'] = "A"
                    elif row['name'] in t2_names:
                        final_df.at[idx, 'last_team'] = "B"
                
                conn.update(data=final_df)
                st.success("✅ 이번 경기 팀 구성이 구글 시트에 저장되었습니다. (다음 경기 중복 방지에 활용)")
