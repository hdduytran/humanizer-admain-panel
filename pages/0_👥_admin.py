from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import pymongo
import streamlit_authenticator as stauth
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram_handler import TelegramHandler

from pytz import timezone
import time
import yaml
from yaml.loader import SafeLoader
from dotenv import load_dotenv
import os
load_dotenv()


@st.cache_resource
def init_connection():
    return pymongo.MongoClient(os.getenv("MONGO_URI"))

client = init_connection()

db = client["Humanizer"]
col_admin = db["admin"]


def get_admin():
    return col_admin.find({})
def new_admin(username, password):
    col_admin.insert_one({"username": username, "password": password})
def delete_admin(username):
    col_admin.delete_one({"username": username})

with open('./config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)
config['credentials']['usernames']["admin"]["password"] = os.getenv(
    "ADMIN-PASSWORD")

print(config)


authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

authenticator.login()
if st.session_state["authentication_status"]:
    authenticator.logout()
    if st.session_state["username"] != "admin":
        st.write("# You are not authorized to access this page.")
        st.stop()
    else:
        st.write("# Welcome Super admin")
        st.write("## Here are the list of all admins")
        all_admin = get_admin()
        df = pd.DataFrame(all_admin)
        df = df[["username", "password"]]
        st.write(df)
        
        st.write("## Add new admin")
        username = st.text_input("Username", key="username_add")
        password = st.text_input("Password")
        if st.button("Add"):
            new_admin(username, password)
            st.write("Admin added successfully. Please refresh the page to see the changes.")
            
        st.write("## Delete admin")
        username = st.text_input("Username", key="username_delete")
        if st.button("Delete"):
            delete_admin(username)
            st.write("Admin deleted successfully. Please refresh the page to see the changes.")
else:
    st.write("# You are not authorized to access this page..")
    st.stop()