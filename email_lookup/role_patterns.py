ROLE_PATTERNS = {
    # Technical Roles
    "software_engineer": {
        "keywords": ["software", "engineer", "developer", "dev", "programmer"],
        "titles": ["software engineer", "backend developer", "full stack engineer"],
        "departments": ["engineering", "technology"]
    },
    "data_engineer": {
        "keywords": ["data", "etl", "pipeline", "analytics", "warehouse"],
        "titles": ["data engineer", "data developer", "etl specialist"],
        "departments": ["data", "analytics"]
    },
    
    # Leadership Roles
    "cto": {
        "keywords": ["chief", "technology", "officer", "technical"],
        "titles": ["cto", "chief technology officer"],
        "departments": ["executive", "technology"]
    },
    "ceo": {
        "keywords": ["chief", "executive", "officer", "president"],
        "titles": ["ceo", "chief executive officer"],
        "departments": ["executive"]
    },
    
    # Management Roles
    "engineering_manager": {
        "keywords": ["manager", "lead", "supervisor", "engineering"],
        "titles": ["engineering manager", "dev manager", "tech lead"],
        "departments": ["engineering"]
    },
    
    # HR/Recruiting
    "recruiter": {
        "keywords": ["talent", "recruit", "hr", "hiring"],
        "titles": ["recruiter", "talent acquisition"],
        "departments": ["human resources"]
    }
}

def get_position_for_role(role: str) -> str:
    """Convert our role to GetProspect's position parameter"""
    return ROLE_PATTERNS.get(role, {}).get("titles", [""])[0]