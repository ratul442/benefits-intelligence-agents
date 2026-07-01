"""Transform the flat catalog into the hardened production catalog format.

Adds: catalog metadata, value_type, alignment.basis/positive_option,
dependencies, market_mapping, output_rules.
"""
import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).parent.parent / "data" / "catalog" / "datapoints_catalog.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "catalog" / "datapoints_catalog.json"

# Parent-child dependency map
DEPENDENCIES = {
    "risk_ltd_pct_salary": {"parent_key": "risk_ltd_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_ltd_waiting": {"parent_key": "risk_ltd_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_ltd_max_age": {"parent_key": "risk_ltd_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_std_duration": {"parent_key": "risk_std_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_std_pct_salary": {"parent_key": "risk_std_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_life_multiple": {"parent_key": "risk_life_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_life_flat_amount": {"parent_key": "risk_life_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_life_ee_contrib": {"parent_key": "risk_life_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_add_multiple": {"parent_key": "risk_add_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_add_dismember": {"parent_key": "risk_add_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_ci_amount": {"parent_key": "risk_ci_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_ci_conditions": {"parent_key": "risk_ci_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_tpd_amount": {"parent_key": "risk_tpd_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "risk_life_dep_amount": {"parent_key": "risk_dep_life", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "well_eap_sessions": {"parent_key": "well_eap_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "well_eap_scope": {"parent_key": "well_eap_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "well_eap_dep_access": {"parent_key": "well_eap_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "flex_plan_type": {"parent_key": "flex_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "flex_voluntary_benefits": {"parent_key": "flex_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "flex_allowance_amount": {"parent_key": "flex_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "flex_enrollment_freq": {"parent_key": "flex_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "flex_buyup_options": {"parent_key": "flex_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "flex_elig_all": {"parent_key": "flex_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "meal_type": {"parent_key": "meal_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "meal_amount": {"parent_key": "meal_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
    "meal_elig_all": {"parent_key": "meal_prev", "required_parent_values": ["Yes"], "if_not_met": "N/A"},
}

# Explicit value_type overrides for known keys
VALUE_TYPE_OVERRIDES = {
    # Percentages
    "ret_er_contrib_rate": "percentage",
    "ret_ee_contrib_rate": "percentage",
    "health_dental_reimb_pct": "percentage",
    "health_surg_coverage_pct": "percentage",
    "health_outpatient_coverage": "percentage",
    "risk_std_pct_salary": "percentage",
    "risk_ltd_pct_salary": "percentage",
    "to_maternity_pay": "percentage",
    # Amounts
    "health_dental_annual_max_ee": "amount",
    "health_dental_annual_max_dep": "amount",
    "health_surg_annual_max": "amount",
    "health_outpatient_annual_max": "amount",
    "health_outpatient_copay": "amount",
    "health_major_med_lifetime_max": "amount",
    "health_maternity_normal_max": "amount",
    "health_maternity_comp_max": "amount",
    "health_vision_annual_max": "amount",
    "well_physical_checkup_amount": "amount",
    "bti_accident_amount": "amount",
    "bti_medical_max": "amount",
    "perq_edu_amount": "amount",
    "perq_child_edu_amount": "amount",
    "flex_allowance_amount": "amount",
    "meal_amount": "amount",
    "risk_ci_amount": "amount",
    "risk_tpd_amount": "amount",
    "risk_life_dep_amount": "amount",
    # Salary multiples
    "risk_life_multiple": "salary_multiple",
    "risk_life_flat_amount": "amount",
    "risk_add_multiple": "salary_multiple",
    # Days
    "to_annual_leave_days": "days",
    "to_annual_leave_exec": "days",
    "to_annual_leave_mid": "days",
    "to_annual_leave_entry": "days",
    "to_annual_leave_max": "days",
    "to_sick_leave_days": "days",
    "to_paternity_days": "days",
    "to_public_holidays": "days",
    # Weeks
    "to_maternity_weeks": "weeks",
    # Duration
    "risk_std_duration": "weeks",
    "risk_ltd_waiting": "duration",
    # Age
    "risk_ltd_max_age": "age",
    # Number
    "well_eap_sessions": "number",
    "risk_ci_conditions": "number",
    "health_surg_deductible": "amount",
    # Multi-select
    "bti_types": "multi_select_list",
    "perq_types": "multi_select_list",
    "perq_edu_types": "multi_select_list",
    "perq_service_award_milestones": "multi_select_list",
    "flex_voluntary_benefits": "multi_select_list",
    "well_eap_scope": "multi_select_list",
    "well_social_flex_work": "multi_select_list",
    "health_maternity_coverage": "multi_select_list",
    # Category
    "ret_plan_type": "category",
    "ret_cash_lieu_method": "category",
    "health_surg_room_type": "category",
    "health_provider_network": "category",
    "meal_type": "category",
    "flex_plan_type": "category",
    "perq_service_award_type": "category",
    "ret_vesting": "category",
    "ret_waiting_period": "category",
}


def infer_value_type(item: dict) -> str:
    """Infer value_type from catalog entry."""
    key = item["comparison_key"]
    if key in VALUE_TYPE_OVERRIDES:
        return VALUE_TYPE_OVERRIDES[key]
    
    prompt = item.get("company_prompt", "").lower()
    logic = item.get("alignment_logic", "")
    
    # Heuristic inference
    if logic == "50th Percentile":
        if "percentage" in prompt or "%" in prompt:
            return "percentage"
        if "amount" in prompt or "maximum" in prompt or "allowance" in prompt:
            return "amount"
        if "days" in prompt:
            return "days"
        if "weeks" in prompt:
            return "weeks"
        if "multiple" in prompt:
            return "salary_multiple"
        return "number"
    
    if "yes/no" in prompt:
        return "yes_no"
    if "extract list" in prompt or "extract types" in prompt or "extract service list" in prompt:
        return "multi_select_list"
    if "extract type" in prompt:
        return "category"
    
    return "yes_no"  # Default for Prevalence entries


def infer_alignment_basis(item: dict, value_type: str) -> dict:
    """Build the alignment object with basis and positive_option."""
    logic = item.get("alignment_logic", "Prevalence")
    
    if logic == "50th Percentile":
        return {
            "logic": "50th Percentile",
            "basis": "numeric_percentile"
        }
    
    # Prevalence logic
    if value_type == "yes_no":
        return {
            "logic": "Prevalence",
            "basis": "yes_no_prevalence",
            "positive_option": "Yes"
        }
    elif value_type in ("multi_select_list", "category"):
        return {
            "logic": "Prevalence",
            "basis": "selected_option_prevalence"
        }
    else:
        return {
            "logic": "Prevalence",
            "basis": "yes_no_prevalence",
            "positive_option": "Yes"
        }


def extract_market_mapping(prompt: str) -> dict | None:
    """Extract MARKET MAPPING from company_prompt text."""
    match = re.search(r"MARKET MAPPING:\s*['\"]?(.+?)['\"]?\s*\.?\s*$", prompt)
    if not match:
        match = re.search(r"MARKET MAPPING:\s*(.+?)$", prompt)
    if not match:
        return None
    
    mapping_text = match.group(1).strip().rstrip(".")
    
    # Try to split section | option pattern
    if "|" in mapping_text:
        parts = [p.strip().strip("'\"") for p in mapping_text.split("|")]
        return {
            "question": parts[0],
            "option": parts[1] if len(parts) > 1 else None,
            "match_strategy": "exact_option"
        }
    
    return {
        "question": mapping_text.strip("'\""),
        "option": None,
        "match_strategy": "section_match"
    }


def clean_company_prompt(prompt: str) -> str:
    """Remove MARKET MAPPING and format tags from company_prompt."""
    # Remove [Format: Fx] tags
    cleaned = re.sub(r"\s*\[Format:\s*F\d+\]\s*", " ", prompt)
    # Remove MARKET MAPPING: ... at end
    cleaned = re.sub(r"\s*MARKET MAPPING:.*$", "", cleaned)
    return cleaned.strip()


def transform_catalog(items: list[dict]) -> dict:
    """Transform flat catalog array into hardened production format."""
    transformed_items = []
    
    for item in items:
        key = item["comparison_key"]
        value_type = infer_value_type(item)
        alignment = infer_alignment_basis(item, value_type)
        market_mapping = extract_market_mapping(item.get("company_prompt", ""))
        
        new_item = {
            "comparison_key": key,
            "pretty_name": item["pretty_name"],
            "benefit_topic": item["benefit_topic"],
            "company_prompt": clean_company_prompt(item.get("company_prompt", "")),
            "value_type": value_type,
            "alignment": alignment,
            "format_tag": item.get("format_tag", "F4"),
        }
        
        if market_mapping:
            new_item["market_mapping"] = market_mapping
        
        if key in DEPENDENCIES:
            new_item["dependencies"] = DEPENDENCIES[key]
        
        # Default output rules
        new_item["output_rules"] = {
            "allow_not_provided": True,
            "dual_blank_outputs_na": True,
            "suppress_plan_names": True,
            "no_literal_line_breaks": True,
        }
        
        transformed_items.append(new_item)
    
    # Wrap with catalog metadata
    return {
        "catalog_id": "benefits-review",
        "catalog_version": "2026-05-sgp-v1",
        "country": "SGP",
        "survey_config_version": "sgp-benefits-survey-2026",
        "owner": "Benefits Benchmarking",
        "total_datapoints": len(transformed_items),
        "items": transformed_items,
    }


if __name__ == "__main__":
    with open(CATALOG_PATH) as f:
        items = json.load(f)
    
    hardened = transform_catalog(items)
    
    with open(OUTPUT_PATH, "w") as f:
        json.dump(hardened, f, indent=2)
    
    print(f"Transformed {len(items)} items → hardened catalog v{hardened['catalog_version']}")
    print(f"  Value types: {len(set(i['value_type'] for i in hardened['items']))} distinct types")
    print(f"  Dependencies defined: {sum(1 for i in hardened['items'] if 'dependencies' in i)}")
    print(f"  Market mappings: {sum(1 for i in hardened['items'] if 'market_mapping' in i)}")
