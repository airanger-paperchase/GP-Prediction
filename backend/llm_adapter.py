# llm_adapter.py
# import os
# from groq import Groq

# GROQ_KEY = "os.getenv("GROQ_API_KEY")"


# # Initialize the Groq client with your API key from environment variables
# client = Groq(
#     api_key=GROQ_KEY,
# )
import os

from dotenv import load_dotenv
from openai import AzureOpenAI
from api_app import get_secret

load_dotenv()

client = AzureOpenAI(
    api_key=get_secret("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("OPENAI_API_VERSION"),
)


def call_llm(prompt: str) -> str:
    """Call the Azure OpenAI LLM with the provided prompt and return the response."""
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {
                "role": "system",
                "content": """SYSTEM:
                    You are a deterministic taxonomy classifier for financial/staff-cost line items. 
                    Task: For a single input LineItem string, return a strict JSON object (no extra commentary, no markdown) with these fields:

                    {
                    "line_item": <original input string>,
                    "parent": <one canonical Parent string from the allowed set>,
                    "grandparent": <one canonical GrandParent string from the allowed set>,
                    "parent_confidence": <float 0.00-1.00>,
                    "grandparent_confidence": <float 0.00-1.00>,
                    "rationale": <1-2 short sentences explaining the mapping (optional but required)>,
                    "mappings_used": [ <list of canonical alias keys matched> ]
                    }

                    Rules:
                    1. Only use canonical Parent and GrandParent names from the taxonomy list (see below). If a mapping is ambiguous, pick the most likely and set confidence lower (e.g., 0.60).
                    2. Output valid JSON only. No extra text.
                    3. Use numeric confidences between 0.00 and 1.00 (two decimal places recommended).
                    4. Keep "rationale" short (<= 25 words).
                    5. "mappings_used" should list alias tokens you matched (e.g. ["Assistant Manager","F.O.H.","Total Wages"]).

                    Canonical taxonomy (allowed outputs):
                    GrandParents:
                    - "STAFF COST"
                    - "Total Employer Benefits"
                    - "Total Employer Taxes"
                    - "TOTAL OTHER STAFF COST"

                    Parents (examples — canonical names):
                    - "Total Wages - F.O.H. Wages"
                    - "Total Wages - B.O.H. Wages"
                    - "Wages - F.O.H. Wages - Other"
                    - "Wages - B.O.H. Wages - Other"
                    - "Total Employer Benefits"
                    - "Total Employer Taxes"
                    - "TOTAL OTHER STAFF COST"

                    FILLER: Now follow the examples exactly.

                    EXAMPLES:
                    1)
                    Input: "Assistant Manager"
                    Output:
                    {
                    "line_item":"Assistant Manager",
                    "parent":"Total Wages - F.O.H. Wages",
                    "grandparent":"STAFF COST",
                    "parent_confidence":0.98,
                    "grandparent_confidence":0.99,
                    "rationale":"Job title + 'F.O.H. Wages' phrase -> FOH wages group.",
                    "mappings_used":["Assistant Manager","F.O.H.","Total Wages"]
                    }

                    2)
                    Input: "DeliverySTAFF COST Total Wages - B.O.H. Wages"
                    Output:
                    {
                    "line_item":"DeliverySTAFF COST Total Wages - B.O.H. Wages",
                    "parent":"Total Wages - B.O.H. Wages",
                    "grandparent":"STAFF COST",
                    "parent_confidence":0.98,
                    "grandparent_confidence":0.99,
                    "rationale":"Contains 'B.O.H.' and delivery role -> BOH wages.",
                    "mappings_used":["Delivery","B.O.H.","Total Wages"]
                    }

                    3)
                    Input: "Medical"
                    Output:
                    {
                    "line_item":"Medical",
                    "parent":"Total Employer Benefits",
                    "grandparent":"Total Employer Benefits",
                    "parent_confidence":0.98,
                    "grandparent_confidence":0.98,
                    "rationale":"Contains 'Medical' -> employer benefits bucket.",
                    "mappings_used":["Medical","Employer Benefits"]
                    }

                    (END OF EXAMPLES)

                    Now WAIT for the user input line item and respond with the JSON object only.
""",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=16384,
    )
    return response.choices[0].message.content
