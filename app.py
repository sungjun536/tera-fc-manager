import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC 매니저 V3.1", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 데이터 로드 함수 (캐시 적용)
@st.cache_data(ttl=5) # TTL을 5초로 짧게 잡아 동기화 속도 향상
def load_data():
    try:
        # ttl=0으로 설정하여 항상 구글 시트의 실제 데이터를 읽어옴
        data = conn.read(ttl=0)
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        
        for col in ['skill', 'stamina', 'last_team', 'is_present']:
            if col not in data.columns:
                data[col] = ""
        
        data = data.fillna("").astype(str)
        data['skill'] = pd.to_numeric(data['skill'], errors='coerce').fillna(10)
        data['stamina'] = pd.to_numeric(data['stamina'], errors='coerce').fillna(10)
        return data
    except Exception as e:
        st.error(f"⚠️ 데이터 로드 실패: {e}")
        return pd.DataFrame()

# 🔥 [수정] 세션 상태(master_df)를 쓰지 않고, 매번 load_data()를 직접 호출합니다.
# 이렇게 해야 새로고침 시 캐시된 최신 DB 값을 즉시 가져옵니다.
df = load_data()

# 4. 사이드바
with st.sidebar:
    st.title("⚙️ 명단 관리")
    if st.button("🔄 시트 강제 동기화"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("👤 선수 등록"):
        n_name = st.text_input("이름")
        if st.button("✅ 등록"):
            if n_name and n_name not in df['name'].values:
                new_row = pd.DataFrame([{"name": n_name, "skill": 10, "stamina": 10, "last_team": "", "is_present": "TRUE"}])
                conn.update(data=pd.concat([df, new_row], ignore_index=True))
                st.cache_data.clear()
                st.rerun()

# 5. 메인 화면
st.title("⚽ TERA FC TEAM 우사랑 매니저")
st.caption("저장 버튼을 누르면 구글 시트에 즉시 기록되며, 새로고침 시 해당 정보를 불러옵니다.")

if not df.empty:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    
    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                # 시트의 is_present 값을 정확히 해석
                is_present_str = str(row['is_present']).upper()
                stored_value = False if is_present_str == "FALSE" else True
                
                # key값에 데이터의 현재 상태를 포함시키지 않아 충돌 방지
                is_on = st.toggle(f"**{row['name']}**", value=stored_value, key=f"tgl_{row['name']}")
                
                if is_on:
                    cond = st.select_slider("상태", options=["심함", "경미", "정상"], value="정상", key=f"cond_{row['name']}", label_visibility="collapsed")
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({
                        "name": row['name'], "skill": float(row['skill']), "stamina": float(row['stamina']), 
                        "injury": inj_map[cond], "last_team": str(row['last_team'])
                    })

    # 저장 버튼 로직 수정
    if st.button("💾 현재 상태를 시트에 영구 저장", type="primary"):
        with st.spinner("구글 시트에 기록 중..."):
            sync_df = df.copy()
            for i, row in sync_df.iterrows():
                # 현재 화면상의 토글 상태를 데이터프레임에 반영
                current_toggle_state = st.session_state[f"tgl_{row['name']}"]
                sync_df.at[i, 'is_present'] = str(current_toggle_state).upper()
            
            # 구글 시트 업데이트
            conn.update(data=sync_df)
            # 중요: 캐시를 즉시 비워서 다음 로드 때 최신 데이터를 읽게 함
            st.cache_data.clear()
            st.success("✅ 시트 저장 완료! 이제 새로고침해도 유지됩니다.")
            st.rerun()

    st.divider()

    # --- 팀 나누기 로직 (생략 없이 V3.0과 동일) ---
    if st.button("🔥 최적 밸런스 팀 나누기"):
        if len(selected_players) < 2:
            st.error("🚨 참석자를 선택해 주세요.")
        else:
            n = len(selected_players)
            all_combos = list(combinations(range(n), n // 2))
            samples = random.sample(all_combos, min(len(all_combos), 5000))
            
            def get_score(team):
                return sum((p["skill"]*1.5 + p["stamina"]*0.5) * (0.85 if p["injury"]==1 else 0.5 if p["injury"]==2 else 1) for p in team)

            best_t1_idx = min(samples, key=lambda c: abs(get_score([selected_players[i] for i in c]) - get_score([selected_players[i] for i in range(n) if i not in c])))
            t1 = [selected_players[i] for i in best_t1_idx]
            t2 = [selected_players[i] for i in range(n) if i not in best_t1_idx]

            c1, c2 = st.columns(2)
            with c1:
                st.info(f"### 🔵 A팀 ({len(t1)}명)")
                for p in t1: st.write(f"{'🟢' if p['injury']==0 else '🟡' if p['injury']==1 else '🔴'} **{p['name']}**")
            with c2:
                st.warning(f"### 🟠 B팀 ({len(t2)}명)")
                for p in t2: st.write(f"{'🟢' if p['injury']==0 else '🟡' if p['injury']==1 else '🔴'} **{p['name']}**")

            # 결과 자동 저장
            final_df = df.copy()
            for idx, row in final_df.iterrows():
                if row['name'] in [p['name'] for p in t1]: final_df.at[idx, 'last_team'] = "A"
                elif row['name'] in [p['name'] for p in t2]: final_df.at[idx, 'last_team'] = "B"
            conn.update(data=final_df)
            st.cache_data.clear()
