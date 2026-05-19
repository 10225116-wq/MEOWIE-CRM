import os
from pymongo import MongoClient

MONGO_URI = 'mongodb://atlas-sql-6a0a6adc69f3d3d1b22218fa-gqtiua.g.query.mongodb.net/sample_analytics?ssl=true&authSource=admin'

try:
    print("Connecting to MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.get_database('sample_analytics')
    print("Attempting to read from 'users' collection...")
    user = db.users.find_one()
    print("Success! First user:", user)
except Exception as e:
    print("Failed with error:", type(e).__name__, "-", str(e))
