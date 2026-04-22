import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC 매니저 V3.5", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 데이터 로드 함수 (TTL을 0으로 설정하여 항상 최신 시트 참조)
def load_data():
    try:
        # 커넥션 자체 캐시를 완전히 무시 (ttl=0)
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

# 앱 실행 시 세션에 데이터가 없으면 로드
if 'master_df' not in st.session_state:
    st.session_state.master_df = load_data()

df = st.session_state.master_df

# 4. 사이드바
with st.sidebar:
    st.title("⚙️ 명단 관리")
    if st.button("🔄 서버 데이터 강제 동기화"):
        st.session_state.master_df = load_data()
        st.rerun()

# 5. 메인 화면
st.title("⚽ TERA FC TEAM 매니저")
st.caption("저장 버튼을 누르면 화면 상태가 시트에 고정됩니다.")

if not df.empty:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    
    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                # 시트의 값 가져오기
                val = str(row['is_present']).strip().upper()
                stored_state = False if val == "FALSE" else True
                
                # key에 시트 상태를 넣지 않고 고정 key 사용 (상태 충돌 방지)
                t_key = f"tgl_{row['name']}"
                
                # 세션에 이미 값이 있다면 그 값을 우선 사용, 없으면 시트 값 사용
                if t_key not in st.session_state:
                    st.session_state[t_key] = stored_state
                
                is_on = st.toggle(f"**{row['name']}**", key=t_key)
                
                if is_on:
                    cond = st.select_slider("상태", options=["심함", "경미", "정상"], value="정상", key=f"cond_{row['name']}", label_visibility="collapsed")
                    inj_map = {"정상": 0, "경미": 1, "심함": 2}
                    selected_players.append({
                        "name": row['name'], "skill": float(row['skill']), "stamina": float(row['stamina']), 
                        "injury": inj_map[cond], "last_team": str(row['last_team'])
                    })

    # 💾 저장 버튼 로직 (중요!)
    if st.button("💾 현재 상태를 시트에 영구 저장", type="primary"):
        with st.spinner("구글 시트 업데이트 중..."):
            sync_df = df.copy()
            for i, row in sync_df.iterrows():
                # 현재 화면의 토글 상태를 읽음
                curr_state = st.session_state[f"tgl_{row['name']}"]
                sync_df.at[i, 'is_present'] = str(curr_state).upper()
            
            # 1. 구글 시트 물리적 업데이트
            conn.update(data=sync_df)
            
            # 2. 현재 세션 데이터프레임도 즉시 갱신 (새로고침 없이 바로 반영)
            st.session_state.master_df = sync_df
            
            st.success("✅ 시트에 반영되었습니다! 이제 새로고침해도 이 상태가 유지됩니다.")
            # rerun을 하지 않고 상태만 유지함

    st.divider()

    # --- 팀 나누기 로직 ---
    if st.button("🔥 최적 밸런스 팀 나누기"):
        if len(selected_players) < 2:
            st.error("🚨 참석자를 선택해 주세요.")
        else:
            # (팀 나누기 시뮬레이션 및 결과 출력 로직은 동일)
            n = len(selected_players)
            all_combos = list(combinations(range(n), n // 2))
            samples = random.sample(all_combos, min(len(all_combos), 5000))
            def get_score(team):
                return sum((p["skill"]*1.5 + p["stamina"]*0.5) * (0.85 if p["injury"]==1 else 0.5 if p["injury"]==2 else 1) for p in team)
            best_t1_idx = min(samples, key=lambda c: abs(get_score([selected_players[i] for i in c]) - get_score([selected_players[i] for i in range(n) if i not in c])))
            t1, t2 = [selected_players[i] for i in best_t1_idx], [selected_players[i] for i in range(n) if i not in best_t1_idx]
            c1, c2 = st.columns(2); c1.info(f"### 🔵 A팀 ({len(t1)})"); c2.warning(f"### 🟠 B팀 ({len(t2)})")
            for p in t1: c1.write(f"**{p['name']}**");
            for p in t2: c2.write(f"**{p['name']}**");
            
            # 결과 저장 시에도 세션 갱신
            final_df = st.session_state.master_df.copy()
            for idx, row in final_df.iterrows():
                if row['name'] in [p['name'] for p in t1]: final_df.at[idx, 'last_team'] = "A"
                elif row['name'] in [p['name'] for p in t2]: final_df.at[idx, 'last_team'] = "B"
            conn.update(data=final_df)
            st.session_state.master_df = final_df
            st.success("✅ 팀 결과가 저장되었습니다.")
