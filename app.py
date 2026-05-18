import os
from flask import Flask, request, jsonify, send_from_directory
import bcrypt
import jwt
import datetime
from functools import wraps
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient
from bson.objectid import ObjectId

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

# Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'fallback_secret')
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Database connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://user_db:Myproject_io5@cluster0.yb7i3nt.mongodb.net/')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database('meowie_crm')
users_collection = db.users

# --- Static File Serving ---
@app.route('/')
def serve_index():
    return send_from_directory('.', 'login.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# --- Authentication Routes ---
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'customer') # default to customer
    department = data.get('department') if role == 'manager' else None
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
        
    try:
        # Check if user exists
        if users_collection.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400
            
        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Save user to DB
        new_user = {
            'username': username,
            'password': hashed_password.decode('utf-8'),
            'role': role
        }
        if department:
            new_user['department'] = department
            
        result = users_collection.insert_one(new_user)
        
        return jsonify({'message': 'User created successfully', 'user_id': str(result.inserted_id)}), 201
    except Exception as e:
        print("Database error during signup:", str(e))
        return jsonify({'error': f'Database connection error: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    try:
        # Find user
        user = users_collection.find_one({'username': username})
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
            
        # Check password
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return jsonify({'error': 'Invalid credentials'}), 401
            
        # Generate token
        token = jwt.encode({
            'user_id': str(user['_id']),
            'username': user['username'],
            'role': user.get('role', 'customer'),
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, JWT_SECRET, algorithm='HS256')
        
        return jsonify({
            'message': 'Login successful', 
            'token': token,
            'role': user.get('role', 'customer')
        }), 200
    except Exception as e:
        print("Database error during login:", str(e))
        return jsonify({'error': f'Database connection error: {str(e)}'}), 500

# --- OpenAI Integration Route ---
# Decorator to check for JWT token
def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
            
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            current_user = users_collection.find_one({'_id': ObjectId(data['user_id'])})
            if not current_user:
                return jsonify({'error': 'User not found in database'}), 401
        except Exception as e:
            print("Token validation or database error:", str(e))
            return jsonify({'error': f'Authentication or database error: {str(e)}'}), 401
            
        return f(current_user, *args, **kwargs)
    return decorator

@app.route('/api/ai-chat', methods=['POST'])
@token_required
def ai_chat(current_user):
    data = request.json
    user_message = data.get('message')
    
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400
        
    # Check if API key is provided
    if not os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY') == 'your_api_key_here':
        return jsonify({
            'reply': 'System: OpenAI API Key is not configured in .env file.'
        }), 200
        
    # --- Narrow AI Knowledge Base ---
    keyword_one = [
        {"keyword": "late", "category": "Logistics", "issue": "Delayed Shipment"},
        {"keyword": "broken", "category": "Quality", "issue": "Damaged Item"},
        {"keyword": "refund", "category": "Finance", "issue": "Refund Request"},
        {"keyword": "password", "category": "IT", "issue": "Login Issue"},
        {"keyword": "fake", "category": "Quality", "issue": "Counterfeit Product"}
    ]
    
    keyword_sum = [
        {"phrase": "where is my order", "category": "Logistics", "issue": "Delayed Shipment"},
        {"phrase": "not working", "category": "Quality", "issue": "Defective Item"},
        {"phrase": "money back", "category": "Finance", "issue": "Refund Request"},
        {"phrase": "can't log in", "category": "IT", "issue": "Login Issue"},
        {"phrase": "poor quality", "category": "Quality", "issue": "Quality Complaint"}
    ]
    
    category_table = {
        ("Logistics", "Delayed Shipment"): "Logistics",
        ("Quality", "Damaged Item"): "Quality Assurance",
        ("Quality", "Defective Item"): "Quality Assurance",
        ("Quality", "Quality Complaint"): "Quality Assurance",
        ("Quality", "Counterfeit Product"): "Quality Assurance",
        ("Finance", "Refund Request"): "Finance",
        ("IT", "Login Issue"): "IT support"
    }
    
    def analyze_message(msg):
        msg_lower = msg.lower()
        # Scan Exact Keywords first
        for row in keyword_one:
            if row["keyword"] in msg_lower:
                return row["category"], row["issue"]
        # Scan Probable phrases
        for row in keyword_sum:
            if row["phrase"] in msg_lower:
                return row["category"], row["issue"]
        return None, None
        
    try:
        # Check Narrow AI first if it's a customer
        if current_user.get('role') == 'customer':
            category, issue = analyze_message(user_message)
            if category and issue:
                assigned_dept = category_table.get((category, issue), "CRM manager")
                
                # Dynamic friendly department name mapping
                dept_names = {
                    "Logistics": "Bộ phận Vận chuyển (Logistics)",
                    "Quality Assurance": "Bộ phận Đảm bảo Chất lượng (Quality Assurance)",
                    "Finance": "Bộ phận Kế toán & Tài chính (Finance)",
                    "IT support": "Bộ phận Hỗ trợ Kỹ thuật (IT support)",
                    "CRM manager": "Ban Quản lý CRM (CRM manager)"
                }
                friendly_dept = dept_names.get(assigned_dept, assigned_dept)
                
                # Conversational natural language reply (100% English)
                natural_reply = (
                    f"Hi there! I have successfully registered your issue regarding '{issue}' "
                    f"(Category: {category}). Your request has been immediately routed to our {assigned_dept} "
                    f"department for further assistance. A dedicated representative will reach out to you "
                    f"very soon. Thank you so much for bringing this to our attention!"
                )
                return jsonify({'reply': natural_reply}), 200

        # Fallback to OpenAI if no keyword matches or it's a manager
        system_prompt = "You are a helpful assistant integrated into the Meowie CRM system. All responses must be strictly and entirely in English."
        if current_user.get('role') == 'customer':
            system_prompt = "You are the Meowie CRM Bot, assisting a customer. Be friendly and helpful. If they complain about a delivery or product, ask clarifying questions (e.g. 'I need to confirm the issue is X, right?') to help triage. All responses must be strictly and entirely in English."

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150
        )
        ai_reply = response.choices[0].message.content
        return jsonify({'reply': ai_reply}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print("Make sure to access http://127.0.0.1:5000/login.html first.")
    app.run(debug=True, port=5000)
