import os
import re
import json
import asyncio
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import SimpleJsonOutputParser
from neo4j import AsyncGraphDatabase

# Load environment variables
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")

# Verify configuration
if not OPENROUTER_API_KEY:
    print("[!] Warning: OPENROUTER_API_KEY is not set in environment variables.")

# Initialize LLM via ChatOpenAI configured for OpenRouter
llm = ChatOpenAI(
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=OPENROUTER_API_KEY,
    model_name=OPENROUTER_MODEL,
    default_headers={
        "HTTP-Referer": "https://github.com/its-student/graphrag-project",
        "X-Title": "GraphRAG Distributed Memory System"
    },
    temperature=0.1
)

# Extraction Prompt
EXTRACTION_PROMPT = """
You are an expert knowledge graph extractor. Your task is to extract entities and their relationships from the given text of an IT security incident investigation report.
You must extract entities and group them into the following 5 types (POLE+O):
1. Person (e.g., Alice Smith, Bob Johnson)
2. Object (e.g., DB-SQL-01, Laptop-01, shadow.exe, Financial_2026_Backup.dat)
3. Location (e.g., Singapore Data Center, Jakarta HQ, Server Room 3B, IP addresses/domains)
4. Event (e.g., Midnight Breach, FireWall Failure, Phishing Campaign, Incident Response Meeting)
5. Organization (e.g., DeltaCorp, CyberGuard Inc, Aegis Labs, DarkWeb Syndicate)

Return the output strictly as a JSON object with two keys: "nodes" and "relationships".
Each node must have:
- "id": The name/identifier of the entity (use consistent names, capitalize properly, e.g., 'Alice Smith' or 'DB-SQL-01')
- "type": One of the 5 types (Person, Object, Location, Event, Organization)
- "properties": Key-value pairs of any relevant details extracted (e.g., role, IP address, status, description)

Each relationship must have:
- "source": The id of the source node
- "target": The id of the target node
- "type": The relationship type, UPPERCASE with underscores (e.g., WORKS_AT, COMPROMISED, LOCATED_AT, BELONGS_TO, MANAGED_BY, SENT_TO, DETECTED, RUNS_ON, INVESTIGATES, CONTAINS, COMPROMISED_BY)
- "properties": Key-value pairs of any relevant details of the relationship (e.g., timestamp, status)

Output only valid JSON. Do not wrap in markdown tags or write any explanatory text.
If no entities are found, return {{"nodes": [], "relationships": []}}.

Text to analyze:
{text}
"""


async def insert_node(tx, node):
    """Inserts a node into Neo4j using dynamic labels based on whitelist."""
    entity_type = node.get("type", "Entity")
    valid_labels = {"Person", "Object", "Location", "Event", "Organization"}
    label = entity_type if entity_type in valid_labels else "Entity"
    
    properties = node.get("properties", {})
    properties["id"] = node["id"]
    properties["type"] = label
    
    # We use a Cypher query with dynamic label string interpolation 
    # since labels cannot be parameterized. This is safe as label is verified against whitelist.
    query = f"""
    MERGE (n:{label} {{id: $id}})
    SET n += $props
    """
    await tx.run(query, id=node["id"], props=properties)

async def insert_relationship(tx, rel):
    """Inserts a relationship into Neo4j with sanitized type."""
    source_id = rel["source"]
    target_id = rel["target"]
    rel_type = rel["type"].upper().replace(" ", "_")
    properties = rel.get("properties", {})
    
    # Sanitize relationship type (alphanumeric and underscore only)
    rel_type = re.sub(r'[^a-zA-Z0-9_]', '', rel_type)
    if not rel_type:
        rel_type = "RELATED_TO"
        
    query = f"""
    MATCH (s {{id: $source_id}})
    MATCH (t {{id: $target_id}})
    MERGE (s)-[r:{rel_type}]->(t)
    SET r += $props
    """
    await tx.run(query, source_id=source_id, target_id=target_id, props=properties)

def process_file(file_path: str):
    """Extracts text content or image base64 data from various file types."""
    import os
    ext = file_path.split('.')[-1].lower()
    
    # 1. Plain Text / Markdown
    if ext in ["txt", "md", "json", "xml", "html"]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return content.strip(), None
        except Exception as e:
            print(f"[-] Error reading text file {file_path}: {e}")
            return None, None

    # 2. PDF
    elif ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            text = ""
            for page in reader.pages:
                val = page.extract_text()
                if val:
                    text += val + "\n"
            return text.strip(), None
        except ImportError:
            print("[-] Error: 'pypdf' library is not installed. Please run 'pip install pypdf'.")
            return None, None
        except Exception as e:
            print(f"[-] Error parsing PDF {file_path}: {e}")
            return None, None

    # 3. Word (DOCX)
    elif ext == "docx":
        try:
            import docx
            doc = docx.Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs if p.text])
            return text.strip(), None
        except ImportError:
            print("[-] Error: 'python-docx' library is not installed. Please run 'pip install python-docx'.")
            return None, None
        except Exception as e:
            print(f"[-] Error parsing Word document {file_path}: {e}")
            return None, None

    # 4. CSV / Excel (XLSX, XLS)
    elif ext in ["csv", "xlsx", "xls"]:
        try:
            import pandas as pd
            if ext == "csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            text = df.to_markdown(index=False)
            return text, None
        except ImportError:
            print("[-] Error: 'pandas' or 'openpyxl' library is not installed. Please install them.")
            return None, None
        except Exception as e:
            print(f"[-] Error parsing Table file {file_path}: {e}")
            return None, None

    # 5. Image (PNG, JPG, JPEG, WEBP)
    elif ext in ["png", "jpg", "jpeg", "webp"]:
        try:
            import base64
            with open(file_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode('utf-8')
            mime = f"image/{ext}" if ext in ["png", "webp"] else "image/jpeg"
            return None, {"mime": mime, "base64": encoded}
        except Exception as e:
            print(f"[-] Error reading Image file {file_path}: {e}")
            return None, None

    # 6. Audio / Video (WAV, MP3, M4A, FLAC, OGG, MP4, AVI, MOV, MKV)
    elif ext in ["wav", "mp3", "m4a", "flac", "ogg", "mp4", "avi", "mov", "mkv"]:
        try:
            import speech_recognition as sr
            from pydub import AudioSegment
            import tempfile
            
            wav_path = file_path
            temp_file = None
            
            if ext != "wav":
                print(f"[*] Converting {ext.upper()} to WAV for transcription...")
                audio = AudioSegment.from_file(file_path, format=ext)
                temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                audio.export(temp_file.name, format="wav")
                wav_path = temp_file.name
                
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio_data = r.record(source)
                
            print("[*] Transcribing audio with Google Speech Recognition...")
            try:
                # Try Indonesian
                text = r.recognize_google(audio_data, language="id-ID")
            except sr.UnknownValueError:
                # Fallback to English
                print("    -> No Indonesian speech detected, trying English...")
                text = r.recognize_google(audio_data, language="en-US")
                
            if temp_file:
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
                    
            return text.strip(), None
        except ImportError:
            print("[-] Error: 'SpeechRecognition' or 'pydub' library is not installed. Please install them.")
            return None, None
        except Exception as e:
            print(f"[-] Error transcribing Audio/Video {file_path}: {e}")
            print("    Note: formats other than WAV require 'ffmpeg' system binaries to be installed.")
            return None, None

    else:
        print(f"[!] Unsupported file extension: .{ext} for file: {file_path}")
        return None, None

async def extract_graph_data(text: str = None, image_data: dict = None) -> dict:
    """Uses LLM to extract nodes and relationships from text or image with a retry mechanism."""
    from langchain_core.messages import HumanMessage
    
    if image_data:
        # Construct multimodal message payload
        prompt_text = EXTRACTION_PROMPT.format(text="[Image content - extract graph nodes and relationships representing the cyber security incident or narrative depicted in this image]")
        payload = [
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_data['mime']};base64,{image_data['base64']}"
                        }
                    }
                ]
            )
        ]
    else:
        # Text-only message payload
        prompt = ChatPromptTemplate.from_template(EXTRACTION_PROMPT)
        payload = prompt.format_messages(text=text)

    max_retries = 5
    backoff_delay = 4  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            response = await llm.ainvoke(payload)
            content = response.content.strip()
            
            # Clean markdown code blocks if the LLM ignores instructions
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
                
            data = json.loads(content.strip())
            return data
        except Exception as e:
            print(f"[-] Error during LLM extraction (Attempt {attempt}/{max_retries}): {e}")
            if image_data:
                print("    Note: Make sure your configured model in '.env' supports Vision inputs (e.g. google/gemini-2.0-flash-exp:free).")
            if attempt < max_retries:
                print(f"    Waiting {backoff_delay} seconds before retrying...")
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2
            else:
                print("[-] Max retries reached. Returning empty graph data for this report.")
                return {"nodes": [], "relationships": []}

async def main():
    print("[*] Starting Graph Builder...")
    
    # Ensure dataset directory exists
    dataset_dir = "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    
    supported_extensions = (
        ".txt", ".md", ".pdf", ".docx", ".csv", ".xlsx", ".xls",
        ".png", ".jpg", ".jpeg", ".webp",
        ".wav", ".mp3", ".m4a", ".flac", ".ogg",
        ".mp4", ".avi", ".mov", ".mkv"
    )
    
    # Scan dataset directory for all supported files
    all_files = [os.path.join(dataset_dir, f) for f in os.listdir(dataset_dir) if f.lower().endswith(supported_extensions)]
    
    if not all_files:
        # Fallback to root dataset.txt if present
        if os.path.exists("dataset.txt"):
            all_files = ["dataset.txt"]
            print("[*] No files found in 'dataset/' folder. Falling back to root 'dataset.txt'.")
        else:
            print("[-] Error: No files found in 'dataset/' folder and root 'dataset.txt' is missing.")
            print("    Please run '1_generate_dataset.py' to generate the default dataset or place your files in 'dataset/' folder.")
            return
            
    reports_with_source = []
    for file_path in all_files:
        filename = os.path.basename(file_path)
        print(f"[*] Processing dataset file: {file_path}...")
        
        # Extract text or base64 image data from the file
        extracted_text, image_data = process_file(file_path)
        
        if extracted_text:
            # If the file contains narratives separated by === END OF REPORT ===
            if "=== END OF REPORT ===" in extracted_text:
                parts = [p.strip() for p in extracted_text.split("=== END OF REPORT ===") if p.strip()]
            else:
                parts = [extracted_text.strip()]
                
            for part in parts:
                reports_with_source.append({"text": part, "image": None, "source": filename})
        elif image_data:
            reports_with_source.append({"text": None, "image": image_data, "source": filename})
        else:
            print(f"[-] Could not extract content from file: {filename} (skipping)")
            
    print(f"[+] Loaded {len(reports_with_source)} narrative/media inputs from {len(all_files)} file(s).")
    
    # Extract from all reports
    all_nodes = {}
    all_relationships = []
    
    for i, item in enumerate(reports_with_source, 1):
        source_file = item["source"]
        if item["text"]:
            print(f"[*] Extracting graph data from Report #{i} (text from '{source_file}')...")
            graph_data = await extract_graph_data(text=item["text"])
        else:
            print(f"[*] Extracting graph data from Report #{i} (image from '{source_file}')...")
            graph_data = await extract_graph_data(image_data=item["image"])
            
        nodes = graph_data.get("nodes", [])
        relationships = graph_data.get("relationships", [])
        
        print(f"    -> Extracted {len(nodes)} nodes and {len(relationships)} relationships.")
        
        # Deduplicate nodes by ID, merge properties if node already exists
        for node in nodes:
            nid = node["id"]
            if nid in all_nodes:
                if "properties" not in all_nodes[nid]:
                    all_nodes[nid]["properties"] = {}
                all_nodes[nid]["properties"].update(node.get("properties", {}))
            else:
                if "properties" not in node:
                    node["properties"] = {}
                all_nodes[nid] = node
                
        all_relationships.extend(relationships)
        
    print(f"[+] Extraction complete. Total unique nodes: {len(all_nodes)}, Total relationships: {len(all_relationships)}")
    
    # Connect to Neo4j
    print(f"[*] Connecting to Neo4j database at {NEO4J_URI}...")
    try:
        async with AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)) as driver:
            # Check connection
            await driver.verify_connectivity()
            print("[+] Neo4j connection verified.")
            
            # Open session and insert data
            async with driver.session() as session:
                # 1. Clear database (optional, but good for starting fresh)
                # print("[*] Clearing existing facts in the database...")
                # await session.run("MATCH (n) WHERE NOT n:Session AND NOT n:Message DETACH DELETE n")
                
                # 2. Insert nodes
                print("[*] Inserting nodes...")
                for node in all_nodes.values():
                    await session.execute_write(insert_node, node)
                    
                # 3. Insert relationships
                print("[*] Inserting relationships...")
                for rel in all_relationships:
                    # Only insert relationships where both source and target exist in our nodes list
                    if rel["source"] in all_nodes and rel["target"] in all_nodes:
                        await session.execute_write(insert_relationship, rel)
                    else:
                        print(f"    [-] Skipping relationship {rel['source']} -> {rel['target']} (missing node)")
                        
                # 4. Verify insertion
                print("[*] Verifying data ingestion...")
                result = await session.run(
                    "MATCH (n) WHERE labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization'] "
                    "RETURN labels(n)[0] AS type, count(n) AS count"
                )
                node_summary = []
                async for record in result:
                    node_summary.append(f"{record['type']}: {record['count']}")
                    
                result_rel = await session.run(
                    "MATCH ()-[r]->() WHERE type(r) <> 'HAS_MESSAGE' AND type(r) <> 'NEXT' "
                    "RETURN type(r) AS type, count(r) AS count"
                )
                rel_summary = []
                async for record in result_rel:
                    rel_summary.append(f"{record['type']}: {record['count']}")
                    
                print("\n=== INGESTION SUMMARY ===")
                print("Nodes Ingested:")
                for n_sum in node_summary:
                    print(f"  - {n_sum}")
                print("Relationships Ingested:")
                for r_sum in rel_summary:
                    print(f"  - {r_sum}")
                print("=========================\n")
                
    except Exception as e:
        print(f"[-] Database Error: {e}")
        print("    Please make sure Neo4j is running and credentials are correct in your .env file.")

if __name__ == "__main__":
    # Run async main loop
    asyncio.run(main())
