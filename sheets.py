# sheets.py
import gspread
import streamlit as st
import pandas as pd
import bcrypt
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
import plotly.express as px

st.set_page_config(page_title="Smart Records", page_icon='📚', layout='wide', initial_sidebar_state='expanded')
st.image("assets/diligent_header.png")
with open("assets/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

USERS = {
    "Admin": bcrypt.hashpw(b"Lumination1", bcrypt.gensalt()).decode(),
    "Store Manager": bcrypt.hashpw(b"manager456", bcrypt.gensalt()).decode(),
}

def login(username, password):
    hashed = USERS.get(username)
    if hashed and bcrypt.checkpw(password.encode(), hashed.encode()):
        return True
    return False

@st.cache_resource
def get_gsheet_connection(sheet_id, worksheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(worksheet_name)
    return worksheet

@st.cache_data()
def load_data():
    worksheet = get_gsheet_connection(sheet_id="12LY8vB0zusaZORz4CxuxyUjSaBA22FN44t-7-srh3V4", worksheet_name="Inventory")
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""

if not st.session_state.authenticated:
    with st.form("Login Form"):
        st.subheader("🔐 Login")
        username = st.selectbox("Username", options=list(USERS.keys()))
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit:
            if login(username, password):
                st.session_state.authenticated = True
                st.session_state.current_user = username
                st.success("✅ Login Successful")
                st.rerun()
            else:
                st.error("❌ Invalid Username or Password")

if st.session_state.authenticated:
    # col_title, col_logout = st.columns([9, 1])
    with st.sidebar:
        st.write(f"👤 Welcome! {st.session_state.current_user}")
        if st.button("Log Out"):
            st.session_state.authenticated = False
            st.session_state.current_user = ""
            st.rerun()

    worksheet = get_gsheet_connection(sheet_id="12LY8vB0zusaZORz4CxuxyUjSaBA22FN44t-7-srh3V4", worksheet_name="Inventory")
    df_stock_inventory = load_data()
    df_stock_inventory.dropna(subset=["Materials"], inplace=True)

    tab1, tab2 = st.tabs(["📝 Stock Inventory", "📊 Reports"])

    with tab1:
        with st.container(border=True):
            df_total_material = get_gsheet_connection(sheet_id="1fdcDcwTTTRE34Egr8ybWeOfbfttYbEsUMeLaHWjO4Ig", worksheet_name="Data").get_all_records()
            df_total_material = pd.DataFrame(df_total_material)

            # df_total_material = pd.read_excel("NYANDARUA MATERIALS.xlsx")
            stock_filter = df_stock_inventory.copy()
            materials_list = stock_filter["Materials"].unique()
            site_names = df_total_material["SCHEME NAME"].unique()
            team = stock_filter["Issued To"].unique()

            col1, col2, col3 = st.columns(3)
            actions = ["Issue Materials", "Record Supply", "Delete Inventory Record"]
            col4, col5 = st.columns(2)
            select = col4.radio("****Select Action****", actions, help="Choose inventory action")

        if select == "Delete Inventory Record":
            job_id = st.number_input("Delete Job ID:")
            def delete_row_by_id(sheet_id, worksheet_name, id_to_delete):
                worksheet = get_gsheet_connection(sheet_id, worksheet_name)
                all_data = worksheet.get_all_records()
                for idx, row in enumerate(all_data, start=2):
                    if str(row.get("Id")) == str(id_to_delete):
                        worksheet.delete_rows(idx)
                        return True
                return False

            if col5.button(f"Delete Inventory Id: {job_id}"):
                success = delete_row_by_id(sheet_id="12LY8vB0zusaZORz4CxuxyUjSaBA22FN44t-7-srh3V4", worksheet_name="Inventory", id_to_delete=job_id)
                if success:
                    st.success("✅ Record deleted from Google Sheet.")
                    st.rerun()
                else:
                    st.error("⚠️ No matching record found.")

        else:
            selected_materials = col5.multiselect("Select Materials", materials_list)
            if selected_materials:
                stock_track = df_stock_inventory[df_stock_inventory["Materials"].isin(selected_materials)]
                stock_track["Quantity Supplied"] = pd.to_numeric(stock_track["Quantity Supplied"], errors='coerce').fillna(0)
                stock_track["Quantity Issued"] = pd.to_numeric(stock_track["Quantity Issued"], errors='coerce').fillna(0)
                total_qty_supply = stock_track["Quantity Supplied"].sum()
                total_qty_issue = stock_track["Quantity Issued"].sum()
                total_qty_balance = int(total_qty_supply) - int(total_qty_issue)

                if not df_stock_inventory.empty:
                    col1.metric(label="Total Quantity Supplied", value=total_qty_supply)
                    col2.metric(label="Total Quantity Issued", value=total_qty_issue)
                    col3.metric(label="Total Quantity Remaining in Store", value=total_qty_balance)
                else:
                    col5.warning(f"No Supply Records Found For: {selected_materials}")

        if select == "Issue Materials":
            with st.form("Inventory form"):
                issue_scheme = col5.selectbox("**Select Scheme Name**", site_names, key="issue_scheme", help="Where are materials being issued to?")
                col1, col2 = st.columns(2)
                issue_date = col2.date_input("Issue Date", value=datetime.today())
                issued_to = col2.text_input("Issued To (Team Leader Name)", placeholder="Name")
                issue_records = []
                for material in selected_materials:
                    with col1:
                        qty = st.number_input(f"{material}", min_value=0, step=1, key=f"issue_qty_{material}")
                    if qty > 0:
                        issue_records.append({"scheme_name": issue_scheme, "Material Description": material, "quantity_issued": qty, "issued_to": issued_to, "issue_date": issue_date.strftime('%Y-%m-%d')})

                submitted = st.form_submit_button("✅ Submit All Issues")
                if submitted and issue_records:
                    for record in issue_records:
                        worksheet.append_row(["", record["scheme_name"], record["Material Description"], record["quantity_issued"], record["issued_to"], record["issue_date"], "", "", "", ""])
                    st.success("✅ Issues recorded successfully!")
                elif submitted:
                    st.warning("⚠️ Please enter quantity for at least one material.")

        if select == "Record Supply":
            with st.form("multi_material_form"):
                st.subheader("📦 Record Multiple Material Supplies")
                col1, col2 = st.columns([2, 1])
                with col2:
                    driver = st.text_input("Driver:", key="driver")
                    truck = st.text_input("Truck No.:)", key="truck")
                    supply_date = st.date_input("Supply Date", value=datetime.today(), key="date")
                supply_records = []
                for material in selected_materials:
                    with col1:
                        qty = st.number_input(f"Quantity for {material}", min_value=0, step=1, key=f"qty_{material}")
                    if qty > 0:
                        supply_records.append({"Material Description": material, "quantity_supplied": qty, "supply_date": supply_date.strftime('%Y-%m-%d'), "driver": driver, "truck": truck})

                submitted = st.form_submit_button("✅ Submit All Supplies")
                if submitted and supply_records:
                    for record in supply_records:
                        worksheet.append_row(["", "", record["Material Description"], "", "", "", record["quantity_supplied"], record["supply_date"], record["driver"], record["truck"]])
                    st.success("✅ Supplies recorded successfully!")
                elif submitted:
                    st.warning("⚠️ Please enter quantity for at least one material.")

    with tab2:
        st.dataframe(df_stock_inventory, use_container_width=True)
        st.download_button(label="📥 Download Data", data=df_stock_inventory.to_csv(index=False), file_name="inventory.csv", mime="text/csv")
