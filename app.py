import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import random
from itertools import combinations

# 1. 페이지 설정
st.set_page_config(page_title="TERA FC 매니저 V2.8", page_icon="⚽", layout="wide")

# 2. 구글 시트 연결 및 데이터 로드 로직
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        # 시트 데이터 읽기
        data = conn.read(ttl=0)
        data = data.dropna(subset=['name']).drop_duplicates(subset=['name']).reset_index(drop=True)
        
        # 필수 컬럼이 없을 경우 자동 생성
        for col in ['skill', 'stamina', 'last_team', 'is_present']:
            if col not in data.columns:
                data[col] = "" if col in ['last_team', 'is_present'] else 10
        
        # 🔥 [중요] 타입 에러 방지: 모든 컬럼을 문자열로 변환하여 처리
        # 특히 빈 칸(NaN)이 숫자로 인식되어 생기는 TypeError를 방지합니다.
        data = data.fillna("") # 빈 칸을 빈 문자열로 채움
        data = data.astype(str)
        
        # 실력과 체력은 계산을 위해 다시 숫자로 변환
        data['skill'] = pd.to_numeric(data['skill'], errors='coerce').fillna(10)
        data['stamina'] = pd.to_numeric(data['stamina'], errors='coerce').fillna(10)
        
        return data
    except Exception as e:
        st.error(f"⚠️ 데이터 로드 실패: {e}")
        return pd.DataFrame(columns=['name', 'skill', 'stamina', 'last_team', 'is_present'])

df = load_data()

# 3. 사이드바: 명단 관리
with st.sidebar:
    st.title("⚙️ 명단 관리")
    with st.expander("👤 선수 등록/삭제", expanded=False):
        st.subheader("신규 선수")
        n_name = st.text_input("이름", key="new_player_name")
        c1, c2 = st.columns(2)
        n_skill = c1.slider("실력", 1, 20, 10)
        n_stam = c2.slider("체력", 1, 20, 10)
        
        if st.button("✅ 선수 추가"):
            if n_name and n_name not in df['name'].values:
                new_row = pd.DataFrame([{"name": n_name, "skill": n_skill, "stamina": n_stam, "last_team": "", "is_present": "TRUE"}])
                # 기존 데이터와 합치기 전 타입 통일
                updated_list = pd.concat([df, new_row], ignore_index=True)
                conn.update(data=updated_list)
                st.success(f"{n_name} 등록 완료!")
                st.rerun()

        st.divider()
        if not df.empty:
            d_name = st.selectbox("삭제 대상", df["name"].tolist())
            if st.button("🗑️ 삭제"):
                conn.update(data=df[df["name"] != d_name])
                st.rerun()

# 4. 메인 화면
st.title("⚽ TERA FC 매니저 V2.8")
st.caption("참석 정보와 팀 결과가 구글 시트에 안전하게 기록됩니다.")

if df.empty:
    st.info("📢 등록된 선수가 없습니다. 사이드바에서 선수를 추가해 주세요!")
else:
    st.subheader("1. 오늘 경기 참석자 체크")
    selected_players = []
    cols = st.columns(4)
    
    # 참석 여부 실시간 동기화용
    updated_df = df.copy()
    needs_sync = False

    for i, row in df.iterrows():
        with cols[i % 4]:
            with st.container(border=True):
                # 시트의 TRUE/FALSE 값을 읽어서 토글 상태 결정
                is_checked = True if str(row['is_present']).upper() == "TRUE" else False
                is_on = st.toggle(f"**{row['name']}**", value=is_checked, key=f"tgl_{row['name']}")
                
                # 토글 상태가 시트와 다르면 즉시 플래그 세우기
                if is_on != is_checked:
                    updated_df.at[i, 'is_present'] = str(is_on).upper()
                    needs_sync = True

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

    # 변경사항이 있으면 시트에 한 번만 업데이트
    if needs_sync:
        conn.update(data=updated_df)
        st.rerun()

    st.divider()

    # --- 팀 나누기 알고리즘 ---
    def get_team_score(team):
        score = 0
        for p in team:
            # 실력 중심 가중치 계산
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
                    penalty = get_repeat_penalty(t1, t2) * 0.5 # 중복 방지 가중치
                    
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

                # --- 결과를 시트에 영구 기록 ---
                final_df = df.copy()
                t1_names = [p['name'] for p in best_t1]
                t2_names = [p['name'] for p in best_t2]
                
                for idx, row in final_df.iterrows():
                    if row['name'] in t1_names:
                        final_df.at[idx, 'last_team'] = "A"
                    elif row['name'] in t2_names:
                        final_df.at[idx, 'last_team'] = "B"
                
                conn.update(data=final_df)
                st.success("✅ 팀 구성 결과가 시트에 저장되었습니다. (다음 경기 밸런스에 반영)")
