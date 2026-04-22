import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC 매니저 V3.3", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 데이터 로드 함수 (캐시 무효화 전략 강화)
@st.cache_data(ttl=2) # TTL을 극단적으로 줄여 동기화 속도를 높임
def load_data():
    try:
        # ttl=0으로 설정하여 커넥션 자체 캐시를 무시하고 구글 시트 실제 데이터를 읽음
        data = conn.read(ttl=0)
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        
        # 필수 컬럼 보장
        for col in ['skill', 'stamina', 'last_team', 'is_present']:
            if col not in data.columns:
                data[col] = ""
        
        # 타입 및 공백 처리
        data = data.fillna("").astype(str)
        data['skill'] = pd.to_numeric(data['skill'], errors='coerce').fillna(10)
        data['stamina'] = pd.to_numeric(data['stamina'], errors='coerce').fillna(10)
        return data
    except Exception as e:
        st.error(f"⚠️ 데이터 로드 실패: {e}")
        return pd.DataFrame()

# 매 실행 시 최신 데이터 호출
df = load_data()

# 4. 사이드바
with st.sidebar:
    st.title("⚙️ 명단 관리")
    if st.button("🔄 강제 동기화 (캐시 초기화)"):
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
st.caption("참석 여부를 저장한 후 새로고침하면 시트의 최신 상태(TRUE/FALSE)를 그대로 불러옵니다.")

if not df.empty:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    
    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                # 🔥 [가장 중요한 부분] 시트의 값을 불리언으로 변환
                # 시트의 문자열을 앞뒤 공백 제거 후 대문자로 바꿔서 비교
                val = str(row['is_present']).strip().upper()
                stored_state = False if val == "FALSE" else True
                
                # 토글 버튼 (value 인자에 시트에서 읽어온 stored_state를 주입)
                is_on = st.toggle(f"**{row['name']}**", value=stored_state, key=f"tgl_{row['name']}")
                
                if is_on:
                    cond = st.select_slider("상태", options=["심함", "경미", "정상"], value="정상", key=f"cond_{row['name']}", label_visibility="collapsed")
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({
                        "name": row['name'], "skill": float(row['skill']), "stamina": float(row['stamina']), 
                        "injury": inj_map[cond], "last_team": str(row['last_team'])
                    })

    # 저장 버튼
    if st.button("💾 참석 명단 시트에 저장", type="primary"):
        with st.spinner("구글 시트에 기록 중..."):
            sync_df = df.copy()
            for i, row in sync_df.iterrows():
                # 현재 화면의 토글 값을 읽어서 데이터프레임에 업데이트
                current_state = st.session_state[f"tgl_{row['name']}"]
                sync_df.at[i, 'is_present'] = str(current_state).upper()
            
            # 시트 전송
            conn.update(data=sync_df)
            # 전송 직후 캐시를 완전히 비워서 다음 로드 때 시트를 다시 읽게 함
            st.cache_data.clear()
            st.success("✅ 저장 성공! 이제 새로고침해도 이 상태가 유지됩니다.")
            st.rerun()

    st.divider()

    # 팀 나누기 로직 (중략 없이 V3.2와 동일)
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
