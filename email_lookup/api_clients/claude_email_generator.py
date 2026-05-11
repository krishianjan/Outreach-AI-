import anthropic
from config import API_KEYS, CLAUDE_CONFIG
from typing import Dict

class ClaudeEmailGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=API_KEYS["claude"])
        # Try different model names - Claude frequently updates these
        self.possible_models = [
            "claude-3-5-sonnet-20241022",  # Latest model
            "claude-3-5-sonnet-20240620",
            "claude-3-sonnet-20240229",    # Original model name
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307"
        ]
        self.model = self._get_available_model()
    
    def _get_available_model(self):
        """Try to find an available model from the list"""
        for model in self.possible_models:
            try:
                # Test if the model is available by making a small request
                self.client.messages.create(
                    model=model,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Test"}]
                )
                print(f"✅ Using model: {model}")
                return model
            except Exception as e:
                print(f"❌ Model {model} not available: {e}")
                continue
        
        # Fallback to the first model and let it fail with a clear error
        print("⚠️ No model found, using fallback")
        return self.possible_models[0]
    
    def generate_email(self, purpose: str, contact_info: Dict, sender_info: Dict, previous_email: str = "") -> str:
        """Generate email using Claude API"""
        
        prompt = self._build_prompt(purpose, contact_info, sender_info, previous_email)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=CLAUDE_CONFIG["max_tokens"],
                temperature=CLAUDE_CONFIG["temperature"],
                system=self._get_system_prompt(purpose),
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except anthropic.APIConnectionError as e:
            return f"❌ Connection error: {e}"
        except anthropic.RateLimitError as e:
            return f"❌ Rate limit exceeded: {e}"
        except anthropic.APIStatusError as e:
            return f"❌ API error {e.status_code}: {e.response}"
        except Exception as e:
            return f"❌ Error generating email: {str(e)}"
    
    def _get_system_prompt(self, purpose: str) -> str:
        purposes = {
            "job_seeker": """You are an expert email writer crafting professional job inquiry emails. 
            Guidelines:
            - Be respectful and concise
            - Highlight relevant skills matching the target company
            - Show genuine interest in their work
            - Include a clear call-to-action
            - Keep it under 200 words
            - Personalize based on the recipient's role""",
            
            "startup_founder": """You are a startup founder seeking collaboration opportunities.
            Guidelines:
            - Focus on mutual value proposition
            - Be clear about your startup's mission
            - Suggest specific next steps
            - Show knowledge of their company
            - Keep it professional but enthusiastic""",
            
            "looking_for_investor": """You are pitching your startup to potential investors.
            Guidelines:
            - Clear subject line with "Investment Opportunity"
            - Brief problem/solution statement
            - Mention traction or milestones
            - Specific ask or next steps
            - Professional but compelling tone""",
            
            "job_update": """You are sharing a professional update with a contact.
            Guidelines:
            - Positive and professional tone
            - Briefly share your update
            - Reconnect without being pushy
            - Offer value or insights
            - Keep it friendly but business-appropriate""",
            
            "referral_request": """You are requesting a referral or introduction.
            Guidelines:
            - Be respectful of their time
            - Explain why you're interested
            - Make it easy for them to help
            - Show appreciation
            - Don't be pushy or demanding"""
        }
        return purposes.get(purpose, "Write a professional, concise email that will get a positive response.")
    
    def _build_prompt(self, purpose: str, contact_info: Dict, sender_info: Dict, previous_email: str) -> str:
        if previous_email:
            # Follow-up email
            return f"""
            Write a professional follow-up email. Here's the context:
            
            PREVIOUS EMAIL SENT:
            {previous_email}
            
            RECIPIENT DETAILS:
            - Name: {contact_info.get('name', 'Contact')}
            - Email: {contact_info.get('email', '')}
            - Position: {contact_info.get('position', 'N/A')}
            - Company: {contact_info.get('company', '')}
            
            YOUR DETAILS:
            - Name: {sender_info.get('name', '')}
            - Title: {sender_info.get('title', '')}
            - Company: {sender_info.get('company', '')}
            
            Write a polite, non-pushy follow-up email. Reference the previous email lightly and suggest a gentle next step.
            """
        else:
            # Initial email
            return f"""
            Write a professional email based on these details:
            
            PURPOSE: {purpose.replace('_', ' ').title()}
            
            RECIPIENT INFORMATION:
            - Name: {contact_info.get('name', 'Contact')}
            - Email: {contact_info.get('email', '')}
            - Position: {contact_info.get('position', 'N/A')}
            - Company: {contact_info.get('company', '')}
            - Department: {contact_info.get('department', 'N/A')}
            
            YOUR INFORMATION:
            - Your Name: {sender_info.get('name', '')}
            - Your Title: {sender_info.get('title', '')}
            - Your Company: {sender_info.get('company', '')}
            - Your Phone: {sender_info.get('phone', '')}
            - Your LinkedIn: {sender_info.get('linkedin', '')}
            
            Write a compelling email that includes:
            1. A professional subject line
            2. Personalized opening
            3. Clear purpose statement
            4. Value proposition or reason for connecting
            5. Specific call-to-action
            6. Professional closing
            
            Keep it under 200 words, personalized, and likely to get a response.
            """