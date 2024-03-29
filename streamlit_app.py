import re, base64

import streamlit as st
import pandas as pd
import numpy as np

from snowflake import snowpark
from snowflake.connector.errors import DatabaseError


st.set_page_config(
    layout='wide',
    page_title='40k Emporium',
    page_icon=':books:'
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
def build_session():
    params = {
        "account": st.secrets.snowflake_warhammer["ACCOUNT"],
        "user": st.session_state['user'],
        "password": st.session_state["password"],
        "database": st.secrets.snowflake_warhammer["DATABASE"],
        "schema": st.secrets.snowflake_warhammer["SCHEMA"]
    }  

    return snowpark.Session.builder.configs(params).create()

def run_query(query):
    session = build_session()
    return session.sql(query).collect()

@st.cache_data
def get_data(query):
    session = build_session()
    return session.sql(query).to_pandas()

def base64_to_image(encoded_string):
    return base64.b64decode(encoded_string)

def calculate_hits(series: pd.Series, hit_modifier:int, save_roll: int, wound_roll:int = None):
    # series.A could be D3
    try:
        A = int(series.A)
    except ValueError:
        A = float(series.A[1:]) / 2 # D3 -> 1.5
    
    
    try:
        BS = int(series.BS)
    except ValueError:
        # series.BS could be N/A
        net_bs = 1
    else:
        net_bs = BS - hit_modifier

    hits = dict()
    for p, q in PROB_MAP.items():
        num_hits = round(
            A 
            * (PROB_MAP[net_bs] / 6)
            * (q / 6)
            * (1 - (PROB_MAP[save_roll] / 6))
            , 2
        )
        hits[f"{p}+"] = [num_hits]
    
    return hits


remove_int = lambda s: re.sub(r'\d', '', s)

def process_keyword(kw):
    kw = remove_int(kw).strip()
    if "anti" in kw.lower():
        kw = "Anti"
    elif kw.lower().endswith(("x", "+")):
        kw = " ".join(kw.split(" ")[:-1])
    
    return kw

def update_info(selected_unit:str):
    query = f"""
    update dim_units
        set M={st.session_state[f"{selected_unit}_M"]},
            T={st.session_state[f"{selected_unit}_T"]},
            SV={st.session_state[f"{selected_unit}_SV"]},
            ISV={st.session_state[f"{selected_unit}_ISV"]},
            W={st.session_state[f"{selected_unit}_W"]},
            LD={st.session_state[f"{selected_unit}_LD"]},
            OC={st.session_state[f"{selected_unit}_OC"]}
        where dim_units.NAME = '{selected_unit}'
    """

    return run_query(query)

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False


if not st.session_state["authenticated"]:
    welcome_screen = st.empty()

    with welcome_screen:
        c = st.columns((2,3))
        with c[0]:
            st.write(f"# The 40K Emporium")
            with st.form("Credentials"):
                username = st.text_input("Username")
                password = st.text_input("Password", type='password')

                login = st.form_submit_button("Login")

    if login:
        st.session_state['user'] = username
        st.session_state['password'] = password
        # Session and data
        try:
            session = build_session()
        except DatabaseError:
            st.error("Incorrent username and/or password")
        else:
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
    st.write(f"Greetings, {st.secrets[st.session_state['user']]['nickname']}")
    st.write("### Options")
    faction = st.selectbox("Select Faction", options = all_units.RACE.unique(), index=st.secrets[st.session_state['user']]['index'])
    show_image = st.checkbox("Show datasheet as image", value = True)
    expand_collapse = st.checkbox("Expand / Collapse All", value = True)
    show_table = st.checkbox("Show datasheet as text", value = False)
    show_page_two = st.checkbox("Show second page", value = False)
    show_damage_calc = st.checkbox("Show Damage Calc", value = False)
    # show_update_table = st.checkbox("Show Update Table", value = True)
    kwd = st.multiselect('Keyword Definions', options = keywords.index)
    if kwd:
        for k in kwd:
            st.write(f"### {k}")
            st.write(keywords.loc[k, "DEFINITION"])
    st.write("### Resources")
    st.markdown("[WH40k Downloads](https://www.warhammer-community.com/warhammer-40000-downloads/)")
    st.markdown("[Wahapedia Core Rules](https://wahapedia.ru/wh40k10ed/the-rules/core-rules/)")
    show_motto = st.checkbox(":eyes:", value = False)   


left, main = st.columns([2.5, 7])

# filter out units
units = all_units.query(f"RACE == '{faction}'")

# no bias here
MOTTO = {
    "Aeldari": "The Cool. The Awesome. The Aeldari.",
    "Orks": "The Green. The Ugly. The Orks.",
    "Chaos Space Marines": "The Few. The Weak. The Marines."
}

with left:
    f'# {faction}'
    if show_motto:
        st.caption(f'{MOTTO[faction]}')

    selected_units = st.multiselect(label = 'Units', options = units.index.unique())

    weapon_keywords_list = []
    for keywds in weapons.loc[weapons.UNITS.isin(selected_units)].KEYWORDS:
        try:
            weapon_keywords_list.extend(keywds.split(","))
        except AttributeError:
            print(f"No keyword found")

    character_keywords_list = []
    for keywds in units.loc[units.index.isin(selected_units)].CORE:
        try:
            character_keywords_list.extend(keywds.split(","))
        except AttributeError:
            print(f"No keyword found")

    weapon_keywords_set = {process_keyword(kw) for kw in weapon_keywords_list}
    character_keywords_set = {process_keyword(kw) for kw in character_keywords_list}

    unit_keywords_set = weapon_keywords_set.union(character_keywords_set)

    # show keywords
    st.write("### Keywords")
    for kw in unit_keywords_set:
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
        with st.expander(selected_unit, expanded= expand_collapse):
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
                st.caption("Does not account for any Weapon Abilities (e.g. Lethal Hits)")
                # modifiers
                c1, c2, c3, c4 = st.columns(4)
                hit_modifier = c1.number_input(
                    "Net Hit Modifier", 
                    min_value = -1, 
                    max_value = 1, 
                    value = 0, 
                    step = 1,
                    key=f'{selected_unit}_hit_modifier'
                )
                # wound_roll = c2.number_input("Wound Roll", min_value = -1, max_value = 1, value = 0, step = 1)
                save_roll = c3.number_input(
                    "Save Roll", 
                    min_value = 2, 
                    max_value = 6, 
                    value = 3, 
                    step=1,
                    key=f'{selected_unit}_save_roll'
                )
                # feel_no_pain = c4.number_input("Feel No Pain", min_value = 2, max_value = 7, value = 7, step = 1)
                # display
                c1, c2, c3 = st.columns(3)
                n_models = c1.number_input(
                    "Num. Models Attacking",
                    min_value = 1, 
                    value = 1, 
                    step = 1,
                    key=f'{selected_unit}_num_models'
                )
                unit_weapons = sw_df[sw_df.UNITS == selected_unit]
                used_weapons = c1.multiselect(
                    "Weapons", 
                    options = unit_weapons.index, 
                    default = list(unit_weapons.index),
                    key=f'{selected_unit}_used_weapons'
                )
                for weapon in used_weapons:
                    st.markdown(f"**Expected Hits with {weapon} and wound roll of**")
                    expected_hits = calculate_hits(
                        unit_weapons.loc[weapon],
                        hit_modifier=hit_modifier,
                        # wound_roll,
                        save_roll=save_roll
                    )
                    st.write(pd.DataFrame(expected_hits)*n_models)

            # if show_update_table:
            #     st.write("### Update Unit Stats")
            #     update_cols = ["M", "T", "SV", "ISV", "W", "LD", "OC"]

            #     with st.form(key=f"{selected_unit}_form"):
            #         update_st_cols = st.columns(len(update_cols))
            #         for i, col in enumerate(update_cols):
            #             value = su_df.loc[selected_unit, col].astype(int)

            #             if value < 0:
            #                 value = 0

                        
            #             update_st_cols[i].number_input(col, value = value, key=f"{selected_unit}_{col}")

            #         if st.form_submit_button("Update Info"):
            #             success = update_info(selected_unit)

            #             if success:
            #                 st.write("Success!")