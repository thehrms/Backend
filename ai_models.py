"""
AI Model Integration Module
Supports Gemini, ChatGPT, Claude, and DeepSeek models
"""

import os
import requests
import json
import base64
from typing import Dict, Any, Optional, List, Union


class AIModelManager:
    """Manages multiple AI model integrations"""
    
    def __init__(self):
        self.api_keys = {
            'gemini': os.getenv('GEMINI_API_KEY'),
            'chatgpt': os.getenv('OPENAI_API_KEY'),
            'claude': os.getenv('ANTHROPIC_API_KEY'),
            'deepseek': os.getenv('DEEPSEEK_API_KEY')
        }
        
        # Model configurations
        self.model_configs = {
            'gemini': {
                'url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent',
                'name': 'gemini-2.0-flash',
                'supports_pdf': True,
                'max_tokens': 8096,
                'pdf_method': 'native'
            },
            
            'chatgpt': {
                'url': 'https://api.openai.com/v1/chat/completions',
                'model': 'gpt-4o-2024-08-06', # 'gpt-4o-mini',
                'name': 'ChatGPT 4o',
                'supports_pdf': True,
                'max_tokens': 16384,
                'pdf_method': 'gemini_extraction'
            },
            'claude': {
                'url': 'https://api.anthropic.com/v1/messages',
                'model': 'claude-3-7-sonnet-20250219',
                'name': 'Claude 3 Sonnet',
                'supports_pdf': True,
                'max_tokens': 4096,
                'pdf_method': 'gemini_extraction'
            },
            'deepseek': {
                'url': 'https://api.deepseek.com/v1/chat/completions',
                'model': 'deepseek-chat',
                'name': 'DeepSeek Chat',
                'supports_pdf': True,
                'max_tokens': 4096,
                'pdf_method': 'gemini_extraction'
            }
        }
    
    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        """Get list of available models with their capabilities"""
        available = {}
        gemini_available = bool(self.api_keys.get('gemini'))
        
        for model_id, config in self.model_configs.items():
            if self.api_keys.get(model_id):
                # PDF support depends on Gemini being available for extraction
                supports_pdf = config['supports_pdf'] and (model_id == 'gemini' or gemini_available)
                
                available[model_id] = {
                    'name': config['name'],
                    'supports_pdf': supports_pdf,
                    'max_tokens': config['max_tokens'],
                    'pdf_method': config.get('pdf_method', 'native')
                }
        return available
    
    def analyze_policy_with_model(self, model_id: str, pdf_bytes: bytes = None, prompt: str = None) -> str:
        """Analyze policy document using specified AI model"""
        if model_id not in self.api_keys or not self.api_keys[model_id]:
            raise ValueError(f"API key not configured for {model_id}")
        
        # Check if Gemini is available for PDF extraction (required for non-Gemini models)
        if pdf_bytes and model_id != 'gemini' and not self.api_keys.get('gemini'):
            raise ValueError("Gemini API key is required for PDF text extraction with non-Gemini models")
        
        # Step 1: Extract text from PDF using Gemini (if PDF is provided)
        extracted_text = None
        if pdf_bytes:
            try:
                # Use Gemini to extract text from PDF
                extracted_text = self._extract_text_from_pdf_with_gemini(pdf_bytes)
                print(f"✅ Successfully extracted text from PDF using Gemini")
            except Exception as e:
                print(f"⚠️ Failed to extract text from PDF: {e}")
                # If extraction fails, fall back to original behavior
                if model_id == 'gemini':
                    print("Called Gemini for analysis in the first exception")
                    return self._analyze_with_gemini(pdf_bytes, prompt)

                else:
                    raise Exception("PDF text extraction failed and selected model doesn't support PDF")
        
        # Step 2: Use selected model for analysis
        if model_id == 'gemini' and not extracted_text:
            # Use Gemini's native PDF support if no text was extracted
            return self._analyze_with_gemini(pdf_bytes, prompt)
        elif model_id == 'gemini' and extracted_text:
            print("Called Gemini for analysis with extracted text")
            # Use Gemini with extracted text
            analysis_prompt = self._create_text_analysis_prompt(extracted_text, prompt)
            print("@#$#@#"*10)
            print("Calling to the Analysis Prompt with extracted_text")
            return self._chat_with_gemini(analysis_prompt)
        
        elif model_id == 'chatgpt':
            if not extracted_text:
                raise Exception("PDF text extraction required for ChatGPT")
            analysis_prompt = self._create_text_analysis_prompt(extracted_text, prompt)
            return self._analyze_with_chatgpt(analysis_prompt)
        
        
        elif model_id == 'claude':
            if not extracted_text:
                raise Exception("PDF text extraction required for Claude")
            analysis_prompt = self._create_text_analysis_prompt(extracted_text, prompt)
            return self._analyze_with_claude(analysis_prompt)
        elif model_id == 'deepseek':
            if not extracted_text:
                raise Exception("PDF text extraction required for DeepSeek")
            analysis_prompt = self._create_text_analysis_prompt(extracted_text, prompt)
            return self._analyze_with_deepseek(analysis_prompt)
        else:
            raise ValueError(f"Unsupported model: {model_id}")
    
    def _extract_text_from_pdf_with_gemini(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF using Gemini"""
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        extraction_prompt = """
Please extract and return ONLY the text content from this PDF document. 
Do not analyze or summarize - just provide the raw text exactly as it appears in the document.
Maintain the original structure, headings, and formatting as much as possible.
"""
        
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": extraction_prompt},
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
                "maxOutputTokens": 8192  # Higher limit for text extraction
            }
        }
        
        config = self.model_configs['gemini']
        response = requests.post(
            f"{config['url']}?key={self.api_keys['gemini']}", 
            headers={"Content-Type": "application/json"}, 
            json=data
        )
        
        if response.ok:
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise Exception(f"Gemini text extraction error ({response.status_code}): {response.text}")
    
    def _create_text_analysis_prompt(self, extracted_text: str, custom_prompt: str = None) -> str:
        """Create analysis prompt combining extracted text with analysis instructions"""
        base_prompt = custom_prompt or self._get_default_policy_analysis_prompt()
        # from app import get_one_employee
        # example_emp_records = get_one_employee()
        
        # Remove sensitive fields
        # if example_emp_records:
        #     for field in ['created_at', 'temporary_password', 'uid']:
        #         if field in example_emp_records:
        #             example_emp_records.pop(field)
        #     print("example_emp_records: ", example_emp_records)
        
        return f"""
                {base_prompt}
                
                CRITICAL INFORMATION ABOUT THE EMPLOYEE SCHEMA:
                The rules you create must be compatible with the actual employee data structure.
                All field names MUST match EXACTLY as shown in this employee example.
                Use the exact capitalization and notation (including periods in field names).

                When creating rules:
                1. Use field names EXACTLY as they appear above (e.g., 'Curr.Level', 'Gender', 'Employee Status')
                2. Match string values EXACTLY as they appear (e.g., 'Male' not 'male')
                3. For leave balance, use 'leave_balance' field
                4. For tenure calculations, use calculated fields like 'employee_tenure_years'
                
                Here is the extracted text from the leave policy document:

                ---DOCUMENT TEXT START---
                {extracted_text}
                ---DOCUMENT TEXT END---

                Please analyze the above policy text and provide your response following the format specified in the instructions above.
                Remember to create rules that will be used for validating employee leave requests against the policy.
                """
    
    def chat_with_model(self, model_id: str, prompt: str, rules: Union[List[str], Dict] = None) -> str:
        """Chat with specified AI model about rules"""
        if model_id not in self.api_keys or not self.api_keys[model_id]:
            raise ValueError(f"API key not configured for {model_id}")
        
        # Prepare context prompt with rules if provided
        full_prompt = prompt
        if rules:
            # Handle both rule-engine format (list) and old JSON format (dict) for backward compatibility
            if isinstance(rules, list):
                rules_text = "\n".join([f"- {rule}" for rule in rules])
                rule_format = "rule-engine expressions"
            else:
                rules_text = json.dumps(rules, indent=2)
                rule_format = "JSON rule set"
                
            full_prompt = f"""
You are an HR policy assistant. You have access to the following {rule_format} for leave policies:

{rules_text}

A user is asking the following question about leave policies:
"{prompt}"

Please provide a clear, accurate answer based ONLY on the information in the rules above. If the rules don't contain enough information to answer the question, please state that clearly.
"""
        
        if model_id == 'gemini':
            return self._chat_with_gemini(full_prompt)
        elif model_id == 'chatgpt':
            return self._chat_with_chatgpt(full_prompt)
        elif model_id == 'claude':
            return self._chat_with_claude(full_prompt)
        elif model_id == 'deepseek':
            return self._chat_with_deepseek(full_prompt)
        else:
            raise ValueError(f"Unsupported model: {model_id}")
    
    def edit_rules_with_model(self, model_id: str, prompt: str, current_rules: Union[List[str], Dict]) -> Dict:
        """Edit rules using specified AI model"""
        if model_id not in self.api_keys or not self.api_keys[model_id]:
            raise ValueError(f"API key not configured for {model_id}")
        
        # Handle both rule-engine format (list) and old JSON format (dict) for backward compatibility
        if isinstance(current_rules, list):
            rules_text = "\n".join([f"- {rule}" for rule in current_rules])
            rules_format = "rule-engine expressions"
        else:
            rules_text = json.dumps(current_rules, indent=2)
            rules_format = "JSON rules"
        
        edit_prompt = f"""
You are an AI assistant that helps edit leave policy rules. You receive {rules_format} and user requests to modify them.

Current Leave Policy Rules:
{rules_text}

User Request: "{prompt}"

Your task:
1. Determine if the user's request is related to leave policy editing (leave types, days, policies, advance notice, approvals, etc.)
2. If YES: Modify the rules according to the request and return the updated rules
3. If NO: Respond that the prompt isn't about leave policy

Response Format for rule-engine expressions:
- If the request IS about leave policy: Return a JSON object with "success": true, "response": "explanation of changes made", "updatedRules": [array of rule-engine expressions]
- If the request is NOT about leave policy: Return a JSON object with "success": true, "response": "Looks like your prompt isn't about your leave policy", "updatedRules": null

Important Rules for Editing:
- For rule-engine format: Return rules as an array of strings, each string being a valid rule-engine expression
- Only modify what the user specifically requests
- When adding new rules, ensure they follow proper rule-engine syntax (e.g., "leave_type == 'annual' and days_requested <= 18")
- When modifying conditions, ensure they are logical and reasonable
- Use proper operators: ==, !=, <, <=, >, >=, and, or, not
- Variable names should match the context: leave_type, days_requested, advance_notice_days, employee_gender, etc.

Please process the user's request now and return a valid JSON response:
"""
        
        if model_id == 'gemini':
            return self._edit_rules_with_gemini(edit_prompt)
        elif model_id == 'chatgpt':
            return self._edit_rules_with_chatgpt(edit_prompt)
        elif model_id == 'claude':
            return self._edit_rules_with_claude(edit_prompt)
        elif model_id == 'deepseek':
            return self._edit_rules_with_deepseek(edit_prompt)
        else:
            raise ValueError(f"Unsupported model: {model_id}")
    
    def _analyze_with_gemini(self, pdf_bytes: bytes, prompt: str = None) -> str:
        """Analyze with Gemini model (supports PDF)"""
        if not prompt:
            prompt = self._get_default_policy_analysis_prompt()
        
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
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
                "maxOutputTokens": 40096
            }
        }
        
        config = self.model_configs['gemini']
        response = requests.post(
            f"{config['url']}?key={self.api_keys['gemini']}", 
            headers={"Content-Type": "application/json"}, 
            json=data
        )
        
        if response.ok:
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise Exception(f"Gemini API error ({response.status_code}): {response.text}")
    
    def _analyze_with_chatgpt(self, prompt: str) -> str:
        """Analyze with ChatGPT model (text only)"""
        print("###################### Calling ChatGPT Model  ###################### ")
        if not prompt:
            prompt = "Please analyze the leave policy rules and provide recommendations."
        
        config = self.model_configs['chatgpt']
        headers = {
            "Authorization": f"Bearer {self.api_keys['chatgpt']}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": config['model'],
            "messages": [
                {"role": "system", "content": "You are an expert HR policy analyst. Analyze leave policies thoroughly and provide complete, untruncated responses with ALL extracted rules. Never truncate your output or use ellipsis (...) to indicate more content. Always complete your full analysis."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": config['max_tokens'],
            "temperature": 0.1
        }
        
        response = requests.post(config['url'], headers=headers, json=data)
        print("Chatgpt response ", response)
        if response.ok:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"ChatGPT API error ({response.status_code}): {response.text}")
    
    def _analyze_with_claude(self, prompt: str) -> str:
        """Analyze with Claude model (text only)"""
        if not prompt:
            prompt = "Please analyze the leave policy rules and provide recommendations."
        
        config = self.model_configs['claude']
        headers = {
            "x-api-key": self.api_keys['claude'],
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": config['model'],
            "max_tokens": config['max_tokens'],
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        response = requests.post(config['url'], headers=headers, json=data)
        
        if response.ok:
            result = response.json()
            return result['content'][0]['text']
        else:
            raise Exception(f"Claude API error ({response.status_code}): {response.text}")
    
    def _analyze_with_deepseek(self, prompt: str) -> str:
        """Analyze with DeepSeek model (text only)"""
        if not prompt:
            prompt = "Please analyze the leave policy rules and provide recommendations."
        
        config = self.model_configs['deepseek']
        headers = {
            "Authorization": f"Bearer {self.api_keys['deepseek']}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": config['model'],
            "messages": [
                {"role": "system", "content": "You are an HR policy analyst. Analyze leave policies and provide detailed recommendations."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": config['max_tokens'],
            "temperature": 0.1
        }
        
        response = requests.post(config['url'], headers=headers, json=data)
        
        if response.ok:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"DeepSeek API error ({response.status_code}): {response.text}")
    
    def _chat_with_gemini(self, prompt: str) -> str:
        print("""Chat with Gemini""")
        print('self.model_configs["gemini"]["max_tokens"]')
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 40480}
        }
        
        config = self.model_configs['gemini']
        response = requests.post(
            f"{config['url']}?key={self.api_keys['gemini']}", 
            headers={"Content-Type": "application/json"}, 
            json=data
        )
        if response.ok:
            result = response.json()
            print("result ",result)
            return result["candidates"][0]["content"]["parts"][0]["text"]
            # return result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise Exception(f"Gemini API error ({response.status_code}): {response.text}")
    
    def _chat_with_chatgpt(self, prompt: str) -> str:
        """Chat with ChatGPT"""
        config = self.model_configs['chatgpt']
        headers = {
            "Authorization": f"Bearer {self.api_keys['chatgpt']}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": config['model'],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config['max_tokens'],
            "temperature": 0.3
        }
        
        response = requests.post(config['url'], headers=headers, json=data)
        
        if response.ok:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"ChatGPT API error ({response.status_code}): {response.text}")
    
    def _chat_with_claude(self, prompt: str) -> str:
        """Chat with Claude"""
        config = self.model_configs['claude']
        headers = {
            "x-api-key": self.api_keys['claude'],
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": config['model'],
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        response = requests.post(config['url'], headers=headers, json=data)
        
        if response.ok:
            result = response.json()
            return result['content'][0]['text']
        else:
            raise Exception(f"Claude API error ({response.status_code}): {response.text}")
    
    def _chat_with_deepseek(self, prompt: str) -> str:
        """Chat with DeepSeek"""
        config = self.model_configs['deepseek']
        headers = {
            "Authorization": f"Bearer {self.api_keys['deepseek']}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": config['model'],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.3
        }
        
        response = requests.post(config['url'], headers=headers, json=data)
        
        if response.ok:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"DeepSeek API error ({response.status_code}): {response.text}")
    
    def _edit_rules_with_gemini(self, prompt: str) -> Dict:
        """Edit rules with Gemini"""
        response_text = self._chat_with_gemini(prompt)
        return self._parse_edit_response(response_text)
    
    def _edit_rules_with_chatgpt(self, prompt: str) -> Dict:
        """Edit rules with ChatGPT"""
        response_text = self._chat_with_chatgpt(prompt)
        return self._parse_edit_response(response_text)
    
    def _edit_rules_with_claude(self, prompt: str) -> Dict:
        """Edit rules with Claude"""
        response_text = self._chat_with_claude(prompt)
        return self._parse_edit_response(response_text)
    
    def _edit_rules_with_deepseek(self, prompt: str) -> Dict:
        """Edit rules with DeepSeek"""
        response_text = self._chat_with_deepseek(prompt)
        return self._parse_edit_response(response_text)
    
    def _parse_edit_response(self, response_text: str) -> Dict:
        """Parse AI response for rule editing"""
        try:
            # Try to parse as JSON directly
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # Fallback: return the raw response
            return {
                'success': True,
                'response': response_text,
                'updatedRules': None
            }
    
    
    def _get_default_policy_analysis_prompt(self) -> str:
        """
        Get default prompt for leave policy analysis.
        Ensures output rules are compatible with the actual context dict
        used during leave validation.
        """

        return f"""
        You are an expert HR policy analyzer with advanced reasoning skills. 
        Your job is to read the provided leave policy document and extract EVERY 
        rule, condition, eligibility requirement, calendar restriction, and 
        documentation stipulation. The rules will be used by a Python 
        rule-engine library to validate employee leave requests.

        =====================
        CRITICAL INSTRUCTIONS
        =====================
        1. READ the policy thoroughly — include appendices, holidays, blackout dates, tenure rules, and gender-specific leaves.
        2. Use ONLY the EXACT field names listed below in the VALIDATION CONTEXT FIELDS section.
        3. All rule expressions must be valid Python rule-engine expressions.
        4. Do not invent fields — match field names EXACTLY (case-sensitive).
        5. Boolean values must be lowercase `true` / `false`.
        6. String values must match exactly (e.g., 'Male', 'Female', 'Full-Time', 'Part-Time').
        7. Avoid arbitrary or nonsensical limits (e.g., `days_requested > 110960`).
        8. Focus on meaningful HR business rules: balance checks, probation limits, maternity/paternity eligibility, holiday adjacency, approval requirements, etc.
        9. Avoid redundancy — no duplicate or overlapping rules.
        10.In case you find rules in the policy that do not have a corresponding validation context field below, highlight and return those rules in your response as a comment, NOT as a rule.

        =====================
        VALIDATION CONTEXT FIELDS
        =====================
        These are the only fields available during validation:

        BASIC LEAVE FIELDS:
        - leave_type
        - days_requested
        - advance_notice_days
        - consecutive_days

        EMPLOYEE FIELDS:
        - employee_balance
        - total_annual_balance
        - employee_tenure_months
        - employee_tenure_years
        - employee_gender
        - employee_department
        - employee_level
        - employee_name
        - employee_first_name
        - employee_last_name
        - is_probation_period
        - team_size
        - employee_email
        - employee_phone
        - employee_dob
        - employee_age
        - employee_hire_date
        - employee_status
        - employee_job_title
        - employee_employment_type
        - employee_manager_id
        - employee_department_id
        - employee_department_name

        DATE AND CALENDAR FIELDS:
        - current_date
        - request_date
        - leave_start_date
        - leave_end_date
        - season
        - is_weekend_adjacent
        - is_holiday_adjacent
        - is_public_holiday
        - holiday_name
        - is_blackout_period
        - is_peak_business_period

        LEAVE REQUEST ATTRIBUTES:
        - has_medical_certificate
        - is_emergency
        - leave_reason
        - is_recurring_leave
        - has_medical_history

        APPROVAL FIELDS:
        - manager_approval_required
        - hr_approval_required

        USAGE TRACKING:
        - previous_leave_days_this_year
        - critical_project_deadline
        - previous_leave_count
        - previous_approved_leaves
        - previous_rejected_leaves
        - previous_pending_leaves

        TRAVEL AND VISA FIELDS:
        - has_recent_travel
        - recent_travel_destination
        - days_since_travel
        - employee_visa_status
        - has_pending_visa_application
        - is_travel_restricted_period

        LEAVE BALANCE FIELDS:
        - leave_entitled_days
        - leave_used_days
        - leave_remaining_days
        - total_annual_entitled_days
        - total_annual_used_days
        - total_annual_remaining_days

        METADATA:
        - employee_created_at
        - employee_updated_at

        ====================
        OUTPUT REQUIREMENTS
        ====================
        - Output as JSON with key "RULE_ENGINE_RULES"
        - Each rule must be written as: "rule: <expression>"
        - Use ONLY the field names listed above
        - Always express eligibility in POSITIVE terms:
        Example: instead of "employee_status != 'Terminated'",
        write "employee_status == 'Active'".

        Example:
        {{
        "RULE_ENGINE_RULES": [
            "rule: leave_type == 'annual' and days_requested <= 21 and employee_balance >= days_requested",
            "rule: leave_type == 'maternity' and employee_gender == 'Female' and employee_tenure_months >= 12",
            "rule: leave_type == 'sick' and (days_requested <= 3 or has_medical_certificate == true)",
            "rule: employee_employment_type in ['Full-Time', 'Intern']",
            "rule: leave_type == 'annual' and advance_notice_days >= 7",
            "rule: leave_type == 'annual' and is_probation_period == false"
        ]
        }}

        =====================
        FINAL INSTRUCTIONS
        =====================
        - Generate ONLY validating/eligibility rules that describe when a leave request SHOULD be approved.
        - Do NOT generate rules that only deny/negate.
        - Every rule must be a valid Python expression supported by rule-engine.
        - Rules must be self-contained, non-redundant, and executable.
        - Generate highly relevant and exhaustive conditional rules by combining multiple columns and attributes in diverse ways. 
        - Ensure you systematically explore every possible logical combination of fields to cover all edge cases, eligibility criteria, and policy variations — producing as many unique, non-redundant rules as possible, strictly adhering to the employee schema and context keys.
        -Extract even the smallest, most granular details and conditions from the policy to generate highly specific rules, ensuring no minor case or edge scenario is missed.
        - DO NOT generate redundant rules. Each rule must address a unique aspect of the leave policy.
        """ 
    def _get_default_policy_analysis_prompt_oldv1(self) -> str:
        """Get default prompt for policy analysis"""
        # from prompt import prompt_correct,correct_prompt2
        # return correct_prompt2
        # return f"""
        #         You are an expert HR policy analyzer with advanced reasoning skills. 
        #         Your job is to read the provided leave policy document and extract EVERY 
        #         rule, condition, eligibility requirement, calendar restriction, and 
        #         documentation stipulation. The rules will be used by a Python 
        #         rule-engine library to validate employee leave requests.

        #         =====================
        #         CRITICAL INSTRUCTIONS
        #         =====================
        #         1. READ the policy thoroughly — include appendices, holidays, blackout dates, tenure rules, and gender-specific leaves.
        #         2. Use ONLY the fields listed in the employee schema below.
        #         3. All rule expressions must be valid Python rule-engine expressions.
        #         4. Do not invent fields — match field names EXACTLY (case-sensitive, snake_case).
        #         5. Boolean values must be lowercase `true` / `false`.
        #         6. String values must match schema values exactly (e.g., 'Male', 'Female').
        #         7. Avoid arbitrary or nonsensical limits (e.g., `days_requested > 110960`).
        #         8. Focus on meaningful HR business rules: balance checks, probation limits, maternity/paternity eligibility, holiday adjacency, approval requirements, etc.
        #         9. Avoid redundancy — no duplicate or overlapping rules.

        #         ===================
        #         EMPLOYEE SCHEMA FIELDS
        #         ===================
        #         Use EXACTLY these fields in your rules:

        #         {{
        #     # Basic leave details
        #     'leave_type': leave_type,
        #     'days_requested': days_requested,
        #     'advance_notice_days': advance_notice_days,
        #     'consecutive_days': days_requested,
            
        #     # Employee details
        #     'employee_balance': employee_balance,
        #     'total_annual_balance': total_annual_balance,
        #     'employee_tenure_months': tenure_months,
        #     'employee_tenure_years': tenure_years,
        #     'employee_gender': employee_data.get('gender', 'not_specified'),
        #     'employee_department': employee_data.get('department', 'general'),
        #     'employee_level': employee_data.get('level', 'staff'),
            
        #     # Dynamic employee name handling - support various field combinations
        #     'employee_name': get_employee_name(employee_data, employee_uid),
        #     'employee_first_name': get_employee_first_name(employee_data),
        #     'employee_last_name': get_employee_last_name(employee_data),
            
        #     'is_probation_period': tenure_months < 6,  # Assume 6 month probation
        #     'team_size': employee_data.get('team_size', 5),
            
        #     # Date and calendar info
        #     'current_date': current_date.isoformat(),
        #     'request_date': request_date.isoformat(),
        #     'leave_start_date': start_date.isoformat(),
        #     'leave_end_date': end_date.isoformat(),
        #     'season': season,
            
        #     # Leave request attributes
        #     'has_medical_certificate': leave_data.get('has_medical_certificate', False),
        #     'is_emergency': leave_data.get('is_emergency', False),
        #     'leave_reason': leave_data.get('reason', ''),
        #     'is_recurring_leave': leave_data.get('is_recurring', False),
        #     'has_medical_history': employee_data.get('has_medical_history', False),
            
        #     # Calendar and business context
        #     'is_weekend_adjacent': is_weekend_adjacent,
        #     'is_holiday_adjacent': False,  # TODO: Implement holiday checking
        #     'is_public_holiday': False,    # TODO: Implement holiday checking
        #     'holiday_name': '',            # TODO: Implement holiday checking
        #     'is_blackout_period': False,   # TODO: Implement blackout period checking
        #     'is_peak_business_period': False,  # TODO: Implement based on business calendar
            
        #     # Approval requirements
        #     'manager_approval_required': days_requested > 0,  # Default: always required
        #     'hr_approval_required': days_requested > 5 or leave_type in ['maternity', 'paternity', 'sabbatical'],
            
        #     # Usage tracking
        #     'previous_leave_days_this_year': previous_leave_days,
        #     'critical_project_deadline': False,  # TODO: Implement based on project calendar
            
        #     # Travel-related variables
        #     'has_recent_travel': employee_data.get('has_recent_travel', False),
        #     'recent_travel_destination': employee_data.get('recent_travel_destination', ''),
        #     'days_since_travel': employee_data.get('days_since_travel', 999),  # Large number if no recent travel
        #     'employee_visa_status': employee_data.get('visa_status', 'citizen'),
        #     'has_pending_visa_application': employee_data.get('has_pending_visa_application', False),
        #     'is_travel_restricted_period': False,  # TODO: Implement based on policy

        #     # --- New fields from schema ---
        #     "employee_email": employee_data.get("email", ""),
        #     "employee_phone": employee_data.get("phone", ""),
        #     "employee_dob": employee_data.get("date_of_birth"),
        #     "employee_age": calculate_age(employee_data.get("date_of_birth")),
        #     "employee_hire_date": employee_data.get("hire_date", None),
        #     "employee_status": employee_data.get("status", "Inactive"),
        #     "employee_job_title": employee_data.get("job_title", ""),
        #     "employee_employment_type": employee_data.get("employment_type", ""),
        #     "employee_manager_id": employee_data.get("manager_id", ""),
        #     "employee_department_id": employee_data.get("department", {{}}).get("id", ""),
        #     "employee_department_name": employee_data.get("department", {{}}).get("name", "").lower(),

        #     # Leave balances (from list structure)
        #     "leave_entitled_days": get_leave_entitlement(leave_balances, leave_type),
        #     "leave_used_days": get_leave_used(leave_balances, leave_type),
        #     "leave_remaining_days": get_leave_remaining(leave_balances, leave_type),
        #     "total_annual_entitled_days": get_leave_entitlement(leave_balances, "Annual Leave"),
        #     "total_annual_used_days": get_leave_used(leave_balances, "Annual Leave"),
        #     "total_annual_remaining_days": get_leave_remaining(leave_balances, "Annual Leave"),

        #     # Leave history
        #     "previous_leave_count": len(leaves_history),
        #     "previous_approved_leaves": sum(1 for lv in leaves_history if lv.get("status", "").lower() == "approved"),
        #     "previous_rejected_leaves": sum(1 for lv in leaves_history if lv.get("status", "").lower() == "rejected"),
        #     "previous_pending_leaves": sum(1 for lv in leaves_history if lv.get("status", "").lower() == "pending"),

        #     # Attendance
        #     # "average_daily_hours": calculate_average_hours(attendance_records),
        #     # "absent_days_this_month": count_absent_days(attendance_records, current_date),
        #     # "late_checkins_this_month": count_late_checkins(attendance_records),

        #     # Metadata
        #     "employee_created_at": employee_data.get("created_at", ""),
        #     "employee_updated_at": employee_data.get("updated_at", ""),
        # }}

        #         ====================
        #         OUTPUT REQUIREMENTS
        #         ====================
        #         - Output as JSON with key "RULE_ENGINE_RULES"
        #         - Each rule must be written as: 
        #         "rule: <expression>"

        #         Example:
        #         {{
        #         "RULE_ENGINE_RULES": [
        #             "rule: leave_type == 'annual' and days_requested <= employee_balance",
        #             "rule: leave_type == 'maternity' and employee_gender == 'Female'",
        #             "rule: leave_type == 'sick' and (days_requested <= 3 or has_medical_certificate == true)"
        #         ]
        #         }}

        #         =====================
        #         WHAT TO INCLUDE
        #         =====================
        #         - Gender-specific eligibility (maternity → female, paternity → male)
        #         - Tenure-based entitlements
        #         - Probation restrictions
        #         - Advance notice requirements
        #         - Holiday calendar restrictions
        #         - Weekend/holiday sandwich rules
        #         - Blackout period restrictions
        #         - Approval hierarchies (manager/HR escalation)
        #         - Balance validations
        #         - Department/role-specific restrictions if present
        #         - Emergency vs. planned leave rules

        #         =====================
        #         FINAL INSTRUCTIONS
        #         =====================
        #         - Be comprehensive (50–150+ rules if policy is detailed).
        #         - Do not stop early or use ellipses (...).
        #         - Ensure all rules can be parsed and executed by the Python rule-engine library.
        #         """
        # return prompt4
        #### Original Prompt ####
        return """
            You are an expert HR policy analyzer with advanced reasoning capabilities. Your task is to meticulously read the provided leave policy document and extract EVERY rule, stipulation, condition, calendar entry, and nuance related to leave policies. These rules will be used to validate employee leave requests against policy data.

            CRITICAL INSTRUCTIONS:
            
            1. READ EVERY SECTION thoroughly - including appendices, holiday calendars, fine print, and policy addendums
            2. Use ADVANCED REASONING to infer implicit rules and gender-specific requirements
            3. Extract ALL holiday dates and calendar information
            4. Identify gender-specific leave types and their eligibility requirements
            5. Capture approval hierarchies, documentation requirements, and blackout periods
            6. Notice period variations based on leave duration or type
            7. Sandwiching rules and weekend/holiday adjacency policies
            8. Tenure-based eligibility and progressive benefits
            9. Emergency vs. planned leave distinctions
            10. Regional, departmental, or role-specific variations (ONLY if explicitly mentioned in the policy document)
            11. Extract ANY custom conditions or special restrictions mentioned in the policy (e.g., travel-related restrictions, department-specific rules, etc.)
            12. PAY CLOSE ATTENTION to the employee record schema and create rules that use ONLY the fields available in the employee data
            13. Use the full name for the leave like 'annual' , 'personal', 'sick' instead of the PL, AL, SL etc.


            IMPORTANT RULE CREATION GUIDELINES:
            - Only create rules for conditions, requirements, and restrictions that are EXPLICITLY stated in the policy document
            - Use ONLY the fields available in the provided employee schema example
            - Do not make assumptions about designation levels, seniority benefits, or role-based restrictions unless clearly mentioned
            - Do NOT create arbitrary numeric limits (avoid rules like "days_requested > 110960")
            - Focus on MEANINGFUL business rules that have practical application
            - Loss of pay leave is typically a fallback category - do not create specific day limits for it unless explicitly stated
            - Pay special attention to custom conditions, travel restrictions, department-specific rules, or unique policy requirements
            - Each rule should represent a real policy requirement that would be used in leave approval decisions
            - Create rules that are compatible with the Python rule-engine library syntax
            - Reference fields EXACTLY as they appear in the employee schema (e.g., 'Employee Status', 'Curr.Department', etc.)

            For each rule you find, translate it into a Python rule-engine rule expression. Each rule should be written as a valid rule-engine expression string, suitable for use with the Python rule-engine library.

            AVAILABLE VARIABLES for your rules (from employee record schema):
            #### 🏝 Leave Details
            - leave_type : The category of leave being applied for (e.g., annual, sick, maternity, paternity, study, sabbatical, unpaid, emergency, bereavement).
            - days_requested : Total number of leave days requested in the current application.
            - advance_notice_days : Number of days between the leave request date and the leave start date (used for policy checks on advance notice).
            - consecutive_days : Total number of consecutive days covered by the leave period.
            - leave_entitled_days : The number of days an employee is entitled to take for this specific leave type according to company policy.
            - leave_used_days : The number of days already utilized for this specific leave type.
            - leave_remaining_days : The number of days still available to the employee for this specific leave type.
            - total_annual_entitled_days : Total number of annual leave days allotted to the employee for the year.
            - total_annual_used_days : Total number of annual leave days already used by the employee in the year.
            - total_annual_remaining_days : Remaining annual leave days available for the employee in the year.

            #### 👤 Employee Details
            - employee_balance : The employee's current available leave balance (across all types).
            - total_annual_balance : Total leave balance available for the entire year (including unused days carried forward, if applicable).
            - employee_tenure_months : Employee's tenure in months, calculated from the date of joining (DOJ).
            - employee_tenure_years : Employee's tenure in years, calculated from the date of joining.
            - is_probation_period : Boolean value that indicates whether the employee is still within the probation period (default assumption: <6 months).
            - employee_gender : Employee's gender (male, female, other, or not specified).
            - employee_department : Department or business unit where the employee currently works.
            - employee_department_id : Unique identifier of the department (useful for filtering/reporting).
            - employee_department_name : Department name in lowercase (for normalization).
            - employee_level : Employee's current level or grade (e.g., Associate, Manager, Executive).
            - employee_job_title : Official job title/designation of the employee.
            - employee_employment_type : Type of employment (e.g., full-time, part-time, contractual, intern).
            - employee_status : Current employment status (Active, Inactive, Terminated, On Leave).
            - employee_manager_id : Unique identifier of the employee's reporting manager.
            - employee_name : Employee's full name (derived dynamically from first/last name).
            - employee_first_name : Employee's first name.
            - employee_last_name : Employee's last name.
            - team_size : Size of the employee's direct team (if applicable).

            #### 📅 Dates and Calendar Info
            - current_date : The current system date when the leave request is being processed.
            - request_date : Date on which the leave request was created/submitted by the employee.
            - leave_start_date : Start date of the leave period (inclusive).
            - leave_end_date : End date of the leave period (inclusive).
            - season : The season during which leave is being requested (summer, winter, etc., useful for workforce planning).
            - is_weekend_adjacent : Whether the leave is adjacent to a weekend (used to flag long breaks).
            - is_holiday_adjacent : Whether the leave period is adjacent to a public holiday.
            - is_public_holiday : Whether the requested leave overlaps with a public holiday.
            - holiday_name : Name of the public holiday if the leave overlaps with one.
            - is_blackout_period : Whether the requested leave falls during a business-defined blackout period (e.g., peak project deadlines).
            - is_peak_business_period : Whether the leave request falls in a known high-demand business period.

            #### 📜 Leave Request Attributes
            - has_medical_certificate : Whether a medical certificate has been submitted for medical/sick leave validation.
            - is_emergency : Whether this leave was requested as an emergency leave (short notice).
            - leave_reason : The reason stated by the employee for the leave request.
            - is_recurring_leave : Whether the leave is a recurring request (e.g., weekly medical appointments).
            - has_medical_history : Whether the employee has a medical history recorded (may affect approval policies).

            #### ✅ Approval & Policy Checks
            - manager_approval_required : Whether approval from the reporting manager is mandatory for this leave request.
            - hr_approval_required : Whether HR approval is mandatory (typically for maternity, paternity, sabbatical, or long leaves >5 days).
            - previous_leave_days_this_year : Total number of leave days taken by the employee in the current calendar year.
            - critical_project_deadline : Boolean flag indicating whether the leave overlaps with a critical project deadline.

            #### ✈ Travel-Related Information
            - has_recent_travel : Whether the employee has traveled recently (domestic or international).
            - recent_travel_destination : Last recorded travel destination.
            - days_since_travel : Number of days since the last recorded travel (used for health/safety compliance).
            - employee_visa_status : Employee's visa status (citizen, work permit, dependent, etc.).
            - has_pending_visa_application : Whether the employee has any ongoing visa application.
            - is_travel_restricted_period : Whether travel-related leave is restricted during this time (based on policy or government advisories).

            #### 🕒 Employee Metadata
            - employee_email : Employee's official email address.
            - employee_phone : Employee's phone number.
            - employee_dob : Employee's date of birth.
            - employee_age : Employee's age, calculated dynamically from date of birth.
            - employee_hire_date : Employee's hire date (date of joining).
            - employee_created_at : Timestamp when the employee record was created in the system.
            - employee_updated_at : Timestamp when the employee record was last updated in the system.

            #### 📊 Leave History
            - previous_leave_count : Total number of past leave requests submitted by the employee.
            - previous_approved_leaves : Count of previously approved leave requests.
            - previous_rejected_leaves : Count of previously rejected leave requests.
            - previous_pending_leaves : Count of leave requests that are still pending approval.

            Important:
            - Always output rules strictly as dictionary keys.  
            - Do not create redundant or overlapping rules.  
            - Each rule key must be unique and meaningful.  
            - Keep rule values clear, concise, and relevant to the employee context. 
            *** Start the dict output format *** 
            
            {{
            # Basic leave details
            'leave_type' ,
            'days_requested',
            'advance_notice_days',
            'consecutive_days',
            
            # Employee details
            'employee_balance',
            'total_annual_balance',
            'employee_tenure_months',
            'employee_tenure_years',
            'employee_gender',
            'employee_department',
            'employee_level',
            
            # Dynamic employee name handling - support various field combinations
            'employee_name',
            'employee_first_name',
            'employee_last_name',
            
            'is_probation_period': tenure_months < 3,  # Assume 3 month probation
            'team_size',
            
            # Date and calendar info
            'current_date',
            'request_date',
            'leave_start_date',
            'leave_end_date',
            'season': season,
            
            # Leave request attributes
            'has_medical_certificate',
            'is_emergency,
            'leave_reason',
            'is_recurring_leave',
            'has_medical_history',
            
            # Calendar and business context
            'is_weekend_adjacent',
            'is_holiday_adjacent',  # TODO: Implement holiday checking
            'is_public_holiday',    # TODO: Implement holiday checking
            'holiday_name',            # TODO: Implement holiday checking
            'is_blackout_period',   # TODO: Implement blackout period checking
            'is_peak_business_period',  # TODO: Implement based on business calendar
            
            # Approval requirements
            'manager_approval_required'> days_requested > 0,  # Default: always required
            'hr_approval_required'> days_requested > 5 or leave_type in ['maternity', 'paternity', 'sabbatical'],
            
            # Usage tracking
            'previous_leave_days_this_year',
            'critical_project_deadline',  # TODO: Implement based on project calendar
            
            # Travel-related variables
            'has_recent_travel',
            'recent_travel_destination',
            'days_since_travel' # Large number if no recent travel
            'employee_visa_status',
            'has_pending_visa_application',
            'is_travel_restricted_period',  # TODO: Implement based on policy

            # --- New fields from schema ---
            "employee_email",
            "employee_phone",
            "employee_dob",
            "employee_age",
            "employee_hire_date",
            "employee_status",
            "employee_job_title",
            "employee_employment_type",
            "employee_manager_id",
            "employee_department_id",
            "employee_department_name",

            # Leave balances (from list structure)
            "leave_entitled_days",
            "leave_used_days",
            "leave_remaining_days",
            "total_annual_entitled_days",
            "total_annual_used_days",
            "total_annual_remaining_days",

            # Leave history
            "previous_leave_count"> len(leaves_history),
            "previous_approved_leaves"> sum(1 for lv in leaves_history if lv.get("status", "").lower() == "approved"),
            "previous_rejected_leaves"> sum(1 for lv in leaves_history if lv.get("status", "").lower() == "rejected"),
            "previous_pending_leaves"> sum(1 for lv in leaves_history if lv.get("status", "").lower() == "pending"),

            # Attendance
            # "average_daily_hours"> calculate_average_hours(attendance_records),
            # "absent_days_this_month"> count_absent_days(attendance_records, current_date),
            # "late_checkins_this_month"> count_late_checkins(attendance_records),

            # Metadata
            "employee_created_at",
            "employee_updated_at",
            }}
            *** END the dict output format ***
            
            ADVANCED REASONING EXAMPLES (adapted to employee schema):
            1. Gender-specific eligibility:
            rule: leave_type == 'maternity' and Gender == 'Female'
            rule: leave_type == 'paternity' and Gender == 'Male'

            2. Holiday calendar integration:
            rule: leave_type == 'annual' and not (leave_start_date in ['2024-12-25', '2024-01-01', '2024-07-04'])
            rule: not (is_public_holiday == True and leave_type == 'annual' and days_requested == 1)

            3. Tenure-based progression:
            rule: leave_type == 'annual' and ((employee_tenure_years < 2 and days_requested <= 15) or (employee_tenure_years >= 2 and employee_tenure_years < 5 and days_requested <= 20) or (employee_tenure_years >= 5 and days_requested <= 25))

            4. Sandwiching prevention:
            rule: not (is_weekend_adjacent == True and is_holiday_adjacent == True and days_requested <= 2 and leave_type == 'annual')

            5. Medical documentation requirements:
            rule: leave_type == 'sick' and ((days_requested <= 3) or (days_requested > 3 and has_medical_certificate == True))

            6. Emergency vs planned distinctions:
            rule: leave_type == 'emergency' and (advance_notice_days >= 0 and days_requested <= 5)
            rule: leave_type == 'annual' and (is_emergency == False and advance_notice_days >= 14)

            7. Approval hierarchy:
            rule: leave_type == 'annual' and days_requested <= 5 and manager_approval_required == True
            rule: leave_type == 'annual' and days_requested > 5 and manager_approval_required == True and hr_approval_required == True

            8. Employment status considerations:
            rule: 'Employee Status' == 'Confirmed' and leave_type == 'annual' and days_requested <= leave_balance
            rule: 'Employee Status' == 'Probation' and leave_type == 'annual' and days_requested <= 3

            9. Department-specific policies:
            rule: 'Curr.Department' == 'Ecommerce' and leave_type == 'annual' and advance_notice_days >= 7
            rule: 'Curr.Department' == 'Finance' and leave_type == 'annual' and not (leave_start_date[8:10] in ['01', '02', '03', '04', '05'])  # No leave in first 5 days of month

            10. Level-based entitlements:
            rule: 'Curr.Level' == 'Associate' and leave_type == 'annual' and days_requested <= 14
            rule: 'Curr.Level' == 'Manager' and leave_type == 'annual' and days_requested <= 21

            8. Blackout periods:
            rule: leave_type == 'annual' and not (is_blackout_period == True)

            9. Balance checking:
            rule: leave_type == 'annual' and days_requested <= leave_balance

            10. Probation restrictions:
            rule: not (is_probation_period == True and leave_type == 'annual' and days_requested > 3)

            11. Department-specific rules:
            rule: 'Curr.Department' == 'Finance' and not (leave_start_date[8:10] in ['01', '02', '03', '04', '05'])  # No leave in first 5 days of month

            12. Custom policy conditions:
            rule: leave_type == 'sick' and 'Marital Status' == 'Married' and days_requested <= 5
            rule: leave_type == 'bereavement' and 'Marital Status' == 'Married' and days_requested <= 7

            SPECIFIC EXTRACTION REQUIREMENTS:

            A. EMPLOYEE ATTRIBUTES:
            - Use field names EXACTLY as shown in the employee schema
            - For fields with periods like 'Curr.Department', include the period in the field name
            - Preserve case sensitivity of field names (e.g., 'Gender' not 'gender')
            - For date-based comparisons, use the provided calculated fields like 'employee_tenure_years' upto 100 only

            B. HOLIDAY CALENDAR:
            - Extract ALL public holidays with specific dates
            - Create rules that prevent/allow leave on specific dates
            - Include regional holidays, religious observances
            - Create blackout period rules around major holidays

            C. GENDER-SPECIFIC LEAVES:
            - Maternity leave: females only, duration, notice requirements
            - Paternity leave: males only, duration, timing restrictions
            - Adoption leave: gender considerations
            - Parental leave: gender-neutral options
            - Use 'Gender' field name with exact values like 'Male', 'Female'

            D. DOCUMENTATION REQUIREMENTS:
            - Medical certificates: when required, acceptable types
            - Advance documentation for planned surgeries
            - Emergency contact requirements
            - Approval workflows and escalation paths

            E. TENURE AND ELIGIBILITY:
            - Probation period restrictions (use 'Employee Status' == 'Probation')
            - Progressive benefits based on years of service
            - Waiting periods for different leave types
            - Accrual rates and caps

            F. BUSINESS IMPACT CONSIDERATIONS:
            - Department-specific rules (use 'Curr.Department')
            - Team coverage requirements
            - Critical project timelines
            - Client-specific rules (use 'Curr.Clientname')

            G. COMPLEX SCENARIOS:
            - Consecutive leave limitations
            - Partial day leaves
            - Half-day policies
            - Leave extensions and modifications
            - Cancellation policies

            H. LEVEL AND DESIGNATION BASED RULES:
            - Rules based on employee level (use 'Curr.Level')
            - Rules based on designation (use 'Curr.Designation')
            - Special allowances for specific roles or positions

            I. LEAVE BALANCE VALIDATION:
            - Rules to check leave balance against requested days
            - Rules to prevent negative leave balance
            - Use 'leave_balance' field for comparisons

            RULE QUALITY GUIDELINES:
            - Do NOT create rules with arbitrary large numbers (e.g., days_requested > 110960)
            - Do NOT create multiple similar rules with incrementing numbers
            - Each rule should represent a REAL policy decision point
            - Focus on meaningful business logic, not mathematical artifacts
            - Loss of pay leave typically doesn't have specific day limits unless explicitly stated
            - Pay special attention to unique conditions mentioned in the policy document
            - Ensure field names EXACTLY match the employee schema example
            - Use the correct capitalization for field names
            - For string comparisons, use EXACT values as they appear in the data (e.g., 'Male' not 'male')
            - Ensure all rules work with the Python rule-engine library
            - String comparisons are case-sensitive, so match case correctly

            After analyzing the document with this advanced reasoning, provide:

            1. A brief executive summary of the policy
            2. Key insights about gender-specific rules
            3. Holiday calendar findings
            4. Complex rule interdependencies identified
            5. A note about how the rules map to the employee schema fields

            RULE_ENGINE_RULES:
            [List each rule on a separate line starting with "rule: "]

            CRITICAL OUTPUT REQUIREMENT: 
            - You MUST provide ALL rules extracted from the policy document
            - Rules MUST use ONLY the field names available in the employee schema
            - Do NOT use fields that don't exist in the employee schema
            - String values should match the exact format in the employee schema (capitalization matters)
            - Do NOT truncate your response or stop early
            - A comprehensive policy analysis should yield 50-150+ rules
            - If you reach any response limit, continue with additional rules
            - Complete ALL rule extractions - every single policy requirement must become a rule
            - Do not use "..." or ellipsis to indicate more rules - write them all out
            - Ensure your response includes EVERY rule found in the document
            - For period/dot notation fields like 'Curr.Department', always include the period in the field name

            IMPORTANT: Be extremely thorough. A typical comprehensive policy should generate 50-150+ rules covering all scenarios, edge cases, eligibility requirements, calendar restrictions, and business rules. Do not summarize or simplify - capture every nuance. Make sure all rules work with the exact field names in the employee schema."""

    def analyze_rule_completeness(self, model: str, rules: Union[List[str], Dict]) -> dict:
        """Analyze rule engine for completeness using the specified AI model"""
        try:
            if model not in self.api_keys or not self.api_keys[model]:
                raise ValueError(f"API key for {model} not configured")
            
            # Handle both rule-engine format (list) and old JSON format (dict) for backward compatibility
            if isinstance(rules, list):
                rules_text = "\n".join([f"- {rule}" for rule in rules])
                rules_format = "rule-engine expressions"
            else:
                rules_text = json.dumps(rules, indent=2)
                rules_format = "JSON rule set"
            
            completeness_prompt = f"""
Please analyze the following leave policy {rules_format} for completeness and identify any missing or unclear policies:

{rules_text}

Analyze these rules and identify specific gaps or areas that need clarification. Focus on:

1. **Leave Types Coverage**: Are all common leave types defined (annual, sick, maternity, paternity, personal, emergency, bereavement)?

2. **Notice Period Requirements**: Are advance notice requirements clearly specified for each leave type?

3. **Approval Processes**: Are approval workflows and authorization levels clearly defined?

4. **Documentation Requirements**: Are medical certificates or other documentation requirements specified?

5. **Carry-over Policies**: Are year-end leave balance policies clearly defined?

6. **Blackout Periods**: Are any restricted periods for taking leave specified?

7. **Public Holidays**: Is the list of public holidays complete and current?

8. **Sandwiching Rules**: Are policies around taking leave adjacent to holidays/weekends defined?

9. **Maximum Limits**: Are maximum consecutive days and annual limits properly specified?

10. **Special Circumstances**: Are emergency leave, compassionate leave, and other special cases covered?

Please provide your response as a JSON object with this structure:
{{
  "findings": [
    "Specific issue or gap identified",
    "Another missing policy area",
    "Unclear requirement that needs definition"
  ],
  "completeness_score": 85,
  "critical_gaps": [
    "Most important missing policies"
  ],
  "recommendations": [
    "Specific recommendations to improve the policy"
  ]
}}

Focus on actionable, specific findings rather than general observations.
"""

            # Use the appropriate model to analyze
            if model == 'gemini':
                response = self._chat_with_gemini(completeness_prompt)
            elif model == 'chatgpt':
                response = self._chat_with_chatgpt(completeness_prompt)
            elif model == 'claude':
                response = self._chat_with_claude(completeness_prompt)
            elif model == 'deepseek':
                response = self._chat_with_deepseek(completeness_prompt)
            else:
                raise ValueError(f"Unsupported model: {model}")

            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                
                if json_start != -1 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    result = json.loads(json_str)
                    
                    return {
                        'success': True,
                        'findings': result.get('findings', []),
                        'completeness_score': result.get('completeness_score', 0),
                        'critical_gaps': result.get('critical_gaps', []),
                        'recommendations': result.get('recommendations', []),
                        'raw_response': response
                    }
                else:
                    # Fallback: parse the response manually
                    findings = []
                    lines = response.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#') and len(line) > 10:
                            findings.append(line)
                    
                    return {
                        'success': True,
                        'findings': findings[:10],  # Limit to 10 findings
                        'completeness_score': 70,
                        'critical_gaps': [],
                        'recommendations': [],
                        'raw_response': response
                    }
                    
            except json.JSONDecodeError:
                # Fallback: extract findings from text
                findings = []
                lines = response.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and ('not defined' in line.lower() or 'missing' in line.lower() or 'unclear' in line.lower()):
                        findings.append(line)
                
                return {
                    'success': True,
                    'findings': findings[:8] if findings else ["Unable to parse detailed findings from AI response"],
                    'completeness_score': 60,
                    'critical_gaps': [],
                    'recommendations': [],
                    'raw_response': response
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'findings': [],
                'completeness_score': 0
            }

# Global instance
ai_manager = AIModelManager()
