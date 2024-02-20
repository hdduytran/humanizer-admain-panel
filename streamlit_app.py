from datetime import datetime
import streamlit as st
import pandas as pd
import pymongo
import streamlit_authenticator as stauth

import yaml
from yaml.loader import SafeLoader
from dotenv import load_dotenv
import os
load_dotenv()

# Connect to MongoDB
@st.cache_resource
def init_connection():
    return pymongo.MongoClient(os.getenv("MONGO_URI"))
client = init_connection()

# Select the database
db = client["Humanizer"]
col_users = db["users"]

# Create a new user


def create_user(user):
    col_users.insert_one(user)

# Get all users


def get_users():
    return col_users.find({"active":True}, sort=[("updated_time", pymongo.ASCENDING)])


def get_user(username):
    return col_users.find_one({'username': username})

def update_user(username, user):
    col_users.update_one({'username': username}, {'$set': user}, upsert=True)

# streamlit app
st.title('Humanizer')
st.write('Welcome to Humanizer')

with open('./config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)
print(config)
config['credentials']['usernames']["admin"]["password"] = os.getenv("ADMIN-PASSWORD")
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
    st.write('# Create a new user')
    usernames = st.text_input('Enter username')
    if st.button('Create user'):
        usernames = usernames.split(' ')
        for username in usernames:
            username = username.strip()
            if get_user(username):
                user = {
                    "username": username,   
                    "active": True,
                    'updated_time': datetime.now()
                }
                update_user(username, user)
                st.write(f'User {username} already exists, updated user')
            else:
                user = {
                    'username': username,
                    "active": True,
                    'created_time': datetime.now(),
                    'updated_time': datetime.now()
                }

                create_user(user)
                st.write(f'User {username} created successfully')
            
    st.write('# All users')
    users = list(get_users())
    if not users:
        st.write('No users found')
    else:
        df = pd.DataFrame(users)
        df = df.drop(columns=['_id'])

        # remove users
        remove_user_list = st.multiselect('Select users to remove', list(df['username']))
        if st.button('Remove users'):
            for user in remove_user_list:
                update_user(user, {'active': False, 'updated_time': datetime.now()})
                st.write(f'{user} removed successfully')
                
            users = list(get_users())
            df = pd.DataFrame(users)
            if "_id" in df.columns:
                df = df.drop(columns=['_id'])
        st.dataframe(df)
        
elif st.session_state["authentication_status"] is False:
    st.error('Username/password is incorrect')
elif st.session_state["authentication_status"] is None:
    st.warning('Please enter your username and password')