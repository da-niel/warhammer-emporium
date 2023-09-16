import re, base64

import streamlit as st
import pandas as pd

from snowflake import snowpark

st.set_page_config(
    layout='wide'
)

# DICE_ROLL to PROBABILITY mapping
    # if you need a 2 or higher, that corresponds to a 5 (out of 6) chance
PROB_MAP = {
    1:6, 
    2:5,
    3:4,
    4:3,
    5:2,
    6:1
}

@st.cache_resource
def build_session(params):
    return snowpark.Session.builder.configs(params).create()

@st.cache_data
def get_data(query):
    return session.sql(query).to_pandas()

def get_url(stage, unit, page, df):
    path = df[df.RELATIVE_PATH.str.contains(f"{unit} \({page}\)")].RELATIVE_PATH.values[0]
    url_df = get_data(f"select BUILD_STAGE_FILE_URL( @{stage} , '{path}') as url")
    return url_df.iloc[0,0]

def base64_to_image(encoded_string):
    return base64.b64decode(encoded_string)

def calculateHits(series: pd.Series, hit_modifier:int, save_roll: int, wound_roll:int = None):
    net_bs = series.BS - hit_modifier
    hits = dict()
    for p, q in PROB_MAP.items():
        nHits = (
            series.A 
            * (PROB_MAP[net_bs] / 6)
            * (q / 6)
            * (min(PROB_MAP[save_roll] / 6, 1))
        ).round(2)
        hits[f"{p}+"] = [nHits]
    
    return hits


remove_int = lambda s: re.sub(r'\d', '', s)

def process_keyword(kw):
    kw = remove_int(kw).strip()
    if "anti" in kw.lower():
        kw = "Anti"
    elif kw.lower().endswith(("x", "+")):
        kw = " ".join(kw.split(" ")[:-1])
    
    return kw

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

st.write("# Warhammer")

if not st.session_state["authenticated"]:
    welcome_screen = st.empty()

    with welcome_screen:
        c, _ = st.columns((2,3))
        with c:
            with st.form("Credentials"):
                username = st.text_input("Username")
                password = st.text_input("Password", type='password')

                login = st.form_submit_button("Login")

    if login:
        params = {
            "account": st.secrets.snowflake_warhammer["ACCOUNT"],
            "user": username,
            "password": password,
            "database": st.secrets.snowflake_warhammer["DATABASE"],
            "schema": st.secrets.snowflake_warhammer["SCHEMA"]
        }  

        # Session and data
        session = build_session(params)
        welcome_screen.empty()
        st.session_state['authenticated'] = True


if not st.session_state.authenticated:
    st.stop()

tables = {
    "units": None,
    "weapons": None,
    "keywords": None,
    "images": None
}

progress = st.progress(0, "Loading Data...")

for i, table in enumerate(tables.keys()):
    tables[table] = get_data(f"select * from dim_{table}")
    progress.progress(i / len(tables), "Loading Data...")

progress.empty()

all_units, weapons, keywords, images = tables.values()

all_units.set_index("NAME", inplace=True)
weapons.set_index("WEAPONS", inplace=True)
keywords.set_index("ABILITY", inplace=True)
images.set_index("NAME", inplace=True)

# Sidebar
with st.sidebar:
    st.write ("### Options")
    faction = st.selectbox("Select Faction", options = all_units.RACE.unique())
    show_image = st.checkbox("Show datasheet as image", value = True)
    show_table = st.checkbox("Show datasheet as text", value = False)
    show_page_two = st.checkbox("Show second page", value = False)
    show_damage_calc = st.checkbox("Show Damage Calc", value = False)
    
    kwd = st.multiselect('Keyword Definions', options = keywords.index)

    if kwd:
        st.write(keywords.loc[kwd])

    width = st.slider("Reduce info sheet width", min_value = 1, max_value = 1000)


left, main, _ = st.columns([3, 7, 0.01*width])

# filter out units
units = all_units.query(f"RACE == '{faction}'")

with left:
    f'# {faction.capitalize()}'

    selected_units = st.multiselect(label = 'Units', options = units.index.unique())

    skw_list = []
    for kws in weapons.loc[weapons.UNITS.isin(selected_units)].KEYWORDS:
        skw_list.extend(kws.split(","))

    skw_set = {process_keyword(kw) for kw in skw_list}

    # show keywords
    st.write("### Keywords")
    for kw in skw_set:
        if kw.lower() != 'none':
            try:
                st.write(f"**{kw}**")
                st.write(keywords.loc[kw].values[0])
            except:
                pass

# Show Stats
with main:
    # for spacing
    st.write("# ")
    st.write("# ")

    for selected_unit in selected_units:
        su_df = units[units.index == selected_unit] # selected_unit df
        sw_df = weapons[weapons.UNITS == selected_unit] # selected_weapon df
        with st.expander(selected_unit, expanded= True):
            if show_image:
                try:
                    page_1 = base64_to_image(images.loc[f"{selected_unit} (1)"].IMAGE_ENCODED)
                    st.image(page_1)
                    if show_page_two:
                        page_2 = base64_to_image(images.loc[f"{selected_unit} (2)"].IMAGE_ENCODED)
                        st.image(page_2)
                except Exception as e:
                    print(e)
            
            if show_table:
                st.write(su_df.select_dtypes(include='number'))
                for col in su_df.select_dtypes(exclude='number'):
                    st.markdown(f"**{col}**")
                    st.write(su_df[col].values[0])

            
            if show_damage_calc:
                st.write("#### Expected Hits")
                # modifiers
                c1, c2, c3, c4 = st.columns(4)
                hit_modifier = c1.number_input("Net Hit Modifier", min_value = -1, max_value = 1, value = 0, step = 1)
                # wound_roll = c2.number_input("Wound Roll", min_value = -1, max_value = 1, value = 0, step = 1)
                save_roll = c3.number_input("Save Roll", min_value = 2, max_value = 6, value = 3, step=1)
                # feel_no_pain = c4.number_input("Feel No Pain", min_value = 2, max_value = 7, value = 7, step = 1)
                # display
                c1, c2, c3 = st.columns(3)
                n_models = c1.number_input("Num. Models Attacking", min_value = 1, value = 1, step = 1)
                unit_weapons = sw_df[sw_df.UNITS == selected_unit]
                for weapon in unit_weapons.index:
                    st.markdown(f"**Expected Hits with {weapon} and wound roll of**")
                    expected_hits = calculateHits(
                        unit_weapons.loc[weapon],
                        hit_modifier=hit_modifier,
                        # wound_roll,
                        save_roll=save_roll
                    )
                    st.write(pd.DataFrame(expected_hits)*n_models)