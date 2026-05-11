from crewai import Agent, Task, Crew, Process
from typing import Dict, List
import json

class EmailOutreachCrew:
    def __init__(self, claude_generator):
        self.claude_generator = claude_generator
        
    def create_research_agent(self):
        return Agent(
            role='Company Research Specialist',
            goal='Research target companies and contacts to gather relevant information',
            backstory="""You are an expert researcher who can quickly find relevant information 
            about companies, their culture, recent news, and key personnel.""",
            verbose=True
        )
    
    def create_email_strategy_agent(self):
        return Agent(
            role='Email Strategy Expert',
            goal='Develop effective email outreach strategies based on purpose and context',
            backstory="""You specialize in crafting personalized outreach strategies that 
            maximize response rates while maintaining professionalism.""",
            verbose=True
        )
    
    def create_personalization_agent(self):
        return Agent(
            role='Email Personalization Expert',
            goal='Add personalized touches to emails based on research findings',
            backstory="""You excel at finding unique angles and personalization points 
            that make emails stand out and feel genuine.""",
            verbose=True
        )
    
    def run_outreach_analysis(self, domain: str, purpose: str, sender_info: Dict) -> Dict:
        """Use CrewAI to analyze and strategize the outreach"""
        
        research_agent = self.create_research_agent()
        strategy_agent = self.create_email_strategy_agent()
        personalization_agent = self.create_personalization_agent()
        
        # Research task
        research_task = Task(
            description=f"""
            Research the company: {domain}
            Find recent news, company culture, and potential talking points.
            Focus on information relevant for: {purpose}
            """,
            agent=research_agent,
            expected_output="Bullet points of key findings and insights"
        )
        
        # Strategy task
        strategy_task = Task(
            description=f"""
            Based on the research, create an outreach strategy for: {purpose}
            Sender: {sender_info.get('name')} - {sender_info.get('title')}
            Consider timing, approach, and key messaging points.
            """,
            agent=strategy_agent,
            expected_output="Detailed outreach strategy with key messaging points"
        )
        
        # Personalization task
        personalization_task = Task(
            description=f"""
            Based on research and strategy, identify specific personalization opportunities.
            Create hooks and angles that would resonate with the target company.
            """,
            agent=personalization_agent,
            expected_output="List of personalization points and hooks"
        )
        
        crew = Crew(
            agents=[research_agent, strategy_agent, personalization_agent],
            tasks=[research_task, strategy_task, personalization_task],
            process=Process.sequential,
            verbose=True
        )
        
        return crew.kickoff()

# MCP (Multi-Channel Personalization) Engine
class MCPEngine:
    def __init__(self):
        self.personalization_factors = [
            "company_recent_news",
            "recipient_role",
            "industry_trends",
            "mutual_connections",
            "seasonal_context"
        ]
    
    def generate_personalization_hooks(self, domain: str, purpose: str) -> List[str]:
        """Generate multi-channel personalization hooks"""
        hooks = []
        
        # Simulated MCP analysis (in real implementation, this would use various data sources)
        if "engineering" in purpose.lower():
            hooks.append("Recent tech stack developments in their industry")
            hooks.append("Engineering culture and practices")
        
        if "startup" in purpose.lower():
            hooks.append("Startup growth trends and challenges")
            hooks.append("Funding landscape insights")
        
        return hooks