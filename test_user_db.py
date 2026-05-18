import os
from pymongo import MongoClient

uris = [
    # 1. Without <> and with "cluster0"
    "mongodb+srv://user_db:Myproject_io5@cluster0.yb7i3nt.mongodb.net/meowie_crm?retryWrites=true&w=majority",
    # 2. With <> and with "cluster0"
    "mongodb+srv://user_db:<Myproject_io5>@cluster0.yb7i3nt.mongodb.net/meowie_crm?retryWrites=true&w=majority",
    # 3. Without <> and with typo "cluaster0"
    "mongodb+srv://user_db:Myproject_io5@cluaster0.yb7i3nt.mongodb.net/meowie_crm?retryWrites=true&w=majority",
    # 4. With <> and with typo "cluaster0"
    "mongodb+srv://user_db:<Myproject_io5>@cluaster0.yb7i3nt.mongodb.net/meowie_crm?retryWrites=true&w=majority"
]

for i, uri in enumerate(uris, 1):
    print(f"Testing URI #{i}...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        # Try pinging database
        client.admin.command('ping')
        print(f"-> SUCCESS! URI #{i} connected perfectly.")
        break
    except Exception as e:
        print(f"-> Failed: {type(e).__name__} - {str(e)}")
