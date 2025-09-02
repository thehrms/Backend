from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore import SERVER_TIMESTAMP
import os , string
import pandas as pd
import json
import re
import requests
import random
import traceback
from app import app
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
# Check if Firebase credentials are available
service_account_path = "aihrms2-firebase-adminsdk-fbsvc-fce522b367.json"
#client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        
        # Initialize Firebase Admin SDK
        if not firebase_admin._apps:
            if os.path.exists(service_account_path):
                print("🔑 Using service account key file for Firebase authentication")
                cred = credentials.Certificate(service_account_path)
            else:
                print("🔑 Using environment variables for Firebase authentication")
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": "ai-hrms-35186",  # Changed from "fe-be-deployment" to match your JSON
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
        print(f"❌ Traceback: {traceback.format_exc()}")
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

# def openai_map_columns(target_fields, uploaded_headers):
#     """Map target schema fields to uploaded headers using OpenAI (with heuristic fallback)."""
#     try:
#         prompt = f"""
# You are given a list of target database fields and a list of uploaded file column names.
# Map each target field to the best matching uploaded column name. 
# If no suitable match exists, return null.

# Target fields:
# {json.dumps(target_fields, indent=2)}

# Uploaded headers:
# {json.dumps(uploaded_headers, indent=2)}

# Return ONLY valid JSON with keys: mapping and confidence.
# """

#         response = client.chat.completions.create(
#             model="gpt-4o-mini",  # or "gpt-4o" if you want bigger model
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant for schema mapping."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.0,
#             max_tokens=1000
#         )

#         answer_text = response.choices[0].message.content

#         m = re.search(r'\{[\s\S]*\}', answer_text)
#         if not m:
#             raise Exception("No JSON found in OpenAI response")

#         mapping_obj = json.loads(m.group(0))
#         mapping = mapping_obj.get("mapping", {})
#         confidence = mapping_obj.get("confidence", {})

#         # Filter mapping so only target_fields remain
#         filtered_mapping = {
#             tf: (mapping.get(tf) if mapping.get(tf) in uploaded_headers else None)
#             for tf in target_fields
#         }

#         return filtered_mapping, confidence

#     except Exception as e:
#         print(f"⚠️ OpenAI mapping failed, using heuristic. Error: {e}")

#         def normalize(s): 
#             return re.sub(r'[^a-z0-9]', '', s.lower()) if s else ''
        
#         norm_to_target = {normalize(t): t for t in target_fields}
#         mapping, confidence = {}, {}

#         for h in uploaded_headers:
#             nh = normalize(h)
#             mapped = norm_to_target.get(nh)
#             if mapped:
#                 mapping[mapped] = h
#                 confidence[h] = 0.95
#             else:
#                 confidence[h] = 0.1

#         return mapping, confidence

def gemini_map_columns(target_fields, uploaded_headers):
    """Map target schema fields to uploaded headers using Gemini (with heuristic fallback)."""
    try:
        prompt = f"""
You are given a list of target database fields and a list of uploaded file column names.
Map each target field to the best matching uploaded column name. 
If no suitable match exists, return null.

Target fields:
{json.dumps(target_fields, indent=2)}

Uploaded headers:
{json.dumps(uploaded_headers, indent=2)}

Return ONLY valid JSON with keys: mapping and confidence.
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/{os.getenv('GEMINI_MODEL')}:generateContent"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096}
        }

        resp = requests.post(f"{url}?key={os.getenv('GEMINI_API_KEY')}", headers=headers, json=data, timeout=30)
        if not resp.ok:
            raise Exception(f"Gemini API error: {resp.status_code} {resp.text}")

        result = resp.json()
        answer_text = result["candidates"][-1]["content"]["parts"][-1]["text"]
        m = re.search(r'\{[\s\S]*\}', answer_text)
        if not m:
            raise Exception("No JSON found in Gemini response")

        mapping_obj = json.loads(m.group(0))
        mapping = mapping_obj.get("mapping", {})
        confidence = mapping_obj.get("confidence", {})

        # Filter mapping so only target_fields remain
        filtered_mapping = {tf: (mapping.get(tf) if mapping.get(tf) in uploaded_headers else None) for tf in target_fields}

        return filtered_mapping, confidence

    except Exception as e:
        print(f"⚠️ Gemini mapping failed, using heuristic. Error: {e}")
        def normalize(s): return re.sub(r'[^a-z0-9]', '', s.lower()) if s else ''
        norm_to_target = {normalize(t): t for t in target_fields}
        mapping, confidence = {}, {}
        for h in uploaded_headers:
            nh = normalize(h)
            mapped = norm_to_target.get(nh)
            if mapped:
                mapping[mapped] = h
                confidence[h] = 0.95
            else:
                confidence[h] = 0.1
        return mapping, confidence

def insert_data_to_db(df):

    created_users = []
    errors = []
    df.columns = [str(c).strip().lower().replace('\ufeff', '') for c in df.columns]
    # Get all column names from the DataFrame
    columns = df.columns.tolist()
    print(f"📊 Excel columns detected: {columns}")
    # Load canonical target schema fields
    try:
        if not hasattr(app, '_cached_target_fields'):
            schema_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'employee_schema.json')
            schema_path = os.path.abspath(schema_path)
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)

            fields = set()
            #emp_schema = schema.get('employee_schema', {}) if isinstance(schema, dict) else {}
            
            def flatten(obj, parent_key=""):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ("type", "format", "enum", "required", "properties", "items", "minimum"):
                            continue  # skip schema keywords

                        new_key = f"{parent_key}.{k}" if parent_key else k

                        # Always add this key as a potential field
                        fields.add(new_key)

                        # Recurse deeper if needed
                        if isinstance(v, dict):
                            flatten(v, new_key)
                        elif isinstance(v, list):
                            for it in v:
                                flatten(it, new_key)


            flatten(schema.get("employee_schema", {}))
            fields.update(['uid', 'employee_id', 'first_name', 'last_name', 'email', 
                            'phone', 'role', 'source_file_columns'])
            app._cached_target_fields = list(fields)
        target_fields = app._cached_target_fields
    except Exception as e:
        print(f"⚠️ Failed to load employee_schema.json: {e}")
        target_fields = [
            'uid', 'employee_id', 'first_name', 'last_name', 'email', 'phone',
            'department', 'designation', 'date_of_joining', 'employment_type',
            'role', 'temporary_password', 'leave_balance', 'source_file_columns',
            'created_at', 'last_updated'
       ]

    # Map uploaded headers to target schema
    mapping, mapping_conf = gemini_map_columns(target_fields, columns)
    print(f"🧭 Column mapping: {mapping}")
    print(f"🔎 Mapping confidences: {mapping_conf}")
    print(f"🔎 target_fields sample: {target_fields[:40]} (total {len(target_fields)})")

    for index, row in df.iterrows():
        try:
            # Convert row data to dict
            row_data = {col: ('' if pd.isna(row.get(col)) else str(row.get(col)).strip()) for col in columns}
            
            # First name / last name resolution
            first_name, last_name = '', ''
            if 'first_name' in mapping and mapping['first_name']:
                raw_name = row_data.get(mapping['first_name'], '')
                if raw_name:
                    parts = raw_name.split()
                    first_name = parts[0]
                    last_name = " ".join(parts[1:]) if len(parts) > 1 else ''

            if not first_name:
                first_name = f"Employee{index+1}"

            # Email
            email = None
            if 'email' in mapping and mapping['email'] and row_data.get(mapping['email']):
                email = row_data[mapping['email']]
            if not email:
                email = generate_employee_email(first_name)

            password = generate_random_password()

            display_name = first_name
            if 'last_name' in mapping and mapping['last_name'] and row_data.get(mapping['last_name']):
                display_name = f"{first_name} {row_data[mapping['last_name']]}"

            # Create Firebase user
            user_record = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )

            # Start user_data with canonical fields
            user_data = {
                'uid': user_record.uid,
                'email': email,
                'role': 'employee',
                'created_at': SERVER_TIMESTAMP,
                'temporary_password': password,
                'source_file_columns': columns,
                'first_name': first_name
            }
            if last_name:
                user_data['last_name'] = last_name
                
            # Only map values that exist in target schema
            for target_field, uploaded_header in mapping.items():
                if target_field in ("first_name", "last_name"):
                    continue
                if uploaded_header and target_field in target_fields:
                    norm_uploaded = str(uploaded_header).strip().lower().replace('\ufeff', '')
                    value = row_data.get(norm_uploaded, '')
                    if value not in ('', None) and not pd.isna(value):
                        user_data[target_field] = str(value).strip()
                    #user_data[target_field] = '' if pd.isna(value) else str(value).strip()


            # Random leave balance
            user_data['leave_balance'] = random.randint(4, 15)

            user_data = {k: v for k, v in user_data.items() if v not in ('', None)}

            # # Ensure all target_fields exist
            # for tf in target_fields:
            #     if tf in ('uid', 'created_at', 'source_file_columns'):
            #         continue
            #     if tf not in user_data:
            #         user_data[tf] = ''

            # Save to Firestore
            db.collection('users').document(user_record.uid).set(user_data)

            created_users.append({
                'email': email,
                'name': display_name,
                'data': {k: user_data.get(k, '') for k in target_fields},
                'temporary_password': password,
                'leave_balance': user_data['leave_balance']
            })

        except Exception as e:
            errors.append(f"Row {index+2}: {str(e)}")
    
    return created_users, errors