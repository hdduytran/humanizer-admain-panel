from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import pymongo
import streamlit_authenticator as stauth
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram_handler import TelegramHandler

from pytz import timezone

import yaml
from yaml.loader import SafeLoader
from dotenv import load_dotenv
import os
load_dotenv()

COLUMNS = ["user_id", "total_used", "interval_time",
           "created_time", "expiry_date", "last_used",  "active"]

# Connect to MongoDB


@st.cache_resource
def init_connection():
    return pymongo.MongoClient(os.getenv("MONGO_URI"))


client = init_connection()

# Select the database
db = client["Turnitin"]
col_users = db["users"]
telegram_handler = TelegramHandler(os.getenv("BOT_TOKEN_HUMANIZER"))


def create_user(user):
    col_users.insert_one(user)


def get_users():
    return col_users.find({"active": True}, sort=[("updated_time", pymongo.ASCENDING)])


def get_user(user_id):
    return col_users.find_one({'user_id': user_id})


def update_user(user_id, user):
    col_users.update_one({'user_id': user_id}, {'$set': user}, upsert=True)


st.write('Welcome to Turnitin')

with open('./config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)
print(config)
config['credentials']['usernames']["admin"]["password"] = os.getenv(
    "ADMIN-PASSWORD")
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
    # Toggle
    with st.expander("# Send message to all user"):
        st.markdown("# Send message to all users")
        message = st.text_area('Enter message')
        if st.button('Send message'):
            user_ids = [user['user_id'] for user in get_users()]
            telegram_handler.notify_all(message, user_ids)
            st.write('Message sent successfully')
        
    st.write('# Create a new user')
    user_ids = st.text_input('Enter user_id')
    
    cols1 = st.columns(2)
    with cols1[0]:
        expiry_date = st.date_input('Enter expiry date (default: 7)', datetime.now() + timedelta(days=7))
        # convert datetime.date to datetime
        expiry_date = datetime.combine(expiry_date, datetime.min.time())
    with cols1[1]:
        interval_time = st.number_input(
            'Enter interval time', min_value=30, max_value=3600, value=300, step=30)
    user_ids = user_ids.split(' ')
    
    cols = st.columns(2)
    
    with cols[0]:
        if st.button('Create/Update user'):
            for user_id in user_ids:
                user_id = user_id.strip()
                if get_user(user_id):
                    user = {
                        "user_id": user_id,
                        "active": True,
                        'updated_time': datetime.now(),
                        'expiry_date': expiry_date,
                        'interval_time': interval_time
                    }
                    update_user(user_id, user)
                    st.write(f'User {user_id} already exists, updated user')
                else:
                    user = {
                        'user_id': user_id,
                        "active": True,
                        'created_time': datetime.now(),
                        'updated_time': datetime.now(),
                        'expiry_date': expiry_date,
                        'interval_time': interval_time
                    }

                    create_user(user)
                    st.write(f'User {user_id} created successfully')
    with cols[1]:         
        if st.button("Update Interval Time"):
            for user_id in user_ids:
                user_id = user_id.strip()
                user = {
                    'interval_time': interval_time,
                    'updated_time': datetime.now()
                }
                update_user(user_id, user)
                st.write(f'User {user_id} updated successfully')

    st.write('# All users')
    users = list(get_users())
    if not users:
        st.write('No users found')
    else:
        df = pd.DataFrame(users)
        df = df.drop(columns=['_id'])

        # remove users
        remove_user_list = st.multiselect(
            'Select users to remove', list(df['user_id']))
        if st.button('Remove users'):
            for user in remove_user_list:
                update_user(
                    user, {'active': False, 'updated_time': datetime.now()})
                st.write(f'{user} removed successfully')

            users = list(get_users())
            df = pd.DataFrame(users)
            if "_id" in df.columns:
                df = df.drop(columns=['_id'])

        # reordering columns
        # add columns if not exist
        for column in COLUMNS:
            if column not in df.columns:
                df[column] = None
        df = df[COLUMNS]
        # covert last_used  from timestamp to datetime
        # timezone: EAT
        target_timezone = timezone('Africa/Nairobi')
        df['last_used'] = pd.to_datetime(df['last_used'], unit='s')
        df['last_used'] = df['last_used'].dt.tz_localize(
            'UTC').dt.tz_convert(target_timezone)
        df['created_time'] = df['created_time'].dt.tz_localize(
            'UTC').dt.tz_convert(target_timezone)
        df['expiry_date'] = df['expiry_date'].dt.tz_localize(
            'UTC').dt.tz_convert(target_timezone)
        st.dataframe(df)

elif st.session_state["authentication_status"] is False:
    st.error('username/password is incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')
