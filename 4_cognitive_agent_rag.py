import os
import sys
import json
import asyncio
from typing import TypedDict, Dict, Any, List
from dotenv import load_dotenv

# Import LangChain / LangGraph components
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Import our custom Neo4j memory manager via importlib since filename starts with a number
import importlib
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
memory_server_module = importlib.import_module("3_memory_server")
Neo4jMemoryServer = memory_server_module.Neo4jMemoryServer

load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")

# Initialize LLM via ChatOpenAI configured for OpenRouter
llm = ChatOpenAI(
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=OPENROUTER_API_KEY,
    model_name=OPENROUTER_MODEL,
    default_headers={
        "HTTP-Referer": "https://github.com/AldaniP/graphrag-project",
        "X-Title": "GraphRAG Distributed Memory System"
    },
    temperature=0.2
)

# Connect to database
memory_manager = Neo4jMemoryServer()

# Define Agent State for LangGraph
class AgentState(TypedDict):
    session_id: str
    query: str
    messages: List[Dict[str, str]]  # Short-term chat history
    context: str                     # Long-term memory facts retrieved
    thoughts: List[str]              # Reasoning thoughts history
    next_action: Dict[str, Any]      # Action details: type and parameters
    response: str                    # Final answer
    step_count: int                  # Count of cognitive loops executed

# System Prompt for Reasoning Node
REASONING_PROMPT = """
You are the brain of a cognitive AI agent. You are investigating a cyber security breach or helping a user retrieve and store information in a distributed graph memory.
You have access to:
1. Short-term Memory (Chat History): Current conversation context.
2. Long-term Memory (Retrieved Graph Facts): Facts about Persons, Objects, Locations, Events, and Organizations.

Your goal is to answer the user's query: "{query}"

Current state:
- Short-term Memory (Chat History):
{chat_history}

- Retrieved Graph Facts (Long-term Context):
{context}

- Previous Reasoning Steps in this turn:
{thoughts}

You must decide whether you have enough information to answer the user's query, or if you need to perform an action.
You can choose one of the following actions:
1. `answer`: If you have sufficient information to answer the user's query.
2. `search`: If you need to search for another entity in the memory graph to get more context.
3. `write_fact`: If you discovered a new fact from the user's query or conversation that should be stored in the long-term memory graph.

Format your output strictly as a JSON object with the following fields:
- "thought": A detailed description of your reasoning (what you are thinking, what details you have, and why you are choosing the next action).
- "action_type": "answer", "search", or "write_fact".
- "action_details":
  - If action_type is "answer", this is the final detailed markdown answer to the user.
  - If action_type is "search", this is the query string (e.g., entity name) to lookup in the memory graph.
  - If action_type is "write_fact", this is a JSON object with:
    - "entity_id": Name/ID of the entity.
    - "entity_type": "Person", "Object", "Location", "Event", or "Organization".
    - "properties": Key-value pairs of properties (e.g., role, status, description).
    - "relationship": (Optional) A JSON object if you also want to create a relationship to another existing entity:
      - "target_id": Target entity ID.
      - "type": Relationship type (UPPERCASE with underscores).
      - "properties": Key-value pairs for the relationship.

Output only valid JSON. Do not wrap in markdown or include any explanatory text outside the JSON.
"""

# ==========================================
# LANGGRAPH NODE FUNCTIONS
# ==========================================

async def retrieve_context_node(state: AgentState) -> Dict[str, Any]:
    """Node: Retrieves facts related to the query from long-term memory (GraphRAG)."""
    print("[*] Node: Retrieving context from long-term memory...")
    await memory_manager.connect()
    
    # Retrieve facts from Neo4j
    facts = await memory_manager.search_facts(state["query"])
    
    return {
        "context": facts,
        "step_count": state.get("step_count", 0)
    }

def parse_llm_json(content: str) -> dict:
    """Parses LLM JSON response with a robust regex-based fallback if malformed."""
    import re
    import json
    content = content.strip()
    
    # Clean potential markdown wrappers
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    try:
        return json.loads(content)
    except Exception as e:
        print(f"[!] Standard JSON parsing failed ({e}). Attempting regex recovery...")
        
        # Regex to extract thought, action_type
        thought_match = re.search(r'"thought"\s*:\s*"(.*?)"\s*(?:,|\n|})', content, re.DOTALL)
        if not thought_match:
            thought_match = re.search(r'"thought"\s*:\s*\'(.*?)\'\s*(?:,|\n|})', content, re.DOTALL)
            
        action_type_match = re.search(r'"action_type"\s*:\s*"(.*?)"', content, re.IGNORECASE)
        if not action_type_match:
            action_type_match = re.search(r'"action_type"\s*:\s*\'(.*?)\'', content, re.IGNORECASE)
            
        thought = thought_match.group(1) if thought_match else "Thinking..."
        action_type = action_type_match.group(1) if action_type_match else "answer"
        
        # Determine details
        action_details = {}
        if action_type == "search":
            query_match = re.search(r'"query"\s*:\s*"(.*?)"', content, re.IGNORECASE)
            if not query_match:
                query_match = re.search(r'"query"\s*:\s*\'(.*?)\'', content, re.IGNORECASE)
            if query_match:
                action_details = {"query": query_match.group(1)}
            else:
                details_match = re.search(r'"action_details"\s*:\s*"(.*?)"', content, re.IGNORECASE)
                if details_match:
                    action_details = {"query": details_match.group(1)}
                
        elif action_type == "answer":
            # Extract detailed answer response
            details_match = re.search(r'"action_details"\s*:\s*"(.*?)"\s*$', content, re.DOTALL)
            if not details_match:
                details_match = re.search(r'"action_details"\s*:\s*"(.*?)"\s*(?:,|\n|})', content, re.DOTALL)
            if details_match:
                action_details = details_match.group(1)
            else:
                action_details = "Terjadi masalah parsing detail pemikiran. Namun, investigasi selesai."
        else:
            action_details = {}
            
        # Clean up escapes
        thought = thought.replace('\\"', '"').replace('\\n', '\n')
        if isinstance(action_details, str):
            action_details = action_details.replace('\\"', '"').replace('\\n', '\n')
            
        return {
            "thought": thought,
            "action_type": action_type,
            "action_details": action_details
        }

async def reason_node(state: AgentState) -> Dict[str, Any]:
    """Node: Evaluates state and decides next action (answer, search, or write_fact)."""
    print(f"[*] Node: Reason (Step {state.get('step_count', 0) + 1})...")
    
    # Format chat history
    chat_history_str = ""
    for msg in state["messages"]:
        chat_history_str += f"{msg['role'].upper()}: {msg['content']}\n"
        
    # Format previous thoughts
    thoughts_str = "\n".join([f"- {t}" for t in state.get("thoughts", [])])
    if not thoughts_str:
        thoughts_str = "None"
        
    prompt = ChatPromptTemplate.from_template(REASONING_PROMPT)
    chain = prompt | llm
    
    try:
        response = await chain.ainvoke({
            "query": state["query"],
            "chat_history": chat_history_str,
            "context": state["context"],
            "thoughts": thoughts_str
        })
        
        content = response.content.strip()
        action_data = parse_llm_json(content)
        
        thought = action_data.get("thought", "Thinking...")
        action_type = action_data.get("action_type", "answer")
        action_details = action_data.get("action_details", {})
        
        # Log this reasoning step in episodic memory
        await memory_manager.connect()
        await memory_manager.log_reasoning_step(
            session_id=state["session_id"],
            step_index=state.get("step_count", 0) + 1,
            thought=thought,
            action_name=action_type,
            action_details=json.dumps(action_details)
        )
        
        # Update state
        new_thoughts = list(state.get("thoughts", []))
        new_thoughts.append(thought)
        
        return {
            "thoughts": new_thoughts,
            "next_action": {"type": action_type, "details": action_details},
            "step_count": state.get("step_count", 0) + 1
        }
        
    except Exception as e:
        print(f"[-] Error in reason node: {e}")
        # Fallback to direct answer action
        return {
            "next_action": {
                "type": "answer",
                "details": f"I encountered an error processing my thoughts: {str(e)}. Let me answer directly."
            },
            "step_count": state.get("step_count", 0) + 1
        }

async def execute_action_node(state: AgentState) -> Dict[str, Any]:
    """Node: Executes the tool action selected by the reason node."""
    action = state["next_action"]
    action_type = action["type"]
    details = action["details"]
    
    print(f"[*] Node: Executing action '{action_type}'...")
    await memory_manager.connect()
    
    current_context = state["context"]
    
    if action_type == "search":
        if isinstance(details, dict):
            search_query = details.get("query", details.get("search_query", next(iter(details.values())) if details else ""))
        else:
            search_query = details
        new_facts = await memory_manager.search_facts(search_query)
        current_context += f"\n\n### Additional search for '{search_query}':\n{new_facts}"
        print(f"    -> Additional facts retrieved for: {search_query}")
        
    elif action_type == "write_fact":
        entity_id = details.get("entity_id")
        entity_type = details.get("entity_type")
        properties = details.get("properties", {})
        
        # Write node
        await memory_manager.write_fact_node(entity_id, entity_type, properties)
        print(f"    -> Saved long-term node: {entity_id} ({entity_type})")
        
        # Write optional relationship
        rel = details.get("relationship")
        if rel:
            target_id = rel.get("target_id")
            rel_type = rel.get("type")
            rel_props = rel.get("properties", {})
            await memory_manager.write_fact_relationship(entity_id, target_id, rel_type, rel_props)
            print(f"    -> Saved relationship: {entity_id} -[{rel_type}]-> {target_id}")
            
        current_context += f"\n[System Log: Successfully wrote fact: {entity_id} ({entity_type})]"
        
    return {
        "context": current_context,
        "next_action": {} # Reset action
    }

async def generate_answer_node(state: AgentState) -> Dict[str, Any]:
    """Node: Finalizes response and saves both query & response to short-term memory."""
    print("[*] Node: Generating final answer...")
    await memory_manager.connect()
    
    action = state.get("next_action", {})
    response_text = ""
    
    if action.get("type") == "answer":
        response_text = action["details"]
    else:
        # Fallback: We hit the step limit or did not get a direct 'answer' action type.
        # Call the LLM one final time to compile all gathered facts and thoughts into a natural language response.
        final_prompt = """
        You are a cognitive AI agent. You have completed your investigation steps and must now compile a final, comprehensive answer for the user's query: "{query}"
        
        Here is the accumulated context from the memory graph:
        {context}
        
        Here is the chat history:
        {chat_history}
        
        Here are your reasoning thoughts during the investigation:
        {thoughts}
        
        Please provide the final, formatted markdown response to the user. Do not include JSON formatting or search queries. Just write a clear, helpful answer in the user's language (Indonesian).
        """
        # Format chat history
        chat_history_str = ""
        for msg in state["messages"]:
            chat_history_str += f"{msg['role'].upper()}: {msg['content']}\n"
            
        thoughts_str = "\n".join([f"- {t}" for t in state.get("thoughts", [])])
        if not thoughts_str:
            thoughts_str = "None"
            
        prompt = ChatPromptTemplate.from_template(final_prompt)
        chain = prompt | llm
        
        try:
            response = await chain.ainvoke({
                "query": state["query"],
                "context": state["context"],
                "chat_history": chat_history_str,
                "thoughts": thoughts_str
            })
            response_text = response.content.strip()
        except Exception as e:
            response_text = f"Maaf, saya tidak dapat merumuskan jawaban akhir karena kesalahan: {e}"
        
    # Write to short-term memory (Session/Message)
    # 1. Save user query
    await memory_manager.add_message(state["session_id"], "user", state["query"])
    # 2. Save assistant response
    await memory_manager.add_message(state["session_id"], "assistant", response_text)
    
    print("[+] Conversational turn recorded in short-term memory.")
    
    return {
        "response": response_text
    }

# ==========================================
# ROUTING LOGIC
# ==========================================

def route_decision(state: AgentState) -> str:
    """Decides whether to execute action or compile the final answer."""
    next_action = state.get("next_action", {})
    action_type = next_action.get("type", "answer")
    
    # Prevent infinite loops (max 4 cognitive cycles)
    if state.get("step_count", 0) >= 4 or action_type == "answer":
        return "generate_answer"
    return "execute_action"

# ==========================================
# BUILD LANGGRAPH WORKFLOW
# ==========================================

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("retrieve_context", retrieve_context_node)
workflow.add_node("reason", reason_node)
workflow.add_node("execute_action", execute_action_node)
workflow.add_node("generate_answer", generate_answer_node)

# Set Entry Point
workflow.set_entry_point("retrieve_context")

# Define Transitions
workflow.add_edge("retrieve_context", "reason")
workflow.add_conditional_edges(
    "reason",
    route_decision,
    {
        "execute_action": "execute_action",
        "generate_answer": "generate_answer"
    }
)
workflow.add_edge("execute_action", "reason")
workflow.add_edge("generate_answer", END)

# Compile Graph
agent_graph = workflow.compile()

# ==========================================
# INTERACTIVE TERMINAL LAYOUT & SPINNER
# ==========================================
import time
import threading

# ANSI Escape Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_BLUE = "\033[34m"
C_GRAY = "\033[90m"

class ConsoleSpinner:
    def __init__(self, message="Agen sedang menganalisis"):
        self.message = message
        self.running = False
        self.thread = None

    def spin(self):
        chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        while self.running:
            sys.stdout.write(f"\r{C_CYAN}{chars[idx]} {self.message}...{C_RESET}")
            sys.stdout.flush()
            idx = (idx + 1) % len(chars)
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

async def print_db_stats():
    """Prints a styled card containing current Neo4j database statistics."""
    print(f"\n{C_BLUE}┌──────────────────────────────────────────────┐{C_RESET}")
    print(f"{C_BLUE}│       STATISTIK MEMORI JANGKA PANJANG        │{C_RESET}")
    print(f"{C_BLUE}├──────────────────────────────────────────────┤{C_RESET}")
    try:
        async with memory_manager.driver.session() as session:
            res = await session.run(
                "MATCH (n) WHERE labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization'] "
                "RETURN labels(n)[0] AS label, count(n) AS count"
            )
            total = 0
            async for rec in res:
                label_name = f"{rec['label']}:"
                count_val = rec['count']
                total += count_val
                print(f"{C_BLUE}│{C_RESET}  - {C_BOLD}{label_name:<15}{C_RESET} {count_val:<23} {C_BLUE}│{C_RESET}")
                
            res_rel = await session.run(
                "MATCH ()-[r]->() WHERE type(r) <> 'HAS_MESSAGE' AND type(r) <> 'NEXT' "
                "AND type(r) <> 'HAS_REASONING' AND type(r) <> 'NEXT_STEP' AND type(r) <> 'EXECUTED' "
                "RETURN count(r) AS count"
            )
            record_rel = await res_rel.single()
            rel_count = record_rel['count'] if record_rel else 0
            print(f"{C_BLUE}├──────────────────────────────────────────────┤{C_RESET}")
            print(f"{C_BLUE}│{C_RESET}  {C_BOLD}Total Node:{C_RESET}  {total:<11} {C_BOLD}Total Relasi:{C_RESET} {rel_count:<7} {C_BLUE}│{C_RESET}")
    except Exception as e:
        print(f"{C_BLUE}│{C_RESET}  {C_RED}Gagal memuat statistik database: {e:<10}{C_RESET} {C_BLUE}│{C_RESET}")
    print(f"{C_BLUE}└──────────────────────────────────────────────┘{C_RESET}\n")

async def run_cli():
    print(f"{C_CYAN}{C_BOLD}")
    print("  ____                 _      ____     _     ____ ")
    print(" / ___|_ __ __ _ _ __ | |__  |  _ \\   / \\   / ___|")
    print("| |  _| '__/ _` | '_ \\| '_ \\ | |_) | / _ \\ | |  _ ")
    print("| |_| | | | (_| | |_) | | | ||  _ < / ___ \\| |_| |")
    print(" \\____|_|  \\__,_| .__/|_| |_||_| \\_/_/   \\_\\\\____|")
    print("                |_|                               ")
    print(f"{C_RESET}")
    print(f"{C_BOLD}Sistem Multi-Agen GraphRAG dengan Memori Terdistribusi Neo4j{C_RESET}")
    print(f"{C_GRAY}============================================================{C_RESET}")
    
    try:
        await memory_manager.connect()
        await memory_manager.init_constraints()
    except Exception as e:
        print(f"\n{C_RED}[-] Fatal: Gagal terhubung ke Neo4j database: {e}{C_RESET}")
        print("    Pastikan database Neo4j lokal Anda aktif dan berkas '.env' terkonfigurasi.")
        sys.exit(1)
        
    print(f"{C_GREEN}[+] Koneksi Neo4j terverifikasi.{C_RESET}")
    session_id = input(f"{C_BOLD}[?] Masukkan Session ID (default: session_001): {C_RESET}").strip()
    if not session_id:
        session_id = "session_001"
        
    print(f"\n{C_GREEN}[+] Memulai sesi: {C_BOLD}{session_id}{C_RESET}")
    print(f"{C_GRAY}────────────────────────────────────────────────────────────{C_RESET}")
    print(f"Perintah Khusus:")
    print(f"  {C_BOLD}/clear{C_RESET}  - Bersihkan histori chat & log berpikir sesi ini")
    print(f"  {C_BOLD}/stats{C_RESET}  - Tampilkan statistik entitas graf di Neo4j")
    print(f"  {C_BOLD}/help{C_RESET}   - Tampilkan panduan kueri")
    print(f"  {C_BOLD}/exit{C_RESET}   - Keluar dari program")
    print(f"{C_GRAY}────────────────────────────────────────────────────────────{C_RESET}")

    while True:
        try:
            query = input(f"\n{C_GREEN}{C_BOLD}User > {C_RESET}").strip()
            if not query:
                continue
            
            if query.lower() in ["/exit", "exit", "keluar"]:
                print(f"\n{C_YELLOW}[-] Menutup koneksi database dan keluar. Sampai jumpa!{C_RESET}\n")
                break
                
            if query.lower() in ["/clear", "clear session", "hapus sesi"]:
                print(f"\n{C_YELLOW}[*] Menghapus riwayat percakapan dan log berpikir sesi: {session_id}...{C_RESET}")
                await memory_manager.delete_session_history(session_id)
                print(f"{C_GREEN}[+] Sesi {session_id} berhasil dibersihkan! (Ingatan jangka panjang tetap utuh){C_RESET}")
                print(f"{C_GRAY}────────────────────────────────────────────────────────────{C_RESET}")
                continue
                
            if query.lower() == "/stats":
                await print_db_stats()
                continue
                
            if query.lower() == "/help":
                print(f"\n{C_BOLD}💡 Panduan Tanya-Jawab GraphRAG:{C_RESET}")
                print("1. Tanya umum: 'Informasi apa yang kamu punya?' (Menampilkan kategori & sampel).")
                print("2. Tanya spesifik: 'Siapa itu Alice Smith dan di mana dia bekerja?'")
                print("3. Tanya investigatif: 'Apa hubungan antara shadow.exe dengan Charlie Brown?'")
                print("4. Tambah memori baru: 'Ingat fakta ini: [Fakta Baru]'")
                print(f"{C_GRAY}────────────────────────────────────────────────────────────{C_RESET}")
                continue
                
            chat_history = await memory_manager.get_chat_history(session_id, limit=10)
            
            initial_state = {
                "session_id": session_id,
                "query": query,
                "messages": chat_history,
                "context": "",
                "thoughts": [],
                "next_action": {},
                "response": "",
                "step_count": 0
            }
            
            spinner = ConsoleSpinner("Agen sedang menganalisis memori graf")
            spinner.start()
            
            try:
                final_state = await agent_graph.ainvoke(initial_state)
            finally:
                spinner.stop()
                
            if final_state.get("thoughts"):
                print(f"\n{C_YELLOW}🧠 JALUR BERPIKIR AGEN (EPISODIC LOGS):{C_RESET}")
                for idx, thought in enumerate(final_state["thoughts"], 1):
                    print(f"  {C_YELLOW}{idx}.{C_RESET} {C_GRAY}{thought}{C_RESET}")
                    
            print(f"\n{C_CYAN}{C_BOLD}Assistant > {C_RESET}{final_state['response']}")
            print(f"\n{C_GRAY}────────────────────────────────────────────────────────────{C_RESET}")
            
        except KeyboardInterrupt:
            print(f"\n\n{C_YELLOW}[-] Interupsi terdeteksi. Menutup sesi...{C_RESET}")
            break
        except Exception as e:
            print(f"\n{C_RED}[-] Terjadi kesalahan: {e}{C_RESET}")

    await memory_manager.close()

if __name__ == "__main__":
    asyncio.run(run_cli())
