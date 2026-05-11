import anthropic
import json
from config import API_KEYS, CLAUDE_CONFIG
from typing import Dict, List

class ClaudeEmailGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=API_KEYS["claude"])
        self.model = CLAUDE_CONFIG["model"]
        
        # RAG context for better email generation
        self.email_templates_context = """
        Professional Email Writing Guidelines:
        
        1. JOB SEEKER EMAILS:
           - Start with respectful greeting
           - Mention specific interest in company/role
           - Highlight relevant skills briefly
           - Request conversation/next steps
           - Keep it under 200 words
        
        2. STARTUP FOUNDER EMAILS:
           - Focus on mutual value proposition
           - Be concise about your startup
           - Suggest clear next steps
           - Show knowledge of their work
        
        3. INVESTOR PITCHES:
           - Clear subject line with "Investment Opportunity"
           - Brief problem/solution statement
           - Traction/metrics if available
           - Specific ask
        
        4. REFERRAL REQUESTS:
           - Acknowledge their position respectfully
           - Explain why you're interested
           - Make it easy for them to help
           - Don't be pushy
        """

    def generate_email(self, purpose: str, receiver_info: Dict, sender_info: Dict, custom_context: str = "") -> str:
        """Generate email using Claude with RAG-enhanced context"""
        
        prompt = self._build_prompt(purpose, receiver_info, sender_info, custom_context)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=CLAUDE_CONFIG["max_tokens"],
                temperature=CLAUDE_CONFIG["temperature"],
                system=self.email_templates_context,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            return f"❌ Claude API Error: {str(e)}\n\nFallback template would be used here."

    def _build_prompt(self, purpose: str, receiver_info: Dict, sender_info: Dict, custom_context: str) -> str:
        purposes = {
            "job_seeker": "job application or opportunity inquiry",
            "startup_founder": "startup collaboration or partnership discussion",
            "looking_for_investor": "investment opportunity pitch",
            "job_update": "professional update and reconnection",
            "referral_request": "request for referral or introduction"
        }
        
        return f"""
        Generate a professional email for: {purposes.get(purpose, purpose)}
        
        RECIPIENT INFORMATION:
        - Email: {receiver_info.get('email', 'N/A')}
        - Position: {receiver_info.get('position', 'N/A')}
        - Department: {receiver_info.get('department', 'N/A')}
        - Company: {receiver_info.get('company', 'N/A')}
        
        SENDER INFORMATION:
        - Name: {sender_info.get('name', 'N/A')}
        - Title: {sender_info.get('title', 'N/A')}
        - Company: {sender_info.get('company', 'N/A')}
        - Phone: {sender_info.get('phone', 'N/A')}
        - LinkedIn: {sender_info.get('linkedin', 'N/A')}
        
        CUSTOM CONTEXT: {custom_context}
        
        Please generate:
        1. A compelling subject line
        2. Professional email body (150-250 words)
        3. Appropriate closing
        
        Make it personalized, respectful, and actionable. Focus on creating value for the recipient.
        """