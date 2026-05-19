import os
from pymongo import MongoClient

uris = [
    # 1. URL encoded password with `<Myproject_io5>` as password (i.e. %3CMyproject_io5%3E) on cluster0
    "mongodb+srv://user_db:%3CMyproject_io5%3E@cluster0.yb7i3nt.mongodb.net/meowie_crm?retryWrites=true&w=majority",
    # 2. URL encoded password on cluaster0
    "mongodb+srv://user_db:%3CMyproject_io5%3E@cluaster0.yb7i3nt.mongodb.net/meowie_crm?retryWrites=true&w=majority",
]

for i, uri in enumerate(uris, 1):
    print(f"Testing URL Encoded URI #{i}...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command('ping')
        print(f"-> SUCCESS! URL Encoded URI #{i} connected perfectly.")
        break
    except Exception as e:
        print(f"-> Failed: {type(e).__name__} - {str(e)}")
