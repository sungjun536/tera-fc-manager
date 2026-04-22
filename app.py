import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정 및 디자인
st.set_page_config(page_title="TERA FC 매니저 V2.0", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        data = conn.read(ttl=0)
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        return data
    except Exception as e:
        st.error(f"⚠️ 시트 연결 실패: {e}")
        return pd.DataFrame(columns=['name', 'skill', 'stamina'])

df = load_data()

# 3. 사이드바: 명단 관리 (누구나 접근 가능)
with st.sidebar:
    st.title("⚙️ 명단 관리")
    st.caption("선수 추가 및 삭제가 가능합니다.")
    
    with st.expander("👤 선수 등록/삭제", expanded=True):
        st.subheader("신규 선수 등록")
        n_name = st.text_input("선수 이름", placeholder="이름 입력")
        c1, c2 = st.columns(2)
        n_skill = c1.slider("실력", 1, 20, 10)
        n_stam = c2.slider("체력", 1, 20, 10)
        
        if st.button("✅ 명단에 추가"):
            if n_name:
                if n_name not in df['name'].values:
                    new_row = pd.DataFrame([{"name": n_name, "skill": n_skill, "stamina": n_stam}])
                    updated_df = pd.concat([df, new_row], ignore_index=True)
                    conn.update(data=updated_df)
                    st.success(f"{n_name} 등록 완료!")
                    st.rerun()
                else:
                    st.error("이미 등록된 이름입니다.")

        st.divider()
        
        st.subheader("명단 삭제")
        if not df.empty:
            d_name = st.selectbox("삭제할 선수 선택", df["name"].tolist())
            if st.button("🗑️ 선택 삭제", type="secondary"):
                updated_df = df[df["name"] != d_name]
                conn.update(data=updated_df)
                st.warning(f"{d_name} 삭제 완료")
                st.rerun()

# 4. 메인 화면
st.title("⚽ TERA FC 자동화 매니저")
st.write("모든 팀 편성은 데이터 기반으로 자동 최적화됩니다.")

if df.empty:
    st.info("📢 등록된 선수가 없습니다. 사이드바에서 선수를 추가해주세요!")
else:
    st.subheader("1. 오늘 경기 참석자 및 컨디션 체크")
    selected_players = []
    
    cols = st.columns(4)
    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                is_on = st.toggle(f"**{row['name']}**", value=True, key=f"tgl_{row['name']}")
                if is_on:
                    cond = st.select_slider(
                        "상태",
                        options=["심함", "경미", "정상"],
                        value="정상",
                        key=f"cond_{row['name']}",
                        label_visibility="collapsed"
                    )
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({
                        "name": row['name'], "skill": row['skill'], "stamina": row['stamina'], "injury": inj_map[cond]
                    })

    st.divider()

    # 팀 스탯 계산 로직
    def get_team_stats(team):
        s_total, t_total = 0, 0
        for p in team:
            s, t = p["skill"], p["stamina"]
            if p["injury"] == 1: s *= 0.9; t *= 0.8
            elif p["injury"] == 2: s *= 0.6; t *= 0.4
            s_total += s
            t_total += t
        return s_total, t_total

    if st.button("🔥 최적의 밸런스로 팀 나누기", type="primary"):
        if len(selected_players) < 2:
            st.error("🚨 참석자를 2명 이상 선택해 주세요.")
        else:
            with st.spinner("최상의 밸런스를 계산 중..."):
                n = len(selected_players)
                all_combos = list(combinations(range(n), n // 2))
                selected_combos = random.sample(all_combos, min(len(all_combos), 3000))
                
                # 실력 합산 차이가 가장 적은 조합 찾기
                best_match = min(selected_combos, key=lambda c: abs(get_team_stats([selected_players[i] for i in c])[0] - get_team_stats([selected_players[i] for i in range(n) if i not in c])[0]))
                
                t1 = [selected_players[i] for i in best_match]
                t2 = [selected_players[i] for i in range(n) if i not in best_match]

            # 결과 출력
            c1, c2 = st.columns(2)
            with c1:
                st.info(f"### 🔵 A팀 ({len(t1)}명)")
                for p in t1:
                    icon = "🟢" if p['injury']==0 else "🟡" if p['injury']==1 else "🔴"
                    st.write(f"{icon} **{p['name']}**")
            with c2:
                st.warning(f"### 🟠 B팀 ({len(t2)}명)")
                for p in t2:
                    icon = "🟢" if p['injury']==0 else "🟡" if p['injury']==1 else "🔴"
                    st.write(f"{icon} **{p['name']}**")

    # --- 하단 공지사항 (색상 및 보정 설명) ---
    st.markdown("---")
    st.subheader("📢 컨디션 아이콘 안내")
    
    # 가이드 테이블 형태 출력
    guide_cols = st.columns(3)
    guide_cols[0].markdown("### 🟢 정상\n데이터가 **100%** 반영됩니다.")
    guide_cols[1].markdown("### 🟡 경미(하)\n실력 **90%** / 체력 **80%** 반영")
    guide_cols[2].markdown("### 🔴 심함(상)\n실력 **60%** / 체력 **40%** 반영")
    
    st.caption("※ 모든 팀 배정은 실력 지수 합계의 차이를 최소화하도록 알고리즘에 의해 자동 결정됩니다.")