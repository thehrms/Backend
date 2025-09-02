context = {
            # Basic leave details
            'leave_type': leave_type,
            'days_requested': days_requested,
            'advance_notice_days': advance_notice_days,
            'consecutive_days': days_requested,
            
            # Employee details
            'employee_balance': employee_balance,
            'total_annual_balance': total_annual_balance,
            'employee_tenure_months': tenure_months,
            'employee_tenure_years': tenure_years,
            'employee_gender': employee_data.get('gender', 'not_specified'),
            'employee_department': employee_data.get('department', 'general'),
            'employee_level': employee_data.get('level', 'staff'),
            
            # Dynamic employee name handling - support various field combinations
            'employee_name': get_employee_name(employee_data, employee_uid),
            'employee_first_name': get_employee_first_name(employee_data),
            'employee_last_name': get_employee_last_name(employee_data),
            
            'is_probation_period': tenure_months < 6,  # Assume 6 month probation
            'team_size': employee_data.get('team_size', 5),
            
            # Date and calendar info
            'current_date': current_date.isoformat(),
            'request_date': request_date.isoformat(),
            'leave_start_date': start_date.isoformat(),
            'leave_end_date': end_date.isoformat(),
            'season': season,
            
            # Leave request attributes
            'has_medical_certificate': leave_data.get('has_medical_certificate', False),
            'is_emergency': leave_data.get('is_emergency', False),
            'leave_reason': leave_data.get('reason', ''),
            'is_recurring_leave': leave_data.get('is_recurring', False),
            'has_medical_history': employee_data.get('has_medical_history', False),
            
            # Calendar and business context
            'is_weekend_adjacent': is_weekend_adjacent,
            'is_holiday_adjacent': False,  # TODO: Implement holiday checking
            'is_public_holiday': False,    # TODO: Implement holiday checking
            'holiday_name': '',            # TODO: Implement holiday checking
            'is_blackout_period': False,   # TODO: Implement blackout period checking
            'is_peak_business_period': False,  # TODO: Implement based on business calendar
            
            # Approval requirements
            'manager_approval_required': days_requested > 0,  # Default: always required
            'hr_approval_required': days_requested > 5 or leave_type in ['maternity', 'paternity', 'sabbatical'],
            
            # Usage tracking
            'previous_leave_days_this_year': previous_leave_days,
            'critical_project_deadline': False,  # TODO: Implement based on project calendar
            
            # Travel-related variables
            'has_recent_travel': employee_data.get('has_recent_travel', False),
            'recent_travel_destination': employee_data.get('recent_travel_destination', ''),
            'days_since_travel': employee_data.get('days_since_travel', 999),  # Large number if no recent travel
            'employee_visa_status': employee_data.get('visa_status', 'citizen'),
            'has_pending_visa_application': employee_data.get('has_pending_visa_application', False),
            'is_travel_restricted_period': False,  # TODO: Implement based on policy

            # --- New fields from schema ---
            "employee_email": employee_data.get("email", ""),
            "employee_phone": employee_data.get("phone", ""),
            "employee_dob": employee_data.get("date_of_birth"),
            "employee_age": calculate_age(employee_data.get("date_of_birth")),
            "employee_hire_date": employee_data.get("hire_date", None),
            "employee_status": employee_data.get("status", "Inactive"),
            "employee_job_title": employee_data.get("job_title", ""),
            "employee_employment_type": employee_data.get("employment_type", ""),
            "employee_manager_id": employee_data.get("manager_id", ""),
            "employee_department_id": employee_data.get("department", {}).get("id", ""),
            "employee_department_name": employee_data.get("department", {}).get("name", "").lower(),

            # Leave balances (from list structure)
            "leave_entitled_days": get_leave_entitlement(leave_balances, leave_type),
            "leave_used_days": get_leave_used(leave_balances, leave_type),
            "leave_remaining_days": get_leave_remaining(leave_balances, leave_type),
            "total_annual_entitled_days": get_leave_entitlement(leave_balances, "Annual Leave"),
            "total_annual_used_days": get_leave_used(leave_balances, "Annual Leave"),
            "total_annual_remaining_days": get_leave_remaining(leave_balances, "Annual Leave"),

            # Leave history
            "previous_leave_count": len(leaves_history),
            "previous_approved_leaves": sum(1 for lv in leaves_history if lv.get("status", "").lower() == "approved"),
            "previous_rejected_leaves": sum(1 for lv in leaves_history if lv.get("status", "").lower() == "rejected"),
            "previous_pending_leaves": sum(1 for lv in leaves_history if lv.get("status", "").lower() == "pending"),

            # Attendance
            # "average_daily_hours": calculate_average_hours(attendance_records),
            # "absent_days_this_month": count_absent_days(attendance_records, current_date),
            # "late_checkins_this_month": count_late_checkins(attendance_records),

            # Metadata
            "employee_created_at": employee_data.get("created_at", ""),
            "employee_updated_at": employee_data.get("updated_at", ""),
        }