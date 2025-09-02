from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import pandas as pd
import io
import random
import string
from werkzeug.utils import secure_filename
import requests
from ai_models import ai_manager
import rule_engine
import json
from datetime import datetime, date, timedelta
import traceback
load_dotenv()

# Legacy Gemini function for backward compatibility
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def analyze_policy_with_gemini(pdf_bytes):
    """Send PDF directly to Gemini for analysis and generate JSON rules"""
    import base64
    
    # Convert PDF to base64 for Gemini API
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    # Prepare prompt for Gemini
    prompt = """
You are an HR policy analyzer. Please analyze this leave policy document and provide detailed answers to these 5 questions:

1. Does the document list all types of leaves in the organization (e.g., paid leave, maternity leave, compensatory off, sick leave, etc.)? If yes, list them.

2. Does the document specify how leaves are credited to the employee, and how many are credited? Please provide details about the leave credit system.

3. Does the document specify when are the allowed times an employee may apply for a leave? What are the advance notice requirements?

4. Does the document specify leave "sandwiching" policy (i.e., restrictions around long weekends, holidays, etc.)? What are the rules?

5. Does the document specify a list of public holidays? If yes, list them or describe how they are determined.

6. Validate that the json rule engine created, picks up all the rules and policies related to leaves in the uploaded document.

7. Ensure you pick up all the stipulations related to the leaves, including any specific conditions, limitations, or requirements mentioned in the document.

8. Ensure department specific leave policy details are found in the policy.

9. Ensure gender-specific leave policy details are found in the policy.

10. Ensure the leave credit system is clearly defined, ie. frequency of credits, date of joining linkage, etc.

11. Ensure policies related to modification of leaves are defined.

Please provide clear, specific answers for each question. If information is not found for any question, clearly state that it's not specified in the document.

After providing the analysis, please also generate a structured JSON rule set that can be used by a deterministic function to automatically approve/reject leave requests. The JSON should follow this structure, but you may alter this structure as per the uploaded policy:

{
  "leaveTypes": {
    "annual": {"maxDays": 21, "carryOver": true, "maxCarryOver": 5},
    "sick": {"maxDays": 10, "requiresCertificate": true, "certificateThreshold": 3},
    "maternity": {"maxDays": 90, "requiresAdvanceNotice": 30},
    "personal": {"maxDays": 5, "requiresApproval": true}
  },
  "advanceNoticeRequirements": {
    "annual": 7,
    "personal": 3,
    "sick": 0,
    "maternity": 30
  },
  "sandwichingPolicy": {
    "enabled": true,
    "maxConsecutiveDays": 10,
    "restrictAroundHolidays": true,
    "holidayBuffer": 1
  },
  "publicHolidays": [
    "2024-01-01",
    "2024-12-25"
  ],
  "approvalRules": {
    "autoApprove": {
      "maxDays": 3,
      "leaveTypes": ["sick", "personal"],
      "conditions": ["sufficientBalance", "validNotice"]
    },
    "requiresApproval": {
      "minDays": 4,
      "leaveTypes": ["annual", "maternity"],
      "specialCases": ["sandwiching", "insufficientBalance"]
    },
    "departmentLevelPolicies":{},
    "specialCases":{}
  }
}

Please extract actual values from the policy document and generate the JSON accordingly. If specific values are not mentioned, use reasonable defaults and mention which values were assumed.
"""

    # Call Gemini API with PDF file
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": pdf_base64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096
        }
    }
    
    response = requests.post(f"{url}?key={GEMINI_API_KEY}", headers=headers, json=data)
    
    if response.ok:
        result = response.json()
        try:
            answer = result["candidates"][0]["content"]["parts"][0]["text"]
            return answer
        except (KeyError, IndexError) as e:
            return f"Error parsing Gemini response: {str(e)}\nFull response: {result}"
    else:
        return f"Gemini API error ({response.status_code}): {response.text}"

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*")

# Check if Firebase credentials are available
service_account_path = "aihrms2-firebase-adminsdk-fbsvc-fce522b367.json"

FIREBASE_ENABLED = (
    os.path.exists(service_account_path) or 
    all([
        os.getenv("FIREBASE_PRIVATE_KEY_ID") and "your_actual" not in os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
        os.getenv("FIREBASE_PRIVATE_KEY") and "Your_actual" not in os.getenv("FIREBASE_PRIVATE_KEY", ""),
        os.getenv("FIREBASE_CLIENT_EMAIL") and "firebase-adminsdk-xxxxx" not in os.getenv("FIREBASE_CLIENT_EMAIL", "")
    ])
)

if FIREBASE_ENABLED:
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, auth
        
        # Initialize Firebase Admin SDK
        if not firebase_admin._apps:
            if os.path.exists(service_account_path):
                print("🔑 Using service account key file for Firebase authentication")
                cred = credentials.Certificate(service_account_path)
            else:
                print("🔑 Using environment variables for Firebase authentication")
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": "fe-be-deployment",
                    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                    "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace('\\n', '\n'),
                    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL")
                })
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("✅ Firebase initialized successfully!")
        
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        FIREBASE_ENABLED = False
else:
    print("⚠️  Firebase credentials not configured. Running in mock mode.")

def generate_employee_email(first_name):
    """Generate email with first name + 5 random digits + @om.com"""
    random_digits = ''.join(random.choices(string.digits, k=5))
    return f"{first_name.lower()}{random_digits}@om.com"

def generate_random_password():
    """Generate a random password for new users"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

def calculate_business_days(start_date_str, end_date_str):
    """Calculate business days between two dates"""
    try:
        from datetime import datetime, timedelta
        
        if isinstance(start_date_str, str):
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = start_date_str
            
        if isinstance(end_date_str, str):
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            end_date = end_date_str
        
        # Simple calculation: count all days between start and end (inclusive)
        # For more accurate business days, you'd exclude weekends and holidays
        days = (end_date - start_date).days + 1
        return max(1, days)  # Minimum 1 day
    except:
        return 1  # Default to 1 day if parsing fails

# Mock data for when Firebase is not available
MOCK_USERS = {
    "admin@om.com": {
        'uid': 'mock-admin-uid',
        'email': 'admin@om.com',
        'first_name': 'Admin',
        'last_name': 'User',
        'role': 'admin',
        'department': 'Administration',
        'position': 'System Administrator'
    },
    "employee@om.com": {
        'uid': 'mock-employee-uid',
        'email': 'employee@om.com',
        'first_name': 'John',
        'last_name': 'Doe',
        'role': 'employee',
        'department': 'Engineering',
        'position': 'Software Developer'
    }
}

MOCK_LEAVE_REQUESTS = [
    {
        'id': 'mock-request-1',
        'employee_uid': 'mock-employee-uid',
        'employee_name': 'John Doe',
        'employee_department': 'Engineering',
        'start_date': '2025-08-25',
        'end_date': '2025-08-27',
        'leave_type': 'vacation',
        'reason': 'Family vacation',
        'status': 'pending',
        'created_at': {'seconds': 1724054400}
    },
    {
        'id': 'mock-request-2',
        'employee_uid': 'mock-employee-uid',
        'employee_name': 'John Doe',
        'employee_department': 'Engineering',
        'start_date': '2025-08-20',
        'end_date': '2025-08-20',
        'leave_type': 'sick',
        'reason': 'Medical appointment',
        'status': 'approved',
        'created_at': {'seconds': 1724054400}
    }
]

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy', 
        'message': 'HR Portal API is running',
        'firebase_enabled': FIREBASE_ENABLED,
        'mode': 'production' if FIREBASE_ENABLED else 'mock'
    })

@app.route('/api/verify-token', methods=['POST'])
def verify_token():
    """Verify Firebase ID token and return user info"""
    try:
        id_token = request.json.get('idToken')
        if not id_token:
            return jsonify({'error': 'No token provided'}), 400
        
        if FIREBASE_ENABLED:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            
            # Get user role from Firestore
            user_doc = db.collection('users').document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_role = user_data.get('role','employee')
                frontend_role = 'admin' if user_role =='admin' else 'employee'
                return jsonify({
                    'uid': uid,
                    'email': decoded_token.get('email'),
                    'role': frontend_role,
                    'profile': user_data
                })
                
                # Use system_role if available, otherwise fall back to role, default to employee
                # system_role = user_data.get('system_role') or user_data.get('role', 'employee')
                # # Normalize system role to admin/employee only
                # if system_role.lower() in ['admin', 'administrator', 'hr', 'manager']:
                #     system_role = 'admin'
                # else:
                #     system_role = 'employee'
                
                # return jsonify({
                #     'uid': uid,
                #     'email': decoded_token.get('email'),
                #     'role': system_role,
                #     'profile': user_data
                # })
            else:
                return jsonify({'error': 'User not found in database'}), 404
        else:
            # Mock authentication for testing
            email = id_token.lower()
            if email in MOCK_USERS:
                user_data = MOCK_USERS[email]
                return jsonify({
                    'uid': user_data['uid'],
                    'email': user_data['email'],
                    'role': user_data['role'],
                    'profile': user_data
                })
            else:
                return jsonify({'error': 'Invalid credentials (mock mode)'}), 401
            
    except Exception as e:
        return jsonify({'error': str(e)}), 401


@app.route('/api/admin/upload-employees', methods=['POST'])
def upload_employees():
    """Upload employee data from Excel/CSV file"""
    try:
        if not FIREBASE_ENABLED:
            return jsonify({
                'message': 'Firebase not configured - running in mock mode',
                'created_users': [],
                'errors': ['Please configure Firebase credentials for full functionality']
            })
        
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        
        # Check if user is admin
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Read Excel or CSV file
        filename = secure_filename(file.filename)
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(file.read()))
        elif filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(file.read().decode('utf-8')))
        else:
            return jsonify({'error': 'Invalid file format. Please use Excel or CSV.'}), 400
        
        from modules.insert_data import insert_data_to_db
        
        created_users,errors = insert_data_to_db(df)
        return jsonify({
            'message': f"Successfully created {len(created_users)} employees",
            'created_users': created_users,
            'errors': errors
        }) 
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/employee/profile', methods=['GET'])
def get_employee_profile():
    """Get employee profile data"""
    try:
        if FIREBASE_ENABLED:
            id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            
            user_doc = db.collection('users').document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                # Remove sensitive data
                user_data.pop('temporary_password', None)
                
                # Calculate total used leave days across all leave types for the current year
                from datetime import datetime
                current_year = datetime.now().year
                
                leave_requests_ref = db.collection('leave_requests')
                approved_requests = leave_requests_ref.where('employee_uid', '==', uid) \
                                                    .where('status', '==', 'approved') \
                                                    .stream()

                total_used_days = 0
                for leave_request in approved_requests:
                    request_data = leave_request.to_dict()
                    start_date = request_data['start_date']
                    
                    # Check if request is in current year
                    if isinstance(start_date, str):
                        request_year = int(start_date.split('-')[0])
                    else:
                        request_year = start_date.year
                    
                    if request_year == current_year:
                        total_used_days += calculate_business_days(request_data['start_date'], request_data['end_date'])
                
                # Add calculated fields
                initial_balance = user_data.get('leave_balance', 0)
                user_data['remaining_leave_balance'] = max(0, initial_balance - total_used_days)
                user_data['used_leave_days'] = total_used_days
                
                return jsonify(user_data)
            else:
                return jsonify({'error': 'User not found'}), 404
        else:
            # Return mock employee data
            return jsonify(MOCK_USERS["employee@om.com"])
            
    except Exception as e:
        return jsonify({'error': str(e)}), 401

from flask import request

@app.route('/api/employee/leave-requests', methods=['GET'])
def get_leave_requests():
    """Get employee's leave requests"""
    try:
        if FIREBASE_ENABLED:
            id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            
            leave_requests = []
            docs = db.collection('leave_requests').where('employee_uid', '==', uid).stream()
            
            for doc in docs:
                leave_data = doc.to_dict()
                leave_data['id'] = doc.id
                leave_requests.append(leave_data)
            
            return jsonify(leave_requests)
        else:
            # Return mock data filtered for employee
            return jsonify([req for req in MOCK_LEAVE_REQUESTS if req['employee_uid'] == 'mock-employee-uid'])
        
    except Exception as e:
        print("error ",traceback.print_exc())
        return jsonify({'error': str(e)}), 401

@app.route('/api/employee/leave-requests', methods=['POST'])
def create_leave_request():
    """Create a new leave request with rule-engine validation"""
    try:
        # Try to get JSON data with multiple approaches
        data = None
        
        # First try: check if content type is JSON and use get_json()
        if request.content_type and 'json' in request.content_type.lower():
            try:
                data = request.get_json()
                if data:
                    print(f"✅ Got JSON data from get_json(): {data}")
            except Exception as e:
                print(f"❌ get_json() failed: {e}")
        
        # Second try: force JSON parsing if first approach failed
        if not data and request.get_data():
            try:
                import json
                raw_data = request.get_data(as_text=True)
                print(f"🔍 Raw request data: {raw_data}")
                data = json.loads(raw_data)
                print(f"✅ Parsed JSON from raw data: {data}")
            except Exception as e:
                print(f"❌ JSON parsing failed: {e}")
        
        # Third try: form data
        if not data and request.form:
            try:
                data = request.form.to_dict()
                print(f"✅ Got form data: {data}")
            except Exception as e:
                print(f"❌ Form data extraction failed: {e}")
        
        print(f"🔍 Debug - Final data: {data}")
        print(f"🔍 Debug - Content-Type: {request.content_type}")
        print(f"🔍 Debug - Is JSON: {request.is_json}")
        print(f"🔍 Debug - Request method: {request.method}")
        
        if not data:
            return jsonify({
                'error': 'No data provided. Please ensure request has valid JSON body.',
                'debug_info': {
                    'content_type': request.content_type,
                    'is_json': request.is_json,
                    'has_data': bool(request.get_data()),
                    'has_form': bool(request.form),
                    'raw_data_length': len(request.get_data()) if request.get_data() else 0
                }
            }), 400
        
        # Validate required fields
        required_fields = ['start_date', 'end_date', 'leave_type']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        if FIREBASE_ENABLED:
            id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            
            # Validate leave request against rule-engine rules
            validation_result = validate_leave_request_with_rules(uid, data)
            if not validation_result['valid']:
                return jsonify({'error': validation_result['reason']}), 400
            
            leave_request = {
                'employee_uid': uid,
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'leave_type': data['leave_type'],
                'reason': data.get('reason', ''),
                'status': 'pending',
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP,
                'validation_notes': validation_result['reason']
            }
            
            doc_ref = db.collection('leave_requests').add(leave_request)
            
            # Create a JSON-serializable response object
            from datetime import datetime
            response_leave_request = {
                'id': doc_ref[1].id,
                'employee_uid': uid,
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'leave_type': data['leave_type'],
                'reason': data.get('reason', ''),
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'validation_notes': validation_result['reason']
            }
            
            return jsonify({
                'message': 'Leave request created successfully', 
                'leave_request': response_leave_request,
                'validation': validation_result
            })
        else:
            # Mock leave request creation
            new_request = {
                'id': f'mock-request-{len(MOCK_LEAVE_REQUESTS) + 1}',
                'employee_uid': 'mock-employee-uid',
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'leave_type': data['leave_type'],
                'reason': data.get('reason', ''),
                'status': 'pending',
                'created_at': {'seconds': 1724054400}
            }
            MOCK_LEAVE_REQUESTS.append(new_request)
            
            return jsonify({'message': 'Leave request created successfully (mock mode)', 'leave_request': new_request})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/leave-requests', methods=['GET'])
def get_all_leave_requests():
    """Get all leave requests for admin"""
    try:
        if FIREBASE_ENABLED:
            id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            decoded_token = auth.verify_id_token(id_token)
            
            # Check if user is admin
            admin_doc = db.collection('users').document(decoded_token['uid']).get()
            if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
                return jsonify({'error': 'Access denied. Admin role required.'}), 403
            
            leave_requests = []
            docs = db.collection('leave_requests').stream()
            
            for doc in docs:
                leave_data = doc.to_dict()
                leave_data['id'] = doc.id
                
                # Get employee details
                employee_doc = db.collection('users').document(leave_data['employee_uid']).get()
                if employee_doc.exists:
                    employee_data = employee_doc.to_dict()
                    leave_data['employee_name'] = f"{employee_data.get('first_name', '')} {employee_data.get('last_name', '')}"
                    leave_data['employee_department'] = employee_data.get('department', '')
                
                leave_requests.append(leave_data)
            
            return jsonify(leave_requests)
        else:
            # Return mock data for admin
            return jsonify(MOCK_LEAVE_REQUESTS)
        
    except Exception as e:
        print("error")
        return jsonify({'error': str(e)}), 401

@app.route('/api/admin/leave-requests/<request_id>/status', methods=['PUT'])
def update_leave_request_status(request_id):
    """Update leave request status (approve/reject)"""
    try:
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['approved', 'rejected']:
            return jsonify({'error': 'Invalid status. Must be approved or rejected.'}), 400
        
        if FIREBASE_ENABLED:
            id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
            decoded_token = auth.verify_id_token(id_token)
            
            # Check if user is admin
            admin_doc = db.collection('users').document(decoded_token['uid']).get()
            if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
                return jsonify({'error': 'Access denied. Admin role required.'}), 403
            
            db.collection('leave_requests').document(request_id).update({
                'status': status,
                'updated_at': firestore.SERVER_TIMESTAMP,
                'approved_by': decoded_token['uid']
            })
            
            return jsonify({'message': f'Leave request {status} successfully'})
        else:
            # Mock status update
            for request in MOCK_LEAVE_REQUESTS:
                if request['id'] == request_id:
                    request['status'] = status
                    break
            
            return jsonify({'message': f'Leave request {status} successfully (mock mode)'})
        
    except Exception as e:
        print("error ", traceback.print_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/employees', methods=['GET'])
def get_all_employees():
    """Get all employees for admin"""
    try:
        if not FIREBASE_ENABLED:
            return jsonify([
                {'id': '1', 'email': 'john.doe@company.com', 'first_name': 'John', 'last_name': 'Doe', 'department': 'Engineering'},
                {'id': '2', 'email': 'jane.smith@company.com', 'first_name': 'Jane', 'last_name': 'Smith', 'department': 'Marketing'}
            ])
            
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        
        # Check if user is admin
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403
        
        employees = []
        docs = db.collection('users').where('role', '!=', 'admin').stream()
        
        for doc in docs:
            employee_data = doc.to_dict()
            # Remove sensitive data
            employee_data.pop('temporary_password', None)
            employees.append(employee_data)
        
        return jsonify(employees)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 401

@app.route('/api/admin/clear-data', methods=['DELETE'])
def clear_all_data():
    """Clear all Firebase data except admin user"""
    try:
        if not FIREBASE_ENABLED:
            return jsonify({'message': 'All data cleared successfully (mock mode)', 'deleted_users': [], 'errors': []})
            
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        
        # Check if user is admin
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403
        
        admin_email = decoded_token.get('email')
        if admin_email != 'admin@aihr.com':
            return jsonify({'error': 'Only admin@aihr.com can perform this operation.'}), 403
        
        deleted_users = []
        errors = []
        
        # Clear Firestore collections
        try:
            # Delete all users except admin from Firestore
            users_ref = db.collection('users')
            docs = users_ref.stream()
            
            for doc in docs:
                user_data = doc.to_dict()
                if user_data.get('email') != 'admin@aihr.com':
                    doc.reference.delete()
                    deleted_users.append(user_data.get('email', doc.id))
            
            # Delete all leave requests
            leave_requests_ref = db.collection('leave_requests')
            leave_docs = leave_requests_ref.stream()
            for doc in leave_docs:
                doc.reference.delete()
            
        except Exception as e:
            errors.append(f"Firestore deletion error: {str(e)}")
        
        # Clear Firebase Auth users
        try:
            # List all users from Firebase Auth
            page = auth.list_users()
            auth_deleted_count = 0
            
            while page:
                for user in page.users:
                    if user.email != 'admin@aihr.com':
                        try:
                            auth.delete_user(user.uid)
                            auth_deleted_count += 1
                        except Exception as e:
                            errors.append(f"Failed to delete user {user.email}: {str(e)}")
                
                if page.has_next_page:
                    page = page.get_next_page()
                else:
                    break
                    
        except Exception as e:
            errors.append(f"Firebase Auth deletion error: {str(e)}")
        
        return jsonify({
            'message': 'Data cleared successfully',
            'deleted_users': deleted_users,
            'auth_deleted_count': auth_deleted_count if 'auth_deleted_count' in locals() else 0,
            'errors': errors
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 401

@app.route('/api/admin/ai-models', methods=['GET'])
def get_available_ai_models():
    """Get list of available AI models"""
    try:
        if not FIREBASE_ENABLED:
            # Return mock data for testing
            return jsonify({
                'models': {
                    'gemini': {'name': 'Gemini 1.5 Flash', 'supports_pdf': True, 'max_tokens': 4096, 'pdf_method': 'native'},
                    'chatgpt': {'name': 'ChatGPT 4o Mini', 'supports_pdf': True, 'max_tokens': 4096, 'pdf_method': 'gemini_extraction'},
                    'claude': {'name': 'Claude 3 Sonnet', 'supports_pdf': True, 'max_tokens': 4096, 'pdf_method': 'gemini_extraction'},
                    'deepseek': {'name': 'DeepSeek Chat', 'supports_pdf': True, 'max_tokens': 4096, 'pdf_method': 'gemini_extraction'}
                }
            })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        available_models = ai_manager.get_available_models()
        return jsonify({'models': available_models})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
import re
def extract_section(title, text):
                    
    """Extracts content following a bold section title until next section or end."""
    pattern = rf"\*\*{title}\:\*\*\s*(.*?)(?=\n\s*\*\*|$)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ''

# @app.route('/api/admin/analyze-policy', methods=['POST'])
@app.route('/api/admin/analyze-policy', methods=['POST'])
def analyze_policy():
    try:
        if not FIREBASE_ENABLED:
            return jsonify({
                'analysis': 'Mock policy analysis: This is a sample policy analysis response when Firebase is not configured.',
                'rules': [
                    "leave_type == 'annual' and days_requested <= 21 and employee_balance >= days_requested",
                    "leave_type == 'sick' and days_requested <= 10 and (days_requested <= 3 or has_medical_certificate == True)",
                    "leave_type == 'personal' and days_requested <= 5 and advance_notice_days >= 3",
                    "leave_type == 'annual' and advance_notice_days >= 7"
                ]
            })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        if file.filename == '' or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Please upload a PDF file.'}), 400

        # Get selected AI model from form data
        selected_model = request.form.get('model', 'gemini')  # Default to Gemini
        
        pdf_bytes = file.read()
        print("Parsing PDF to analyse_policy_with_model")
        # Use the AI model manager
        full_response = ai_manager.analyze_policy_with_model(selected_model, pdf_bytes)
        print("returned to analyze_policy function from analyze_policy_with_model")
        print(f"🔍 Full response preview (first 500 chars): {full_response[:500]}...")
        
        # Debug: Check if the response contains the expected markers
        print(f"🔍 Response starts with ```json: {full_response.strip().startswith('```json')}")
        print(f"🔍 Response contains ```json: {'```json' in full_response}")
        print(f"🔍 Response contains closing ```: {'```' in full_response[10:]}")
        
        # Improved JSON extraction - handle multiple patterns and incomplete responses
        match = None
        json_str = None
        
        # Pattern 1: Complete code block with closing ```
        match = re.search(r"```json\s*(.*?)\s*```", full_response, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            print("✅ Found complete JSON code block")
        
        # Pattern 2: Incomplete code block (starts with ```json but no closing ```)
        if not match:
            match = re.search(r"```json\s*(.*)", full_response, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                # Try to find where JSON likely ends (look for last closing brace)
                if json_str.count('{') > 0:
                    # Find the last complete JSON object
                    brace_count = 0
                    last_valid_pos = -1
                    for i, char in enumerate(json_str):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                last_valid_pos = i + 1
                    if last_valid_pos > 0:
                        json_str = json_str[:last_valid_pos]
                        print("✅ Found incomplete JSON code block, extracted JSON portion")
        
        # Pattern 3: JSON object without code block markers
        if not match:
            match = re.search(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", full_response, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                print("✅ Found JSON object without code block markers")
        
        print(f"🔍 Final extraction result: {json_str is not None}")
        
        if json_str:
            print(f"📦 Extracted JSON: {json_str}")
            try:
                data = json.loads(json_str)
                print("✅ Successfully parsed JSON from code block")
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                # Return analysis without structured data
                return jsonify({
                    'analysis': full_response,
                    'rules': [],
                    'model_used': selected_model,
                    'executive_summary': "",
                    'holiday_calendar_findings': "",
                    'complex_rule_interdependencies': "",
                    'employee_schema_mapping': ""
                })

            # 3. Extract required fields
            executive_summary = data.get("executive_summary", "")
            holiday_calendar_findings = data.get("holiday_calendar_findings", "")
            complex_rule_interdependencies = data.get("complex_rule_interdependencies", "")
            employee_schema_mapping = data.get("employee_schema_mapping", "")

            from utils.rule_normalizer import normalize_rule, validate_rule
            raw_rules = data.get("RULE_ENGINE_RULES", [])
            # Normalize + validate rules
            # clean_rules = []
            # for r in raw_rules:
            #     print(f"Raw rule: {r}")
            #     # Strip "rule:" prefix if present
            #     expr = r.replace("rule:", "").strip()

            #     expr = normalize_rule(expr)
            #     if validate_rule(expr):
            #         clean_rules.append(expr)

            return jsonify({
            'analysis': full_response,
            'rules': raw_rules,
            'model_used': selected_model,
            'executive_summary':executive_summary,
            'holiday_calendar_findings':holiday_calendar_findings,
            'complex_rule_interdependencies':complex_rule_interdependencies,
            'employee_schema_mapping':employee_schema_mapping
            })
        else:
            try:
                data = json.loads(full_response)  # fallback if model didn’t wrap in ```
            except Exception as e:
                print(f"❌ No JSON found in response: {e}")
                print(f"🔍 Full response preview: {full_response[:1000]}...")
                # Return analysis without structured data instead of raising error
                return jsonify({
                    'analysis': full_response,
                    'rules': [],
                    'model_used': selected_model,
                    'executive_summary': "",
                    'holiday_calendar_findings': "",
                    'complex_rule_interdependencies': "",
                    'employee_schema_mapping': ""
                })    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
def analyze_policy_v2():
    try:
        if not FIREBASE_ENABLED:
            return jsonify({
                'analysis': 'Mock policy analysis: This is a sample policy analysis response when Firebase is not configured.',
                'rules': [
                    "leave_type == 'annual' and days_requested <= 21 and employee_balance >= days_requested",
                    "leave_type == 'sick' and days_requested <= 10 and (days_requested <= 3 or has_medical_certificate == True)",
                    "leave_type == 'personal' and days_requested <= 5 and advance_notice_days >= 3",
                    "leave_type == 'annual' and advance_notice_days >= 7"
                ]
            })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['file']
        if file.filename == '' or not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Please upload a PDF file.'}), 400

        # Get selected AI model from form data
        selected_model = request.form.get('model', 'gemini')  # Default to Gemini
        
        pdf_bytes = file.read()
        
        # Use the AI model manager
        full_response = ai_manager.analyze_policy_with_model(selected_model, pdf_bytes)
        # import re
        # executive_summary = ''
        # holiday_calendar_findings = ''
        # complex_rule_interdependencies = ''
        # employee_schema_mapping = ''
        # rule_engine_rules = []
        
        # print("full_response ",full_response)
        # if selected_model=="gemini":
        #     match = re.search(r"```json\s*(.*?)\s*```", full_response, re.DOTALL)
        #     if match:
        #         json_str = match.group(1).strip()
        #         # 2. Parse JSON string
        #         data = json.loads(json_str)

        #         # 3. Extract required fields
        #         executive_summary = data.get("executive_summary", "")
        #         holiday_calendar_findings = data.get("holiday_calendar_findings", "")
        #         complex_rule_interdependencies = data.get("complex_rule_interdependencies", "")
        #         employee_schema_mapping = data.get("employee_schema_mapping", "")
        #         rule_engine_rules = data.get("RULE_ENGINE_RULES", [])
        # elif selected_model in ["ChatGPT 4o", "chatgpt", "ChatGPT"]:
        #     executive_summary = extract_section("Executive Summary", full_response)
        #     holiday_calendar_findings = extract_section("Holiday Calendar Findings", full_response)
        #     complex_rule_interdependencies = extract_section("Complex Rule Interdependencies Identified", full_response)
        #     employee_schema_mapping = extract_section("Mapping Rules to Employee Schema Fields", full_response)

        #     # Extract RULE_ENGINE_RULES from ```python``` code block
        #     rules_match = re.search(r"```python\s*(.*?)\s*```", full_response, re.DOTALL)
        #     rule_engine_rules = []
        #     if rules_match:
        #         rules_block = rules_match.group(1)
        #         # Extract each line that starts with 'rule:'
        #         rule_engine_rules = [line.strip() for line in rules_block.splitlines() if line.strip().startswith("rule:")]

        #     print("rule_engine_rules extracted rules by ",selected_model)
        #     print("rule_engine_rules ",rule_engine_rules)
        # return jsonify({
        #                 'analysis': full_response,
        #                 'rules': rule_engine_rules,
        #                 'model_used': selected_model,
        #                 'executive_summary':executive_summary,
        #                 'holiday_calendar_findings':holiday_calendar_findings,
        #                 'complex_rule_interdependencies':complex_rule_interdependencies,
        #                 'employee_schema_mapping':employee_schema_mapping
        #                 })
        # # else:
        # #     return jsonify({
        # #     'analysis': full_response,
        # #     'rules': rule_engine_rules,
        # #     'model_used': selected_model,
        # #     'executive_summary':executive_summary,
        # #     'holiday_calendar_findings' :holiday_calendar_findings,
        # #     'complex_rule_interdependencies':complex_rule_interdependencies, 
        # #     'employee_schema_mapping':employee_schema_mapping
        # #     })
            
        # Extract rule-engine rules from the response
        import re
        
        # Look for RULE_ENGINE_RULES section with various formats
        rules_patterns = [
            r'### RULE_ENGINE_RULES\s*(.*?)(?:\n\n|\Z)',
            r'RULE_ENGINE_RULES:\s*(.*?)(?:\n\n|\Z)',
            r'RULE_ENGINE_RULES\s*(.*?)(?:\n\n|\Z)',
            r'```python\s*(rule:.*?)```',
            r'```json\s*(.*?)\s*```',
            r'"rule:\s*([^"]+)"'
        ]
        
        rules = []
        for pattern in rules_patterns:
            rules_match = re.search(pattern, full_response, re.DOTALL | re.IGNORECASE)
            if rules_match:
                rules_section = rules_match.group(1)
                # Extract individual rules - look for lines starting with 'rule:'
                rule_lines = re.findall(r'^rule:\s*(.+)$', rules_section, re.MULTILINE | re.IGNORECASE)
                rules = [rule.strip() for rule in rule_lines if rule.strip()]
                if rules:  # If we found rules with this pattern, use them
                    break

        # If still no rules found, try a more aggressive search across the entire response
        if not rules:
            rule_lines = re.findall(r'^rule:\s*(.+)$', full_response, re.MULTILINE | re.IGNORECASE)
            rules = [rule.strip() for rule in rule_lines if rule.strip()]
        
        print(f"📊 Extracted {len(rules)} rules from AI response")
        for i, rule in enumerate(rules[:10]):  # Show first 10 rules
            print(f"  Rule {i+1}: {rule}")
        if len(rules) > 10:
            print(f"  ... and {len(rules) - 10} more rules")
        
        # If no rules found, create some default rule-engine rules
        if not rules:
            rules = [
                "leave_type == 'annual' and days_requested <= 21 and employee_balance >= days_requested",
                "leave_type == 'sick' and days_requested <= 10 and (days_requested <= 3 or has_medical_certificate == True)",
                "leave_type == 'personal' and days_requested <= 5 and advance_notice_days >= 3",
                "leave_type == 'annual' and advance_notice_days >= 7",
                "not (is_weekend_adjacent == True and is_holiday_adjacent == True and consecutive_days > 10)"
            ]
        return jsonify({
            'analysis': full_response,
            'rules': rules,
            'model_used': selected_model})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/chat-rules', methods=['POST'])
def chat_with_rules():
    try:
        if not FIREBASE_ENABLED:
            return jsonify({'answer': 'Mock response: This would answer your question based on the policy rules when Firebase is configured.'})
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        data = request.get_json()
        question = data.get('question', '').strip()
        rules = data.get('rules', {})
        selected_model = data.get('model', 'gemini')  # Default to Gemini
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        if not rules:
            return jsonify({'error': 'No rules provided. Please generate rules first.'}), 400

        # Use the AI model manager
        answer = ai_manager.chat_with_model(selected_model, question, rules)
        
        return jsonify({
            'answer': answer,
            'model_used': selected_model
        })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/edit-rules', methods=['POST'])
def edit_rules():
    """Edit leave policy rules using AI assistance"""
    try:
        if not FIREBASE_ENABLED:
            # Mock response when Firebase is disabled
            data = request.get_json()
            prompt = data.get('prompt', '').strip().lower()
            
            # Simple mock logic to demonstrate functionality
            if any(word in prompt for word in ['sick', 'leave', 'day', 'policy', 'annual', 'vacation', 'parental', 'maternity', 'paternity']):
                return jsonify({
                    'success': True,
                    'response': f'Mock response: I would process your request "{data.get("prompt", "")}" and update the rules accordingly when Firebase and AI models are configured.',
                    'updatedRules': data.get('currentRules', {}),
                    'model_used': data.get('model', 'gemini')
                })
            else:
                return jsonify({
                    'success': True,
                    'response': 'Looks like your prompt isn\'t about your leave policy. Please ask about leave types, days, policies, or related topics.',
                    'updatedRules': None,
                    'model_used': data.get('model', 'gemini')
                })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        current_rules = data.get('currentRules', {})
        policy_id = data.get('policyId', '')
        selected_model = data.get('model', 'gemini')  # Default to Gemini
        
        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400
        
        if not current_rules:
            return jsonify({'error': 'No current rules provided'}), 400

        # Use the AI model manager
        result = ai_manager.edit_rules_with_model(selected_model, prompt, current_rules)
        result['model_used'] = selected_model
        
        return jsonify(result)
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/analyze-rule-completeness', methods=['POST'])
def analyze_rule_completeness():
    """Analyze rule engine for completeness using AI"""
    try:
        if not FIREBASE_ENABLED:
            # Mock response when Firebase is disabled
            data = request.get_json()
            mock_findings = [
                "Notice period requirements not clearly defined",
                "Minimum advance approval days missing for vacation leave",
                "Sick leave documentation requirements unclear",
                "Annual leave carry-over policy not specified",
                "Emergency leave approval process not defined"
            ]
            return jsonify({
                'success': True,
                'findings': mock_findings,
                'model_used': data.get('model', 'gemini'),
                'completeness_score': 75
            })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        data = request.get_json()
        onlyRules = [i  for i in data['rules'] if i ]
        data['rules'] = onlyRules
        print("analyze_rule_completeness data:", data['rules'])
        rules = data.get('rules', [])  # Default to empty list instead of dict
        selected_model = data.get('model', 'gemini')
        
        # Handle both list and dict formats for rules
        if isinstance(rules, dict):
            # If rules is a dict, convert to list format or handle appropriately
            if not rules:  # Empty dict
                print("rules is empty dict")
                return jsonify({'error': 'Rules data is required'}), 400
        elif isinstance(rules, list):
            # If rules is a list, check if it's empty
            if not rules:  # Empty list
                print("rules is empty list, length:", len(rules))
                print("rules content:", rules)
                return jsonify({'error': 'Rules data is required. Please generate rules first from the policy analysis.'}), 400
        else:
            print("rules is neither dict nor list, type:", type(rules))
            return jsonify({'error': 'Invalid rules format'}), 400

        print(f"Rules type: {type(rules)}, length: {len(rules) if hasattr(rules, '__len__') else 'N/A'}")
        print(f"Rules content preview: {str(rules)[:200]}...")

        # Use the AI model manager to analyze completeness
        result = ai_manager.analyze_rule_completeness(selected_model, rules)
        result['model_used'] = selected_model
        
        return jsonify(result)
    except Exception as e:
        import traceback
        print("Error occuring ", e)
        print("Error ", traceback.print_exc())
        
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/dismiss-policy-gap', methods=['POST'])
def dismiss_policy_gap():
    """Dismiss a specific policy gap item"""
    try:
        if not FIREBASE_ENABLED:
            # Mock response when Firebase is disabled
            return jsonify({
                'success': True,
                'message': 'Policy gap dismissed successfully (mock mode)'
            })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        data = request.get_json()
        gap_index = data.get('gapIndex')
        gap_type = data.get('gapType', 'finding')  # 'finding' or 'critical'
        gap_text = data.get('gapText', '')
        
        if gap_index is None:
            return jsonify({'error': 'Gap index is required'}), 400
            
        # In a real implementation, you might want to store dismissed gaps
        # For now, we'll just return success
        print(f"Dismissing {gap_type} gap at index {gap_index}: {gap_text}")
        
        return jsonify({
            'success': True,
            'message': f'{gap_type.capitalize()} gap dismissed successfully',
            'dismissed_gap': {
                'index': gap_index,
                'type': gap_type,
                'text': gap_text
            }
        })
        
    except Exception as e:
        import traceback
        print("Error dismissing policy gap:", e)
        print("Error traceback:", traceback.print_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/save-rules', methods=['POST'])
def save_rules():
    """Save leave policy rules to Firestore"""
    try:
        if not FIREBASE_ENABLED:
            return jsonify({'success': True, 'message': 'Mock response: Rules would be saved to Firestore when Firebase is configured.', 'policy_id': 'mock-policy-id'})
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        data = request.get_json()
        rules = data.get('rules', {})
        policy_id = data.get('policyId', None)
        make_active = data.get('makeActive', False)
        
        if not rules:
            return jsonify({'error': 'Rules data is required'}), 400
        
        # If policy_id is provided, update the existing policy
        if policy_id:
            try:
                policy_ref = db.collection('leave_policies').document(policy_id)
                policy_doc = policy_ref.get()
                
                if not policy_doc.exists:
                    return jsonify({'error': 'Policy not found'}), 404
                
                # Update the existing policy
                update_data = {
                    'rules': rules,
                    'updated_at': firestore.SERVER_TIMESTAMP,
                    'updated_by': decoded_token['uid']
                }
                
                policy_ref.update(update_data)
                
                # If makeActive is true, we could implement logic to mark this as active
                # For now, we'll assume the most recently updated policy is active
                
                return jsonify({
                    'success': True,
                    'message': 'Rules updated successfully' + (' and set as active policy' if make_active else ''),
                    'policy_id': policy_id
                })
                
            except Exception as e:
                return jsonify({'error': f'Failed to update policy: {str(e)}'}), 500
        
        else:
            # Create new policy
            policy_data = {
                'rules': rules,
                'uploaded_at': firestore.SERVER_TIMESTAMP,
                'uploaded_by': decoded_token['uid']
            }
            
            # Save to Firestore in the 'leave_policies' collection
            doc_ref = db.collection('leave_policies').add(policy_data)
            
            return jsonify({
                'success': True,
                'message': 'Rules saved successfully to Firestore',
                'policy_id': doc_ref[1].id
            })
        
    except Exception as e:
        return jsonify({'error': f'Failed to save rules: {str(e)}'}), 500

@app.route('/api/leave-types', methods=['GET'])
def get_leave_types():
    """Get available leave types from rule-engine rules"""
    try:
        if not FIREBASE_ENABLED:
            # Return mock leave types for testing
            return jsonify({
                'leave_types': [
                    {'value': 'annual', 'label': 'Annual Leave', 'maxDays': 18},
                    {'value': 'sick', 'label': 'Sick Leave', 'maxDays': 10},
                    {'value': 'maternity', 'label': 'Maternity Leave', 'maxDays': 90},
                    {'value': 'paternity', 'label': 'Paternity Leave', 'maxDays': 5},
                    {'value': 'emergency', 'label': 'Emergency Leave', 'maxDays': 3},
                    {'value': 'compensatory', 'label': 'Compensatory Off', 'maxDays': 5}
                ]
            })
        
        # Get the latest policy rules
        policies_ref = db.collection('leave_policies').order_by('uploaded_at', direction=firestore.Query.DESCENDING).limit(1)
        policies = list(policies_ref.stream())
        
        if not policies:
            # Return default leave types if no policies found
            return jsonify({
                'leave_types': [
                    {'value': 'annual', 'label': 'Annual Leave', 'maxDays': 21},
                    {'value': 'sick', 'label': 'Sick Leave', 'maxDays': 10}
                ]
            })
        
        policy_data = policies[0].to_dict()
        rules = policy_data.get('rules', [])
        
        # Handle both rule-engine format (list) and old JSON format (dict) for backward compatibility
        if isinstance(rules, list):
            # Extract leave types from rule-engine rules
            leave_types = extract_leave_types_from_rules(rules)
        else:
            # Legacy JSON format support
            leave_types_dict = rules.get('leaveTypes', {})
            leave_types = []
            for leave_type, config in leave_types_dict.items():
                if isinstance(config, dict):
                    max_days = config.get('maxDays', 0)
                elif isinstance(config, (int, float)):
                    max_days = int(config)
                else:
                    max_days = 0
                
                leave_types.append({
                    'value': leave_type,
                    'label': leave_type.replace('_', ' ').title() + ' Leave',
                    'maxDays': max_days
                })
        
        return jsonify({'leave_types': leave_types})
        
    except Exception as e:
        print(f"❌ Error fetching leave types: {e}")
        return jsonify({'error': f'Failed to fetch leave types: {str(e)}'}), 500

def extract_leave_types_from_rules(rules):
    """Extract leave types from rule-engine rules"""
    leave_types_found = set()
    leave_type_info = {}
    
    # Default configurations for common leave types
    default_configs = {
        'annual': {'label': 'Annual Leave', 'maxDays': 21},
        'sick': {'label': 'Sick Leave', 'maxDays': 10},
        'maternity': {'label': 'Maternity Leave', 'maxDays': 90},
        'paternity': {'label': 'Paternity Leave', 'maxDays': 5},
        'emergency': {'label': 'Emergency Leave', 'maxDays': 3},
        'personal': {'label': 'Personal Leave', 'maxDays': 5},
        'compensatory': {'label': 'Compensatory Off', 'maxDays': 5},
        'loss_of_pay': {'label': 'Loss of Pay Leave', 'maxDays': 365},
        'bereavement': {'label': 'Bereavement Leave', 'maxDays': 3},
        'marriage': {'label': 'Marriage Leave', 'maxDays': 7}
    }
    
    try:
        for rule in rules:
            if isinstance(rule, str) and 'leave_type ==' in rule:
                # Extract leave type from rule like: leave_type == 'annual'
                import re
                matches = re.findall(r"leave_type\s*==\s*['\"]([^'\"]+)['\"]", rule)
                for leave_type in matches:
                    leave_types_found.add(leave_type)
                    
                    # Try to extract max days from the same rule
                    days_matches = re.findall(r"days_requested\s*<=\s*(\d+)", rule)
                    if days_matches:
                        max_days = int(days_matches[0])
                        leave_type_info[leave_type] = {
                            'maxDays': max_days,
                            'label': default_configs.get(leave_type, {}).get('label', leave_type.replace('_', ' ').title() + ' Leave')
                        }
        
        # Build the final leave types list
        result = []
        for leave_type in sorted(leave_types_found):
            config = leave_type_info.get(leave_type, default_configs.get(leave_type, {
                'label': leave_type.replace('_', ' ').title() + ' Leave',
                'maxDays': 0
            }))
            
            result.append({
                'value': leave_type,
                'label': config['label'],
                'maxDays': config['maxDays']
            })
        
        # If no leave types found in rules, return some defaults
        if not result:
            result = [
                {'value': 'annual', 'label': 'Annual Leave', 'maxDays': 21},
                {'value': 'sick', 'label': 'Sick Leave', 'maxDays': 10}
            ]
        
        print(f"🔍 Extracted leave types: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Error extracting leave types from rules: {e}")
        # Return defaults on error
        return [
            {'value': 'annual', 'label': 'Annual Leave', 'maxDays': 21},
            {'value': 'sick', 'label': 'Sick Leave', 'maxDays': 10}
        ]


def get_employee_name(employee_data, employee_uid=""):
    """Dynamically get employee name from various possible field combinations"""
    try:
        # Try different possible field combinations for employee name
        if 'name' in employee_data:
            # Single name field
            return str(employee_data.get('name', '')).strip()
        elif 'first_name' in employee_data and 'last_name' in employee_data:
            # Separate first_name and last_name fields
            first_name = str(employee_data.get('first_name', '')).strip()
            last_name = str(employee_data.get('last_name', '')).strip()
            return f"{first_name} {last_name}".strip()
        elif 'first_name' in employee_data:
            # Only first_name available
            return str(employee_data.get('first_name', '')).strip()
        elif 'last_name' in employee_data:
            # Only last_name available
            return str(employee_data.get('last_name', '')).strip()
        elif 'full_name' in employee_data:
            # Alternative full_name field
            return str(employee_data.get('full_name', '')).strip()
        elif 'display_name' in employee_data:
            # Alternative display_name field
            return str(employee_data.get('display_name', '')).strip()
        else:
            # Fallback: use email username part or uid
            if 'email' in employee_data:
                email = employee_data.get('email', '')
                return email.split('@')[0] if '@' in email else email
            else:
                return employee_uid[:8] if employee_uid else 'Unknown'  # Use first 8 chars of UID as fallback
    except Exception as e:
        print(f"⚠️ Error getting employee name: {e}")
        return employee_uid[:8] if employee_uid else 'Unknown'


def get_employee_first_name(employee_data):
    """Get employee first name from various possible field combinations"""
    try:
        if 'first_name' in employee_data:
            return str(employee_data.get('first_name', '')).strip()
        elif 'name' in employee_data:
            # Split name field to get first name
            name = str(employee_data.get('name', '')).strip()
            return name.split(' ')[0] if name else ''
        elif 'full_name' in employee_data:
            # Split full_name field to get first name
            name = str(employee_data.get('full_name', '')).strip()
            return name.split(' ')[0] if name else ''
        else:
            return ''
    except Exception as e:
        print(f"⚠️ Error getting employee first name: {e}")
        return ''


def get_employee_last_name(employee_data):
    """Get employee last name from various possible field combinations"""
    try:
        if 'last_name' in employee_data:
            return str(employee_data.get('last_name', '')).strip()
        elif 'name' in employee_data:
            # Split name field to get last name
            name = str(employee_data.get('name', '')).strip()
            name_parts = name.split(' ', 1)
            return name_parts[1] if len(name_parts) > 1 else ''
        elif 'full_name' in employee_data:
            # Split full_name field to get last name
            name = str(employee_data.get('full_name', '')).strip()
            name_parts = name.split(' ', 1)
            return name_parts[1] if len(name_parts) > 1 else ''
        else:
            return ''
    except Exception as e:
        print(f"⚠️ Error getting employee last name: {e}")
        return ''


def validate_leave_request_with_rules(employee_uid, leave_data):
    """Validate leave request against rule-engine rules"""
    try:
        if not FIREBASE_ENABLED:
            return {'valid': True, 'reason': 'Mock validation - always valid when Firebase disabled'}
        
        print(f"🔍 Validating leave request for employee: {employee_uid}")
        print(f"🔍 Leave data: {leave_data}")
        
        # Get the latest policy rules
        policies_ref = db.collection('leave_policies').order_by('uploaded_at', direction=firestore.Query.DESCENDING).limit(1)
        policies = list(policies_ref.stream())
        
        if not policies:
            return {'valid': True, 'reason': 'No policy rules found - request allowed'}
        
        policy_data = policies[0].to_dict()
        rules = policy_data.get('rules', [])
        
        print(f"🔍 Found {len(rules)} policy rules")
        
        # Get employee data
        employee_doc = db.collection('users').document(employee_uid).get()
        if not employee_doc.exists:
            return {'valid': False, 'reason': 'Employee not found'}
        
        employee_data = employee_doc.to_dict()
        if not employee_data:
            return {'valid': False, 'reason': 'Employee data is empty or corrupted'}
        
        # Parse leave request data
        leave_type = leave_data['leave_type']
        start_date = datetime.strptime(leave_data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(leave_data['end_date'], '%Y-%m-%d').date()
        days_requested = (end_date - start_date).days + 1
        
        # Basic setup
        current_date = date.today()
        
        # Calculate tenure based on hire_date
        hire_date = None
        if 'hire_date' in employee_data:
            hire_date_str = employee_data['hire_date']
            # Try to parse different date formats
            for date_format in ['%d %b %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    hire_date = datetime.strptime(hire_date_str, date_format).date()
                    break
                except ValueError:
                    continue
        
        # Calculate tenure
        if hire_date:
            tenure_days = (current_date - hire_date).days
            tenure_months = max(1, tenure_days // 30)  # At least 1 month
            tenure_years = max(1, tenure_days // 365)   # At least 1 year
        else:
            # Default values if hire_date not available
            tenure_months = 12
            tenure_years = 1
            
        # Calculate advance notice
        advance_notice_days = max(0, (start_date - current_date).days)
        
        # Get leave balance
        leave_balance = employee_data.get('leave_balance', 0)
        
        # Calculate previous leave days this year
        year_start = date(current_date.year, 1, 1)
        previous_leave_days = 0
        try:
            leave_requests_ref = db.collection('leave_requests')
            approved_requests = leave_requests_ref.where('employee_uid', '==', employee_uid) \
                                                .where('status', '==', 'approved') \
                                                .stream()
            
            for req in approved_requests:
                req_data = req.to_dict()
                req_start = datetime.strptime(req_data.get('start_date', ''), '%Y-%m-%d').date()
                req_end = datetime.strptime(req_data.get('end_date', ''), '%Y-%m-%d').date()
                if req_start >= year_start:
                    previous_leave_days += (req_end - req_start).days + 1
        except Exception as e:
            print(f"Warning: Could not calculate previous leave days: {e}")
        
        # Calculate remaining leave balance
        leave_remaining_days = max(0, leave_balance - previous_leave_days)
        
        # Check if dates fall on weekends or holidays
        def is_weekend(date_obj):
            return date_obj.weekday() >= 5  # Saturday = 5, Sunday = 6
        
        is_weekend_adjacent = (
            is_weekend(start_date - timedelta(days=1)) or  # Day before is weekend
            is_weekend(end_date + timedelta(days=1)) or    # Day after is weekend
            is_weekend(start_date) or is_weekend(end_date) # Leave dates themselves are weekends
        )
        
        # Public holidays (this should be configurable)
        public_holidays_2024 = ['2024-03-14', '2024-08-15', '2024-10-02', '2024-10-20', '2024-10-21', '2024-12-25']
        public_holidays_2025 = ['2025-03-14', '2025-08-15', '2025-10-02', '2025-10-20', '2025-10-21', '2025-12-25']
        all_public_holidays = public_holidays_2024 + public_holidays_2025
        
        is_public_holiday = start_date.isoformat() in all_public_holidays
        
        # Create comprehensive context for rule evaluation
        context = {
            # Basic employee info with field mapping for rules
            'employee_gender': employee_data.get('gender', ''),  # Map gender to employee_gender
            'employee_department_name': employee_data.get('department', ''),
            'employee_level': employee_data.get('role', '').lower(),
            'employee_id': employee_data.get('employee_id', ''),
            'first_name': employee_data.get('first_name', ''),
            'last_name': employee_data.get('last_name', ''),
            'email': employee_data.get('email', ''),
            
            # Leave request details
            'leave_type': leave_type,
            'days_requested': days_requested,
            'advance_notice_days': advance_notice_days,
            'consecutive_days': days_requested,
            'leave_reason': leave_data.get('reason', ''),
            
            # Employee tenure and status
            'employee_tenure_months': tenure_months,
            'employee_tenure_years': tenure_years,
            'is_probation_period': tenure_months < 6,  # 6 months probation period
            
            # Leave balance and usage
            'leave_balance': leave_balance,
            'leave_remaining_days': leave_remaining_days,
            'previous_leave_days_this_year': previous_leave_days,
            
            # Date information
            'current_date': current_date.isoformat(),
            'request_date': current_date.isoformat(),
            'leave_start_date': start_date.isoformat(),
            'leave_end_date': end_date.isoformat(),
            
            # Calendar and business context
            'is_weekend_adjacent': is_weekend_adjacent,
            'is_holiday_adjacent': False,  # Could be enhanced
            'is_public_holiday': is_public_holiday,
            'holiday_name': '',
            'is_blackout_period': False,  # Could be enhanced based on department/dates
            
            # Request attributes
            'has_medical_certificate': leave_data.get('has_medical_certificate', False),
            'is_emergency': leave_data.get('is_emergency', False),
            'is_recurring_leave': leave_data.get('is_recurring', False),
            
            # Approval requirements
            'manager_approval_required': True,
            'hr_approval_required': days_requested > 5 or leave_type in ['maternity', 'paternity'],
        }
        
        # Copy all original employee data as well (for any unmapped fields)
        for key, value in employee_data.items():
            if key not in context:
                context[key] = value
        
        print(f"🔍 Rule evaluation context prepared with {len(context)} fields")
        
        # Filter and validate rules
        passed_rules = []
        failed_rules = []
        error_rules = []
        
        for rule_str in rules:
            if not isinstance(rule_str, str) or not rule_str.strip():
                continue
                
            # Clean up the rule string (remove 'rule:' prefix if present)
            clean_rule = rule_str.replace('rule:', '').strip()
            if not clean_rule:
                continue
            
            try:
                import rule_engine
                rule = rule_engine.Rule(clean_rule)
                
                if rule.matches(context):
                    passed_rules.append(clean_rule)
                    print(f"✅ Rule passed: {clean_rule}")
                else:
                    # Check if this is a positive or negative rule
                    if any(keyword in clean_rule.lower() for keyword in ['not', '!=', '<', 'false']):
                        # This might be a negative constraint that should pass when false
                        # For now, treat negative rules that fail as warnings, not blockers
                        print(f"⚠️ Negative rule failed (may be expected): {clean_rule}")
                    else:
                        failed_rules.append(clean_rule)
                        print(f"❌ Rule failed: {clean_rule}")
                        
            except Exception as e:
                error_rules.append(f"{clean_rule}: {str(e)}")
                print(f"⚠️ Error evaluating rule '{clean_rule}': {e}")
        
        print(f"📊 Rule validation summary:")
        print(f"   ✅ Passed: {len(passed_rules)}")
        print(f"   ❌ Failed: {len(failed_rules)}")
        print(f"   ⚠️ Errors: {len(error_rules)}")
        
        # Determine validation result
        if failed_rules:
            # Check if failed rules are critical or just warnings
            critical_failures = []
            for rule in failed_rules:
                # Skip certain types of rules that might be expected to fail
                if not any(skip_word in rule.lower() for skip_word in [
                    'not (',  # negative conditions
                    'blackout_period == true',  # specific date restrictions
                    'is_public_holiday == true',  # holiday restrictions
                ]):
                    critical_failures.append(rule)
            
            if critical_failures:
                return {
                    'valid': False,
                    'reason': f'Leave request violates {len(critical_failures)} policy rule(s). Please check: {critical_failures[0][:100]}...'
                }
        
        # If no critical failures, approve the request
        validation_notes = []
        if passed_rules:
            validation_notes.append(f"{len(passed_rules)} policy rules satisfied")
        if error_rules:
            validation_notes.append(f"{len(error_rules)} rules had evaluation errors")
        
        return {
            'valid': True,
            'reason': '; '.join(validation_notes) if validation_notes else 'Request meets policy requirements'
        }
        
    except Exception as e:
        print(f"❌ Error in rule validation: {e}")
        import traceback
        traceback.print_exc()
        return {'valid': True, 'reason': f'Validation completed with warnings: {str(e)}'}  # Allow request but log error



def validate_leave_request_with_rules_new(employee_uid, leave_data):
    """Validate leave request against rule-engine rules"""
    try:
        if not FIREBASE_ENABLED:
            return {'valid': True, 'reason': 'Mock validation - always valid when Firebase disabled'}
        
        print(f"🔍 Validating leave request for employee: {employee_uid}")
        print(f"🔍 Leave data: {leave_data}")
        
        # Get the latest policy rules
        policies_ref = db.collection('leave_policies').order_by('uploaded_at', direction=firestore.Query.DESCENDING).limit(1)
        policies = list(policies_ref.stream())
        
        if not policies:
            return {'valid': True, 'reason': 'No policy rules found - request allowed'}
        
        policy_data = policies[0].to_dict()
        rules = policy_data.get('rules', [])
        
        print(f"🔍 Policy rules: {rules}")
        
        # Get employee data
        employee_doc = db.collection('users').document(employee_uid).get()
        if not employee_doc.exists:
            return {'valid': False, 'reason': 'Employee not found'}
        
        employee_data = employee_doc.to_dict()
        if not employee_data:
            return {'valid': False, 'reason': 'Employee data is empty or corrupted'}
        
        # Copy all fields from employee_data to context
        context = employee_data.copy()
        
        # Parse leave request data
        leave_type = leave_data['leave_type']
        start_date = datetime.strptime(leave_data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(leave_data['end_date'], '%Y-%m-%d').date()
        days_requested = (end_date - start_date).days + 1
        
        # Basic setup
        current_date = date.today()
        request_date = current_date  # Assume request is made today
        
        # Calculate tenure based on DOJ
        doj = None
        if 'DOJ' in context:
            doj_str = context['DOJ']
            # Try to parse different date formats
            for date_format in ['%d %b %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                try:
                    doj = datetime.strptime(doj_str, date_format).date()
                    break
                except ValueError:
                    continue
        elif 'hire_date' in context:
            try:
                doj = datetime.strptime(context['hire_date'], '%Y-%m-%d').date()
            except:
                pass
        
        # Set default values if parsing failed
        if doj:
            tenure_days = (current_date - doj).days
            tenure_months = tenure_days // 30
            tenure_years = tenure_days // 365
        else:
            tenure_months = 12
            tenure_years = 1
            
        # Calculate advance notice
        advance_notice_days = (start_date - current_date).days
        
        # Check weekend adjacency
        def is_weekend(date_obj):
            return date_obj.weekday() >= 5  # Saturday = 5, Sunday = 6
        
        is_weekend_adjacent = (
            is_weekend(start_date - timedelta(days=1)) or  # Day before is weekend
            is_weekend(end_date + timedelta(days=1))       # Day after is weekend
        )
        
        # Calculate previous leave days this year
        year_start = date(current_date.year, 1, 1)
        previous_leave_days = 0
        try:
            leave_requests_ref = db.collection('leave_requests')
            approved_requests = leave_requests_ref.where('employee_uid', '==', employee_uid) \
                                                .where('status', '==', 'approved') \
                                                .stream()
            
            for req in approved_requests:
                req_data = req.to_dict()
                req_start = datetime.strptime(req_data.get('start_date', ''), '%Y-%m-%d').date()
                req_end = datetime.strptime(req_data.get('end_date', ''), '%Y-%m-%d').date()
                if req_start >= year_start:
                    previous_leave_days += (req_end - req_start).days + 1
        except Exception as e:
            print(f"Warning: Could not calculate previous leave days: {e}")

        
        mapping = {
            "annual": "Annual Leave",
            "paid": "Paid Leave",
            "maternity": "Maternity",
            "paternity": "Paternity",
            "compensatory": "Compensatory Off",
            "sick": "Sick Leave"
        }
        
        # Add/override calculated fields to context
        context.update({
            # Basic leave details
        
            'leave_type': leave_type,
            'days_requested': days_requested,
            'advance_notice_days': advance_notice_days,
            'consecutive_days': days_requested,
            
            # Employee calculated fields
            'employee_tenure_months': tenure_months,
            'employee_tenure_years': tenure_years,
            'is_probation_period': tenure_months < 6,  # Assume 6 month probation
            
            # Date and calendar info
            'current_date': current_date.isoformat(),
            'request_date': request_date.isoformat(),
            'leave_start_date': start_date.isoformat(),
            'leave_end_date': end_date.isoformat(),
            
            # Leave request attributes
            'has_medical_certificate': leave_data.get('has_medical_certificate', False),
            'is_emergency': leave_data.get('is_emergency', False),
            'leave_reason': leave_data.get('reason', ''),
            'is_recurring_leave': leave_data.get('is_recurring', False),
            
            # Calendar and business context
            'is_weekend_adjacent': is_weekend_adjacent,
            'is_holiday_adjacent': False,  # TODO: Implement holiday checking
            'is_public_holiday': False,    # TODO: Implement holiday checking
            'holiday_name': '',            # TODO: Implement holiday checking
            'is_blackout_period': False,   # TODO: Implement blackout period checking
            
            # Approval requirements
            'manager_approval_required': days_requested > 0,  # Default: always required
            'hr_approval_required': days_requested > 5 or context.get('leave_type') in ['Maternity', 'Paternity', 'Sabbatical'],
            
            # Usage tracking
            'previous_leave_days_this_year': previous_leave_days,
            
            # Field mappings for rule compatibility
            'employee_gender': context.get('gender', 'not_specified'),
            'employee_status': context.get('employment_type', context.get('status', 'Inactive')),  # Use employment_type first, fallback to status
            'employee_employment_type': context.get('employment_type', context.get('status', 'Active')),
            'employee_balance': context.get('leave_balance', 0),
        })
        
        # Normalize data for rule compatibility
        # Map leave types to match rule expectations
        leave_type_mapping = {
            'annual': 'Annual Leave',
            'paid': 'Paid Leave', 
            'maternity': 'Maternity',
            'paternity': 'Paternity',
            'compensatory': 'Compensatory Off',
            'sick': 'Sick Leave',
            'emergency': 'Emergency Leave'
        }
        
        # Convert leave_type to match rule format
        mapped_leave_type = leave_type_mapping.get(leave_type.lower(), leave_type.title())
        context['leave_type'] = mapped_leave_type
        
        print(f"🔍 Enhanced rule context: {context}")
        
        # Filter rules to only those that apply to the requested leave type
        relevant_rules = []
        for rule_str in rules:
            if isinstance(rule_str, str):
                # Check if this rule applies to the requested leave type
                if f"leave_type == '{mapped_leave_type}'" in rule_str:
                    relevant_rules.append(rule_str)
                # Check for rules that match the leave type in a list (like "leave_type in ['Paid Leave', 'Annual Leave']")
                elif f"'{mapped_leave_type}'" in rule_str and 'leave_type in' in rule_str:
                    relevant_rules.append(rule_str)
                # Also include general rules that don't specify a leave type
                elif 'leave_type ==' not in rule_str and 'leave_type in' not in rule_str:
                    relevant_rules.append(rule_str)
        
        print(f"🔍 Relevant rules for {leave_type}: {relevant_rules}")

        def clean_rule(rule_str: str) -> str:
            rule = rule_str.strip()
            if rule.lower().startswith("rule:"):
                rule = rule.split("rule:", 1)[1].strip()
            
            # Fix common typos in rules
            rule = rule.replace("is_emergencyy", "is_emergency")
            rule = rule.replace("emergencyy", "emergency")  # More general fix
            
            # Keep boolean values as lowercase for rule-engine compatibility
            # The rule-engine library expects 'true'/'false', not 'True'/'False'
            rule = rule.replace(" == True", " == true")
            rule = rule.replace(" == False", " == false")
            rule = rule.replace(" != True", " != true") 
            rule = rule.replace(" != False", " != false")
            
            return rule

        
        # Validate against each relevant rule
        failed_rules = []
        passed_rules = []
        
        for rule_str in relevant_rules:
            try:
                expr = clean_rule(rule_str)
                print(f"🔍 Evaluating rule: {expr}")
                rule = rule_engine.Rule(expr)
                result = rule.matches(context)
                print(f"🔍 Rule result: {result}")
                if not result:
                    failed_rules.append(rule_str)
                    print(f"❌ Rule failed: {rule_str}")
                else:
                    passed_rules.append(rule_str)
                    print(f"✅ Rule passed: {rule_str}")
            except Exception as e:
                print(f"⚠️ Error evaluating rule '{rule_str}': {e}")
                print(f"   Cleaned expression: '{expr}'")
                print(f"   Error type: {type(e).__name__}")
                
                # For SymbolResolutionError, try to identify missing variables
                if "SymbolResolutionError" in str(type(e)):
                    print(f"   This might be due to missing context variables")
                    print(f"   Available context keys: {list(context.keys())}")
                    print(f"   Full error message: {str(e)}")
                    
                    # Check if specific variables exist
                    required_vars = ['is_probation_period', 'is_emergency']
                    for var in required_vars:
                        if var in context:
                            print(f"   ✅ {var} = {context[var]} (type: {type(context[var])})")
                        else:
                            print(f"   ❌ {var} is missing from context")
                    
                    # Try to manually evaluate the expression to see what's wrong
                    try:
                        # Create a local scope with the context variables
                        local_scope = context.copy()
                        result = eval(expr, {"__builtins__": {}}, local_scope)
                        print(f"   Manual eval result: {result}")
                        if not result:
                            failed_rules.append(rule_str)
                            print(f"❌ Rule failed (manual eval): {rule_str}")
                        else:
                            passed_rules.append(rule_str)
                            print(f"✅ Rule passed (manual eval): {rule_str}")
                        continue
                    except Exception as eval_e:
                        print(f"   Manual eval also failed: {eval_e}")
                    
                    # Skip this rule if we can't resolve it
                    print(f"   Skipping rule due to unresolvable context variables")
                    continue
                else:
                    # Treat other errors as failed rules
                    failed_rules.append(rule_str)
        
        # Check if we have any specific leave type rules that passed
        leave_type_specific_rules_passed = [rule for rule in passed_rules if f"leave_type == '{mapped_leave_type}'" in rule or f"'{mapped_leave_type}'" in rule and 'leave_type in' in rule]
        
        if leave_type_specific_rules_passed:
            print(f"✅ Leave request approved - specific rules passed: {leave_type_specific_rules_passed}")
            return {'valid': True, 'reason': f'Request satisfies {len(leave_type_specific_rules_passed)} specific policy rules'}
        
        # Provide user-friendly error messages based on failed rules
        def get_user_friendly_error(failed_rules, context, leave_type):
            """Convert technical rule failures into user-friendly messages"""
            
            # Check for common validation failures
            for rule in failed_rules:
                # Gender-based restrictions
                if 'employee_gender' in rule and leave_type.lower() == 'paternity':
                    if context.get('employee_gender') != 'Male':
                        return 'Paternity leave is only available for male employees.'
                
                if 'employee_gender' in rule and leave_type.lower() == 'maternity':
                    if context.get('employee_gender') != 'Female':
                        return 'Maternity leave is only available for female employees.'
                
                # Tenure requirements
                if 'employee_tenure_years >= 1' in rule:
                    if context.get('employee_tenure_years', 0) < 1:
                        return f'This leave type requires at least 1 year of employment. You have {context.get("employee_tenure_years", 0)} years of tenure.'
                
                if 'employee_tenure_months >= 12' in rule:
                    if context.get('employee_tenure_months', 0) < 12:
                        return f'This leave type requires at least 12 months of employment. You have {context.get("employee_tenure_months", 0)} months of tenure.'
                
                # Balance requirements
                if 'employee_balance >=' in rule:
                    balance = context.get('employee_balance', 0)
                    days_requested = context.get('days_requested', 0)
                    if balance < days_requested:
                        return f'Insufficient leave balance. You have {balance} days available but requested {days_requested} days.'
                
                # Advance notice requirements
                if 'advance_notice_days >=' in rule:
                    advance_notice = context.get('advance_notice_days', 0)
                    if 'advance_notice_days >= 15' in rule and advance_notice < 15:
                        return f'This leave requires at least 15 days advance notice. You provided {advance_notice} days notice.'
                    elif 'advance_notice_days >= 60' in rule and advance_notice < 60:
                        return f'This leave requires at least 60 days advance notice. You provided {advance_notice} days notice.'
                
                # Employment status
                if "employee_status == 'Active'" in rule:
                    if context.get('employee_status') != 'Active':
                        return f'Leave can only be requested by active employees. Your current status is: {context.get("employee_status", "Unknown")}'
                
                # Employment type restrictions
                if 'employee_employment_type in' in rule:
                    employment_type = context.get('employee_employment_type', 'Unknown')
                    if employment_type not in ['Full-Time', 'Intern']:
                        return f'This leave type is only available for Full-Time and Intern employees. Your employment type is: {employment_type}'
                
                # Probation period restrictions
                if 'is_probation_period == False' in rule:
                    if context.get('is_probation_period', False):
                        return 'Leave requests are not allowed during probation period unless it\'s an emergency.'
                
                # Weekend/Holiday restrictions
                if 'is_weekend_adjacent == False' in rule:
                    if context.get('is_weekend_adjacent', False):
                        return 'Leave requests cannot be adjacent to weekends according to company policy.'
                
                if 'is_holiday_adjacent == False' in rule:
                    if context.get('is_holiday_adjacent', False):
                        return 'Leave requests cannot be adjacent to public holidays according to company policy.'
                
                # Blackout period restrictions
                if 'is_blackout_period == False' in rule:
                    if context.get('is_blackout_period', False):
                        return 'Leave requests are not allowed during blackout periods.'
                
                # Date validation
                if 'leave_start_date >= current_date' in rule:
                    return 'Leave start date must be in the future.'
                
                if 'leave_end_date >= leave_start_date' in rule:
                    return 'Leave end date must be on or after the start date.'
                
                # Department restrictions
                if 'employee_department_name !=' in rule:
                    dept = context.get('employee_department_name', '')
                    if 'Support Team' in rule and dept.lower() == 'support team':
                        return 'This leave type is not available for Support Team members.'
                
                # Leave count restrictions
                if 'previous_leave_count <' in rule:
                    leave_count = context.get('previous_leave_count', 0)
                    if 'previous_leave_count < 5' in rule and leave_count >= 5:
                        return f'You have reached the maximum number of leave requests for this period. Current count: {leave_count}'
                
                # Annual entitlement restrictions
                if 'previous_leave_days_this_year + days_requested <= total_annual_entitled_days' in rule:
                    prev_days = context.get('previous_leave_days_this_year', 0)
                    requested_days = context.get('days_requested', 0)
                    total_entitled = context.get('total_annual_entitled_days', 0)
                    if prev_days + requested_days > total_entitled:
                        return f'This request would exceed your annual leave entitlement. You have used {prev_days} days out of {total_entitled} total entitled days.'
            
            # Default fallback message
            return f'Leave request does not meet the policy requirements for {leave_type.title()} leave.'
        
        # Check for specific error cases to provide better error messages
        leave_type_specific_failed_rules = [rule for rule in failed_rules if f"leave_type == '{leave_type.title()}'" in rule]
        
        if leave_type_specific_failed_rules or failed_rules:
            user_friendly_error = get_user_friendly_error(failed_rules, context, leave_type)
            return {
                'valid': False,
                'reason': user_friendly_error
            }
        
        # If no specific rules passed, check if we have general rules that passed
        general_rules_passed = [rule for rule in passed_rules if 'leave_type ==' not in rule]
        
        if general_rules_passed and not failed_rules:
            print(f"✅ Leave request approved - general rules satisfied")
            return {'valid': True, 'reason': 'Request satisfies general policy rules'}
        
        return {'valid': True, 'reason': 'All policy rules satisfied'}
        
    except Exception as e:
        print(f"❌ Error in rule validation: {e}")
        return {'valid': False, 'reason': f'Validation error: {str(e)}'}


@app.route('/api/admin/policies', methods=['GET'])
def get_policies():
    """Get all saved leave policies from Firestore"""
    try:
        if not FIREBASE_ENABLED:
            # Return mock data for testing
            return jsonify({
                'policies': [
                    {
                        'id': 'mock-policy-1',
                        'uploaded_at': '2024-01-15T10:30:00Z',
                        'uploaded_by': 'admin@example.com',
                        'rules': {
                            'leaveTypes': {
                                'annual': {'maxDays': 21},
                                'sick': {'maxDays': 10},
                                'maternity': {'maxDays': 90}
                            }
                        }
                    }
                ]
            })
            
        # Verify admin token
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        decoded_token = auth.verify_id_token(id_token)
        admin_doc = db.collection('users').document(decoded_token['uid']).get()
        if not admin_doc.exists or admin_doc.to_dict().get('role') != 'admin':
            return jsonify({'error': 'Access denied. Admin role required.'}), 403

        # Fetch all policies from Firestore, ordered by upload date (newest first)
        policies_ref = db.collection('leave_policies')
        policies_query = policies_ref.order_by('uploaded_at', direction=firestore.Query.DESCENDING)
        policies_docs = policies_query.get()
        
        policies = []
        for doc in policies_docs:
            policy_data = doc.to_dict()
            policy_data['id'] = doc.id
            # Convert timestamp to ISO string if it exists
            if 'uploaded_at' in policy_data and policy_data['uploaded_at']:
                try:
                    policy_data['uploaded_at'] = policy_data['uploaded_at'].isoformat()
                except:
                    policy_data['uploaded_at'] = str(policy_data['uploaded_at'])
            policies.append(policy_data)
        
        return jsonify({'policies': policies})
        
    except Exception as e:
        return jsonify({'error': f'Failed to fetch policies: {str(e)}'}), 500
def get_one_employee():
    docs = db.collection('users').where('role', '==', 'employee').limit(1).stream()
    for doc in docs:
        return doc.to_dict()
    return None


if __name__ == '__main__':
    if FIREBASE_ENABLED:
        print("🚀 Starting HR Portal API with Firebase integration")
        print("✅ Full functionality enabled")
    else:
        print("🚀 Starting HR Portal API in Mock Mode")
        print("⚠️  Firebase credentials not configured - using mock data")
        print("📝 To enable full functionality, update the .env file with your Firebase credentials")
    
    print("🌐 Frontend should connect to: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)



