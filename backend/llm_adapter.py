
import logging
import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
    handlers=[logging.FileHandler("llm_adapter.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
# Initialize Key Vault client
KEY_VAULT_NAME = os.getenv("KEY_VAULT_NAME")
if not KEY_VAULT_NAME:
    logger.error("Missing required environment variable: KEY_VAULT_NAME")
    raise ValueError("KEY_VAULT_NAME environment variable is required.")
KV_URI = f"https://{KEY_VAULT_NAME}.vault.azure.net/"

# Initialize Azure credentials
try:
    # In production, DefaultAzureCredential will automatically use the managed identity
    # configured in the deployment.yaml without needing explicit client ID
    credential = DefaultAzureCredential()
    print("Successfully initialized DefaultAzureCredential")
    secret_client = SecretClient(vault_url=KV_URI, credential=credential)
except Exception as e:
    logger.error(f"Failed to initialize Azure credential: {str(e)}")
    raise


def get_secret(secret_name: str) -> str:
    if not secret_name:
        logger.error("Secret name required for get_secret")
        raise ValueError("Secret name must not be empty")
    try:
        return secret_client.get_secret(secret_name).value
    except Exception as e:
        logger.error("Failed to fetch secret %s from Key Vault: %s", secret_name, str(e))
        raise

api_key = get_secret("AZURE-OPENAI-KEY")
print("1- Azure OpenAI key:")

# Initialize Azure OpenAI client
try:
    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv(
            "OPENAI_API_VERSION", "2023-05-15"
        ),  # Add default API version
    )
    print("Successfully initialized Azure OpenAI client")
    print("2 - Azure OpenAI key:")
except Exception as e:
    logger.error(f"Failed to initialize Azure OpenAI client: {str(e)}")
    raise


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
