import os
import re
import json
import random
import bcrypt
import jwt
import datetime
from functools import wraps
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId
from flask import Flask, request, jsonify, send_from_directory

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

JWT_SECRET = os.getenv('JWT_SECRET', 'fallback_secret')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://user_db:Myproject_io5@cluster0.yb7i3nt.mongodb.net/')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database('meowie_crm')
users_collection = db.users
feedback_collection = db.feedback_tickets
chat_collection = db.department_chat_messages
conversations_collection = db.conversations
taxonomy_collection = db.taxonomy


# --- Department-specific Collections ---
DEPT_COLLECTIONS = {
    'Logistics': db['Logistics'],
    'Quality Assurance': db['Quality Assurance'],
    'Finance': db['Finance'],
    'IT support': db['IT'],
    'CRM manager': db['CRM manager']
}

def save_feedback_ticket(ticket_doc):
    routing = ticket_doc.get('routing_departments', [])
    if not routing:
        routing = ['CRM manager']
    for rkey in routing:
        col = DEPT_COLLECTIONS.get(rkey)
        if col is not None:
            col.insert_one(dict(ticket_doc))

_openai_client = None


def get_openai_client():
    global _openai_client
    key = (os.getenv('OPENAI_API_KEY', '') or '').strip().strip("'").strip('"')
    if key.startswith('key:'):
        key = key[4:]
    if not key or key == 'your_api_key_here':
        return None
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=key)
    return _openai_client


# --- Taxonomy (aligned with index.html dashboard rules) ---
FEEDBACK_TAXONOMY = {
    'Shipping': {
        'department': 'Logistics Team',
        'issues': {
            'Late Delivery': ['delay', "still hasn't arrived", 'overdue', 'stuck', 'waiting', 'slow', 'tracking'],
            'Package arrived damaged': ['broken box', 'crushed', 'smashed', 'damaged', 'wet', 'torn'],
        },
    },
    'Quality': {
        'department': 'Quality Assurance Team',
        'issues': {
            'Defective Product': ['faulty', 'snapped', 'dead', 'broken', 'ripped', 'shattered'],
            'Wrong Item': ['not what I ordered', 'incorrect size', 'wrong color', 'mistake'],
        },
    },
    'Refund': {
        'department': 'Finance Team',
        'issues': {
            'Amount Mismatch': ['short', 'missing dollars', 'wrong math', 'partial', 'charged twice'],
            'Refund delay': ['refund', 'reimbursement', 'money back', 'return'],
        },
    },
    'Technical': {
        'department': 'IT / Dev Team',
        'issues': {
            'App Crash': ['frozen', 'crash', 'glitch', 'error', 'loading screen', 'blank'],
            'Checkout and payment': ['payment', 'checkout', 'promo', 'invalid', 'declined', 'gateway'],
        },
    },
    'Others': {
        'department': 'CRM Management',
        'issues': {'Uncategorized': ['question', 'assistance', 'general inquiry']},
    },
}


def load_db_taxonomy():
    try:
        count = taxonomy_collection.count_documents({})
        if count == 0:
            for cat, data in FEEDBACK_TAXONOMY.items():
                taxonomy_collection.update_one(
                    {'_id': cat},
                    {'$set': {
                        'department': data['department'],
                        'issues': data['issues']
                    }},
                    upsert=True
                )
        docs = list(taxonomy_collection.find({}))
        taxonomy_data = {}
        for doc in docs:
            taxonomy_data[doc['_id']] = {
                'department': doc.get('department'),
                'issues': doc.get('issues', {})
            }
        return taxonomy_data
    except Exception as e:
        print("Error loading dynamic taxonomy:", str(e))
        return FEEDBACK_TAXONOMY

ROUTING_SLUGS = {
    'logistics': 'Logistics',
    'quality_assurance': 'Quality Assurance',
    'finance': 'Finance',
    'it_support': 'IT support',
    'crm_manager': 'CRM manager',
}


def normalize_dept_token(fragment):
    s = (fragment or '').strip().lower()
    if not s:
        return None
    if 'logistics' in s:
        return 'Logistics'
    if 'quality' in s or s.strip() == 'qa':
        return 'Quality Assurance'
    if 'finance' in s:
        return 'Finance'
    if re.search(r'\bit\b', s) or 'dev' in s or 'technical' in s or 'checkout' in s or 'payment' in s or 'promo' in s:
        return 'IT support'
    if 'crm' in s:
        return 'CRM manager'
    return None


def dept_display_to_routing(dept_display):
    if not dept_display:
        return ['CRM manager']
    parts = re.split(r'[,;/]+|\s+and\s+|\s*&\s*', str(dept_display), flags=re.I)
    keys = []
    for p in parts:
        k = normalize_dept_token(p)
        if k and k not in keys:
            keys.append(k)
    if keys:
        return keys
    one = normalize_dept_token(dept_display)
    return [one] if one else ['CRM manager']


def classify_feedback_message(text):
    text_lower = (text or '').lower()
    tax = load_db_taxonomy()
    for category, data in tax.items():
        if category == 'Others':
            continue
        for issue, keywords in data.get('issues', {}).items():
            for word in keywords:
                if word.lower() in text_lower:
                    dept_display = data.get('department')
                    return {
                        'category': category,
                        'issue': issue,
                        'dept_display': dept_display,
                        'routing_departments': dept_display_to_routing(dept_display),
                        'matched_word': word,
                    }
    others_data = tax.get('Others', FEEDBACK_TAXONOMY['Others'])
    d = others_data.get('department', 'CRM Management')
    return {
        'category': 'Others',
        'issue': 'Not detected',
        'dept_display': d,
        'routing_departments': dept_display_to_routing(d),
        'matched_word': None,
    }



def signup_department_to_filter_key(department):
    if not department or department == 'Head of Manager':
        return None
    mapping = {
        'Logistics': 'Logistics',
        'Quality Assurance': 'Quality Assurance',
        'Finance': 'Finance',
        'IT support': 'IT support',
        'CRM manager': 'CRM manager',
    }
    return mapping.get(department.strip())


def slug_to_routing_key(slug):
    s = (slug or '').strip().lower().replace('-', '_')
    return ROUTING_SLUGS.get(s)


def routing_key_to_slug(key):
    for slug, k in ROUTING_SLUGS.items():
        if k == key:
            return slug
    return None


def format_time_display(dt):
    if not dt:
        return ''
    if isinstance(dt, datetime.datetime):
        return dt.strftime('%H:%M, %d/%m/%Y')
    return str(dt)


def format_hm(dt):
    if not dt:
        return ''
    if isinstance(dt, datetime.datetime):
        return dt.strftime('%H:%M')
    return ''


def feedback_doc_to_row(doc):
    cid = doc.get('order_id') or f"#{str(doc.get('_id', ''))[:8]}"
    return {
        'id': cid,
        'time': doc.get('time_display') or format_time_display(doc.get('created_at')),
        'user': doc.get('customer_username', ''),
        'category': doc.get('category', ''),
        'issue': doc.get('issue', ''),
        'dept': doc.get('dept', ''),
        'status': doc.get('status', 'Not contact yet'),
        'text': doc.get('message', ''),
        'routing_departments': doc.get('routing_departments', []),
    }


def seed_feedback_if_empty():
    try:
        total_docs = sum(col.count_documents({}) for col in DEPT_COLLECTIONS.values())
        if total_docs > 0:
            return
        path = os.path.join(os.path.dirname(__file__), 'data', 'feedback_seed.json')
        if not os.path.isfile(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            rows = json.load(f)
        base = datetime.datetime.utcnow()
        for i, row in enumerate(rows):
            doc = dict(row)
            doc['created_at'] = base - datetime.timedelta(hours=len(rows) - i)
            doc['time_display'] = doc.get('time_display') or format_time_display(doc['created_at'])
            doc['source'] = 'seed'
            save_feedback_ticket(doc)
        print('Seeded department feedback collections.')
    except Exception as ex:
        print('Seed feedback skipped:', ex)


seed_feedback_if_empty()


def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        token = None
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            current_user = users_collection.find_one({'_id': ObjectId(payload['user_id'])})
            if not current_user:
                return jsonify({'error': 'User not found in database'}), 401
        except Exception as e:
            print('Token validation or database error:', str(e))
            return jsonify({'error': f'Authentication or database error: {str(e)}'}), 401
        return f(current_user, *args, **kwargs)
    return decorator


@app.route('/')
def serve_index():
    return send_from_directory('.', 'login.html')


@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'customer')
    department = data.get('department') if role == 'manager' else None

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    try:
        if users_collection.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        new_user = {'username': username, 'password': hashed_password.decode('utf-8'), 'role': role}
        if department:
            new_user['department'] = department
        result = users_collection.insert_one(new_user)
        return jsonify({'message': 'User created successfully', 'user_id': str(result.inserted_id)}), 201
    except Exception as e:
        print('Database error during signup:', str(e))
        return jsonify({'error': f'Database connection error: {str(e)}'}), 500


def log_failed_login(username, selected_role, actual_role, reason):
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    u = username or 'N/A'
    sel = selected_role or 'N/A'
    act = actual_role or 'N/A'
    log_msg = f"[{timestamp}] - FAILED LOGIN ATTEMPT: User '{u}' tried to log in as '{sel}' but the actual role is '{act}'. Reason: {reason}.\n"
    print(log_msg.strip())
    try:
        log_filepath = os.path.join(os.path.dirname(__file__), 'login_attempts.log')
        with open(log_filepath, 'a', encoding='utf-8') as f:
            f.write(log_msg)
    except Exception as e:
        print(f"Error writing to log file: {str(e)}")


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    selected_role = data.get('role')
    try:
        user = users_collection.find_one({'username': username})
        if not user:
            log_failed_login(username, selected_role, None, 'User not found')
            return jsonify({'error': 'Wrong Username or Password'}), 401
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            log_failed_login(username, selected_role, user.get('role', 'customer'), 'Incorrect password')
            return jsonify({'error': 'Wrong Username or Password'}), 401
        
        actual_role = user.get('role', 'customer')
        if selected_role and selected_role != actual_role:
            log_failed_login(username, selected_role, actual_role, 'Role mismatch')
            return jsonify({'error': 'Incorrect role selected for this account'}), 401

        token = jwt.encode(
            {
                'user_id': str(user['_id']),
                'username': user['username'],
                'role': user.get('role', 'customer'),
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
            },
            JWT_SECRET,
            algorithm='HS256',
        )
        dept = user.get('department') if user.get('role') == 'manager' else None
        return jsonify(
            {
                'message': 'Login successful',
                'token': token,
                'role': user.get('role', 'customer'),
                'department': dept,
            }
        ), 200
    except Exception as e:
        print('Database error during login:', str(e))
        return jsonify({'error': f'Database connection error: {str(e)}'}), 500


def check_category_permission(current_user, category):
    role = current_user.get('role')
    if role != 'manager':
        return False
    dept = (current_user.get('department') or '').strip()
    if dept == 'Head of Manager':
        return True
    
    mapping = {
        'Logistics': 'Shipping',
        'Quality Assurance': 'Quality',
        'Finance': 'Refund',
        'IT support': 'Technical',
        'CRM manager': 'Others'
    }
    return mapping.get(dept) == category


@app.route('/api/taxonomy', methods=['GET'])
@token_required
def get_taxonomy(current_user):
    tax = load_db_taxonomy()
    return jsonify(tax), 200


@app.route('/api/taxonomy/update', methods=['POST'])
@token_required
def update_taxonomy(current_user):
    data = request.json or {}
    category = data.get('category')
    issues = data.get('issues', {})
    department = data.get('department')
    
    if not category:
        return jsonify({'error': 'Category is required'}), 400
        
    if not check_category_permission(current_user, category):
        return jsonify({'error': f'Permission denied. Managers from your department cannot edit the {category} rules.'}), 403
        
    try:
        update_doc = {'issues': issues}
        if department:
            update_doc['department'] = department
            
        taxonomy_collection.update_one(
            {'_id': category},
            {'$set': update_doc},
            upsert=True
        )
        return jsonify({'message': f'Taxonomy for category {category} updated successfully'}), 200
    except Exception as e:
        print('Error updating taxonomy:', str(e))
        return jsonify({'error': f'Database error: {str(e)}'}), 500


@app.route('/api/feedback', methods=['GET'])
@token_required
def list_feedback(current_user):
    if current_user.get('role') != 'manager':
        return jsonify({'error': 'Managers only'}), 403
    dept = current_user.get('department') or ''
    try:
        if dept == 'Head of Manager':
            all_docs = []
            for dname, col in DEPT_COLLECTIONS.items():
                all_docs.extend(list(col.find({})))
            all_docs.sort(key=lambda x: x.get('created_at', datetime.datetime.min), reverse=True)
            items = [feedback_doc_to_row(d) for d in all_docs]
        else:
            col = DEPT_COLLECTIONS.get(dept)
            if col is None:
                return jsonify({'items': []}), 200
            cur = col.find({}).sort('created_at', -1)
            items = [feedback_doc_to_row(d) for d in cur]
        return jsonify({'items': items}), 200
    except Exception as e:
        print('list_feedback error:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
@token_required
def submit_feedback(current_user):
    if current_user.get('role') != 'customer':
        return jsonify({'error': 'Customers only'}), 403
    data = request.json or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    classified = classify_feedback_message(message)
    username = current_user.get('username', 'Customer')
    order_id = data.get('order_id') or f"#{random.randint(100000, 999999)}"
    now = datetime.datetime.utcnow()
    status = 'Not contact yet' # Start all tickets as Not contact yet to trigger notification

    doc = {
        'order_id': order_id,
        'customer_username': username,
        'message': message,
        'category': classified['category'],
        'issue': classified['issue'],
        'dept': classified['dept_display'],
        'routing_departments': classified['routing_departments'],
        'status': status,
        'created_at': now,
        'time_display': format_time_display(now),
        'source': 'customer',
        'matched_word': classified.get('matched_word'),
    }
    try:
        save_feedback_ticket(doc)
    except Exception as e:
        print('submit_feedback insert error:', e)
        return jsonify({'error': str(e)}), 500

    time_str = now.strftime('%H:%M')
    teams = ', '.join(classified['routing_departments'])
    system_line = (
        f'New feedback {order_id} from {username}: "{message[:280]}" '
        f'— Category: {classified["category"]}, Issue: {classified["issue"]}. Routed to: {teams}.'
    )
    for rkey in classified['routing_departments']:
        try:
            chat_collection.insert_one(
                {
                    'department': rkey,
                    'sender': 'System',
                    'message': system_line,
                    'created_at': now,
                    'time': time_str,
                    'related_order_id': order_id,
                }
            )
        except Exception as e:
            print('chat insert error:', e)

    friendly = teams
    reply = (
        f'Thank you — we received your message and opened ticket {order_id}. '
        f'It has been routed to: {friendly}. A team member will follow up soon.'
    )
    return jsonify({'reply': reply, 'ticket': feedback_doc_to_row(doc)}), 201


@app.route('/api/chat/<slug>/messages', methods=['GET'])
@token_required
def get_chat_messages(current_user, slug):
    if current_user.get('role') != 'manager':
        return jsonify({'error': 'Managers only'}), 403
    rkey = slug_to_routing_key(slug)
    if not rkey:
        return jsonify({'error': 'Unknown department'}), 400
    mgr_dept = current_user.get('department') or ''
    if mgr_dept != 'Head of Manager':
        allowed = signup_department_to_filter_key(mgr_dept)
        if allowed != rkey:
            return jsonify({'error': 'Forbidden'}), 403
    try:
        msgs = list(chat_collection.find({'department': rkey}).sort('created_at', 1).limit(500))
        out = []
        for m in msgs:
            out.append(
                {
                    'sender': m.get('sender', ''),
                    'message': m.get('message', ''),
                    'time': m.get('time') or format_hm(m.get('created_at')),
                }
            )
        return jsonify({'department': rkey, 'slug': slug, 'messages': out}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/<slug>/messages', methods=['POST'])
@token_required
def post_chat_message(current_user, slug):
    if current_user.get('role') != 'manager':
        return jsonify({'error': 'Managers only'}), 403
    rkey = slug_to_routing_key(slug)
    if not rkey:
        return jsonify({'error': 'Unknown department'}), 400
    mgr_dept = current_user.get('department') or ''
    if mgr_dept != 'Head of Manager':
        allowed = signup_department_to_filter_key(mgr_dept)
        if allowed != rkey:
            return jsonify({'error': 'Forbidden'}), 403
    body = request.json or {}
    text = (body.get('message') or '').strip()
    if not text:
        return jsonify({'error': 'Message is required'}), 400
    now = datetime.datetime.utcnow()
    time_str = now.strftime('%H:%M')
    doc = {
        'department': rkey,
        'sender': current_user.get('username', 'Manager'),
        'message': text,
        'created_at': now,
        'time': time_str,
    }
    chat_collection.insert_one(doc)
    return jsonify({'ok': True}), 201


def rule_based_chat_reply(current_user, user_message):
    msg = (user_message or '').strip()
    if not msg:
        return None
    role = current_user.get('role', 'customer')
    if role == 'customer':
        c = classify_feedback_message(msg)
        if c['category'] != 'Others' or c.get('matched_word'):
            teams = ', '.join(c['routing_departments'])
            return f'We have received your feedback! We will send the information to the {teams} department as soon as possible.'
        low = msg.lower()
        if any(x in low for x in ['hello', 'hi', 'hey', 'thanks', 'thank you']):
            return 'Hello! I am here to help. Please describe your order issue or use Submit feedback to open a ticket with our team.'
        return (
            'Thank you for your message. Our staff will review it. '
            'For fastest handling, please submit one clear feedback message with your order details.'
        )
    # manager
    return (
        'Tip: new customer messages appear under Feedback and in your department chat when routed. '
        'Use the dashboard tables for full ticket details.'
    )


@app.route('/api/conversations', methods=['GET'])
@token_required
def get_conversations(current_user):
    if current_user.get('role') != 'customer':
        return jsonify({'error': 'Customers only'}), 403
    username = current_user.get('username')
    try:
        cur = conversations_collection.find({'customer_username': username}).sort('timestamp', 1).limit(500)
        out = []
        for msg in cur:
            out.append({
                'sender': msg.get('sender'),
                'text': msg.get('text'),
                'time': format_time_display(msg.get('timestamp'))
            })
        return jsonify({'messages': out}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai-suggestions', methods=['GET'])
@token_required
def ai_suggestions(current_user):
    if current_user.get('role') != 'manager':
        return jsonify({'error': 'Managers only'}), 403

    others_tickets = []
    try:
        col = DEPT_COLLECTIONS.get('CRM Management')
        if col is not None:
            cur = col.find({'category': 'Others'})
            others_tickets = [t.get('message') for t in cur if t.get('message')]
    except Exception as e:
        print('Error fetching others tickets:', e)

    if not others_tickets:
        others_tickets = [
            "Hi, I noticed the promo code MEOW50 is not working at my checkout screen.",
            "Can I get a discount for my next purchase?",
            "My package has been delayed for 3 days and there's no update on the map."
        ]

    use_ai = os.getenv('USE_OPENAI_FALLBACK', '').lower() in ('1', 'true', 'yes')
    client = get_openai_client() if use_ai else None

    if client:
        system_prompt = (
            "You are an AI data classification expert for the Meowie CRM system. "
            "Analyze these customer messages that currently cannot be classified by the system's keyword rules. "
            "Identify common issues and propose 1-2 category expansions or specific keyword additions. "
            "For each suggestion, provide: "
            "1. 'suggested_issue': A specific subcategory name (e.g. 'Promo Code Error' or 'Delivery Delay'). "
            "2. 'department_category': Must be exactly one of the existing taxonomy categories: "
            "'Shipping', 'Quality', 'Refund', or 'Technical'. "
            "3. 'keywords': A list of 3-5 unique, specific, lowercase keywords to trigger this rule. "
            "4. 'reason': A brief 1-sentence reason based on the messages. "
            "Return a JSON object with a key 'suggestions' containing a list of these objects. "
            "All responses must be strictly in English."
        )
        try:
            response = client.chat.completions.create(
                model='gpt-3.5-turbo',
                response_format={ "type": "json_object" },
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': "\n".join(others_tickets[:15])},
                ],
                max_tokens=300,
            )
            ai_data = json.loads(response.choices[0].message.content)
            return jsonify(ai_data), 200
        except Exception as e:
            print('AI Suggestion generation error:', e)

    fallback_data = {
        'suggestions': [
            {
                'suggested_issue': 'Promo Code Error',
                'department_category': 'Technical',
                'keywords': ['coupon', 'promo', 'discount', 'invalid code'],
                'reason': 'Customers complained about checkout issues when using promo codes'
            },
            {
                'suggested_issue': 'Package Delay Query',
                'department_category': 'Shipping',
                'keywords': ['delayed', 'stuck', 'where is my package', 'no tracking'],
                'reason': 'Customers asking about the status of delayed deliveries'
            }
        ]
    }
    return jsonify(fallback_data), 200


@app.route('/api/ai-chat', methods=['POST'])
@token_required
def ai_chat(current_user):
    data = request.json or {}
    user_message = data.get('message')
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400

    def save_to_db(sender, txt):
        try:
            conversations_collection.insert_one({
                'customer_username': current_user.get('username', 'Customer'),
                'sender': sender,
                'text': txt,
                'timestamp': datetime.datetime.utcnow()
            })
        except Exception as e:
            print('Conversation save error:', e)

    save_to_db('customer', user_message)

    # Auto ticket creation if keyword matched
    classified = classify_feedback_message(user_message)
    if classified['category'] != 'Others':
        username = current_user.get('username', 'Customer')
        order_id = f"#{random.randint(100000, 999999)}"
        now = datetime.datetime.utcnow()
        status = 'Not contact yet' # Trigger notifications

        doc = {
            'order_id': order_id,
            'customer_username': username,
            'message': user_message,
            'category': classified['category'],
            'issue': classified['issue'],
            'dept': classified['dept_display'],
            'routing_departments': classified['routing_departments'],
            'status': status,
            'created_at': now,
            'time_display': format_time_display(now),
            'source': 'customer',
            'matched_word': classified.get('matched_word'),
        }
        try:
            save_feedback_ticket(doc)
        except Exception as e:
            print('Auto-ticket insert error:', e)

        time_str = now.strftime('%H:%M')
        teams = ', '.join(classified['routing_departments'])
        system_line = (
            f'New auto-feedback {order_id} from {username}: "{user_message[:280]}" '
            f'— Category: {classified["category"]}, Issue: {classified["issue"]}. Routed to: {teams}.'
        )
        for rkey in classified['routing_departments']:
            try:
                chat_collection.insert_one({
                    'department': rkey,
                    'sender': 'System',
                    'message': system_line,
                    'created_at': now,
                    'time': time_str,
                    'related_order_id': order_id,
                })
            except Exception as e:
                print('chat insert error:', e)

        reply = f'We have received your feedback! We will send the information to the {teams} department as soon as possible.'
        save_to_db('bot', reply)
        return jsonify({'reply': reply}), 200

    use_ai = os.getenv('USE_OPENAI_FALLBACK', '').lower() in ('1', 'true', 'yes')
    client = get_openai_client() if use_ai else None

    if client:
        system_prompt = (
            "You are a helpful assistant integrated into the Meowie CRM system. "
            "A customer has sent a message that could not be categorized by keywords. "
            "Please analyze the message to deduce the issue the customer is facing. "
            "Return a JSON object with exactly two keys: "
            "1. 'summary': A brief 2-5 word summary of the issue. "
            "2. 'reply': A friendly, empathetic response to the customer acknowledging their issue "
            "and assuring them that it has been forwarded to the CRM manager. "
            "All responses must be strictly in English."
        )
        try:
            response = client.chat.completions.create(
                model='gpt-3.5-turbo',
                response_format={ "type": "json_object" },
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ],
                max_tokens=200,
            )
            ai_data = json.loads(response.choices[0].message.content)
            summary = ai_data.get('summary', 'Uncategorized Issue')
            ai_reply = ai_data.get('reply', 'We have received your message and forwarded it to our CRM manager.')

            username = current_user.get('username', 'Customer')
            order_id = f"#{random.randint(100000, 999999)}"
            now = datetime.datetime.utcnow()

            doc = {
                'order_id': order_id,
                'customer_username': username,
                'message': user_message,
                'category': 'Others',
                'issue': summary,
                'dept': 'CRM Management',
                'routing_departments': ['CRM manager'],
                'status': 'Not contact yet',
                'created_at': now,
                'time_display': format_time_display(now),
                'source': 'customer',
                'matched_word': 'AI inference',
            }
            save_feedback_ticket(doc)

            system_line = (
                f'New auto-feedback {order_id} from {username}: "{user_message[:280]}" '
                f'— Category: Others, Issue: {summary}. Routed to: CRM manager.'
            )
            chat_collection.insert_one({
                'department': 'CRM manager',
                'sender': 'System',
                'message': system_line,
                'created_at': now,
                'time': now.strftime('%H:%M'),
                'related_order_id': order_id,
            })

            save_to_db('bot', ai_reply)
            return jsonify({'reply': ai_reply}), 200

        except Exception as e:
            print('AI Chat error:', str(e))
            # Fallback to rule-based if AI fails

    rb = rule_based_chat_reply(current_user, user_message)
    if rb:
        save_to_db('bot', rb)
        return jsonify({'reply': rb}), 200

    reply = 'I can help with short questions. For a formal ticket, please describe your issue so we can route it.'
    save_to_db('bot', reply)
    return jsonify({'reply': reply}), 200


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)


if __name__ == '__main__':
    print('Starting Flask server...')
    print('Open http://127.0.0.1:5000/login.html')
    app.run(debug=True, port=5000)
