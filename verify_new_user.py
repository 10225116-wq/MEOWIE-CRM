import os
from pymongo import MongoClient

MONGO_URI = 'mongodb+srv://user_db:Myproject_io5@cluster0.yb7i3nt.mongodb.net/'

try:
    print("Connecting to MongoDB Atlas...")
    client = MongoClient(MONGO_URI)
    db = client.get_database('meowie_crm')
    users = list(db.users.find({}, {'password': 0})) # Hide password
    print("Connection Successful!")
    print(f"Total users found in 'meowie_crm.users': {len(users)}")
    for user in users:
        print("- User:", user)
except Exception as e:
    print("Failed to query database:", type(e).__name__, "-", str(e))
