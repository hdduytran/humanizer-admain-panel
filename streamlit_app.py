from datetime import datetime, timedelta, time, date
import numpy as np
import streamlit as st
import pandas as pd
import pymongo
import streamlit_authenticator as stauth
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from telegram_handler import TelegramHandler

from pytz import timezone
import yaml
from yaml.loader import SafeLoader
from dotenv import load_dotenv
import os

load_dotenv()

COLUMNS = [
    "user_id",
    "total_used",
    "interval_time",
    "expiry_date",
    "sub_type",
    "created_time",
    "created_by",
    "updated_by",
    "last_used",
    "level",
    "active",
]

# Connect to MongoDB


@st.cache_resource
def init_connection():
    return pymongo.MongoClient(os.getenv("MONGO_URI"))


client = init_connection()

# Select the database
db = client["Humanizer"]
col_users = db["users"]
col_admin = db["admin"]
telegram_handler = TelegramHandler(os.getenv("BOT_TOKEN_HUMANIZER"))


def create_user(user):
    col_users.insert_one(user)


def get_users():
    current_time = datetime.now()
    return col_users.find(
        {
            "active": True,
            "$or": [
                {"expiry_date": {"$gte": current_time}},
                {"num_slots": {"$gt": 0}}
            ]
        },
        projection=COLUMNS,
        sort=[("updated_time", pymongo.ASCENDING)],
    )


def get_user(user_id):
    return col_users.find_one({"user_id": user_id})


def update_user(user_id, user):
    col_users.update_one({"user_id": user_id}, {"$set": user}, upsert=True)


def get_admin():
    return col_admin.find({})


st.write("Welcome to Humanizer")
with open("./config.yaml") as file:
    config = yaml.load(file, Loader=SafeLoader)
config["credentials"]["usernames"]["admin"]["password"] = os.getenv("ADMIN-PASSWORD")
config["credentials"]["usernames"]["admin"]["password"] = "Duy@254"
admin_user = list(get_admin())
for user in admin_user:
    config["credentials"]["usernames"][user["username"]] = {
        "password": user["password"],
        "logged_in": False,
        "email": "random@gmail.com",
        "name": "random",
    }
print(config)


authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
    config["preauthorized"],
)

authenticator.login()
if st.session_state["authentication_status"]:
    st.write(f"### Welcome {st.session_state['username']}")
    authenticator.logout()
    # Toggle
    if st.session_state["username"] == "admin":
        with st.expander("# Send message to all user"):
            st.markdown("# Send message to all users")
            message = st.text_area("Enter message")
            if st.button("Send message"):
                user_ids = [user["user_id"] for user in get_users()]
                telegram_handler.notify_all(message, user_ids)
                st.write("Message sent successfully")

    st.write("# Create a new user")
    user_ids = st.text_input("Enter user_id")

    cols1 = st.columns(2)
    with cols1[0]:
        options = {
            "3 hours": timedelta(hours=3),
            # "0 days (slots plan)": timedelta(days=0) + timedelta(days=0),
            "1 day": timedelta(days=1) +     timedelta(days=1),
            "1 week": timedelta(weeks=1) + timedelta(days=1),
            "2 weeks": timedelta(weeks=2) + timedelta(days=1),
            "1 month": timedelta(days=31) + timedelta(days=1),
        }
        selected_option = st.selectbox(
            "Choose expiry duration (From Now)", list(options.keys())
        )

        d = datetime.now() + options[selected_option]
        if selected_option != "3 hours":
            d = datetime.combine(d - timedelta(days=1), time(21, 0))
        expiry_date = st.date_input("Or choose an exact date", d)
        if selected_option == "3 hours":
            print("Selected 3 hours", expiry_date, d.time())
            expiry_date = datetime.combine(expiry_date, d.time())
        else:
            expiry_date = datetime.combine(expiry_date, time(21, 0))


        # convert datetime.date to datetime
    with cols1[1]:
        interval_time = st.number_input(
            "Enter interval time", min_value=10, max_value=3600, value=100, step=10
        )
        
        # num_slots = st.number_input(
        #     "Enter number of slots to add", min_value=0, max_value=10000, value=1, step=1
        # )

    user_ids = user_ids.split(" ")

    cols = st.columns(2)

    with cols[0]:
        if st.button("Create/Update user (with slots)"):
            for user_id in user_ids:
                user_id = user_id.strip()
                if user_info := get_user(user_id):
                    user = {
                        "user_id": user_id,
                        "active": True,
                        "sub_type": selected_option,
                        "updated_time": datetime.now(),
                        "updated_by": st.session_state["username"],
                        "created_by": st.session_state["username"],
                        # "num_slots": num_slots,
                        "expiry_date": expiry_date,
                        "interval_time": interval_time,
                    }
                    if user_info.get("blocked"):
                        st.write(f"User {user_id} is blocked, no action taken")
                    else:
                        update_user(user_id, user)
                        st.write(f"User {user_id} already exists, updated user")
                else:
                    user = {
                        "user_id": user_id,
                        "active": True,
                        "sub_type": selected_option,
                        "created_time": datetime.now(),
                        "created_by": st.session_state["username"],
                        "updated_by": st.session_state["username"],
                        # "num_slots": num_slots,
                        "updated_time": datetime.now(),
                        "expiry_date": expiry_date,
                        "interval_time": interval_time,
                    }

                    create_user(user)
                    st.write(f"User {user_id} created successfully")
    with cols[1]:
        if st.button("Update Interval Time"):
            for user_id in user_ids:
                user_id = user_id.strip()
                user = {
                    "interval_time": interval_time,
                    "updated_time": datetime.now(),
                    # "num_slots": num_slots,
                    "updated_by": st.session_state["username"],
                }
                update_user(user_id, user)
                st.write(f"User {user_id} updated successfully")

    if st.session_state["username"] == "admin":

        st.write("# All users")

        users = list(get_users())
        if not users:
            st.write("No users found")
        else:
            df = pd.DataFrame(users)
            df = df.drop(columns=["_id"])

            # remove users
            remove_user_list = st.multiselect(
                "Select users to remove", list(df["user_id"])
            )
            if st.button("Remove users"):
                for user in remove_user_list:
                    update_user(
                        user,
                        {
                            "active": False,
                            "updated_time": datetime.now(),
                            "updated_by": st.session_state["username"],
                        },
                    )
                    st.write(f"{user} removed successfully")

            users = list(get_users())
            df = pd.DataFrame(users)
            if "_id" in df.columns:
                df = df.drop(columns=["_id"])
            # reordering columns
            # add columns if not exist
            for column in COLUMNS:
                if column not in df.columns:
                    df[column] = None
            df = df[COLUMNS]
            # covert last_used  from timestamp to datetime
            # timezone: EAT
            target_timezone = timezone("Africa/Nairobi")
            df["last_used"] = pd.to_datetime(df["last_used"], unit="s")
            df["last_used"] = (
                df["last_used"].dt.tz_localize("UTC").dt.tz_convert(target_timezone)
            )
            # df['created_time'] = df['created_time'].dt.tz_localize(
            #     'UTC').dt.tz_convert(target_timezone)
            df["expiry_date"] = (
                df["expiry_date"].dt.tz_localize("UTC").dt.tz_convert(target_timezone)
            )
            st.dataframe(df)
    st.markdown("# Delete/Block user")
    user_ids = st.text_input("Enter user_id to delete/block")
    user_ids = user_ids.split(" ")
    cols = st.columns(2)
    with cols[0]:
        if st.button("Delete user"):
            for user_id in user_ids:
                user_id = user_id.strip()
                update_user(
                    user_id,
                    {
                        "active": False,
                        "updated_time": datetime.now(),
                        "updated_by": st.session_state["username"],
                    },
                )
                st.write(f"{user_id} deleted successfully")
    with cols[1]:
        if st.button("Block user"):
            for user_id in user_ids:
                user_id = user_id.strip()
                update_user(
                    user_id,
                    {
                        "active": False,
                        "updated_time": datetime.now(),
                        "updated_by": st.session_state["username"],
                        "blocked": True,
                    },
                )
                st.write(f"{user_id} blocked successfully")

elif st.session_state["authentication_status"] is False:
    st.error("username/password is incorrect")
elif st.session_state["authentication_status"] is None:
    st.warning("Please enter your username and password")
