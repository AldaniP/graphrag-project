import os
import re
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase
from mcp.server.fastmcp import FastMCP

# Load env
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

class Neo4jMemoryServer:
    def __init__(self, uri=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD):
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None

    async def connect(self):
        if not self.driver:
            self.driver = AsyncGraphDatabase.driver(
                self.uri, 
                auth=(self.username, self.password),
                notifications_min_severity="WARNING"
            )
            await self.driver.verify_connectivity()
            print("[+] Neo4jMemoryServer connected successfully.")

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None
            print("[-] Neo4jMemoryServer connection closed.")

    async def init_constraints(self):
        """Creates indexes and constraints for memory storage."""
        queries = [
            "CREATE CONSTRAINT unique_session_id IF NOT EXISTS FOR (s:Session) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT unique_message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
            "CREATE INDEX node_id_index IF NOT EXISTS FOR (n:Person) ON (n.id)",
            "CREATE INDEX obj_id_index IF NOT EXISTS FOR (o:Object) ON (o.id)",
            "CREATE INDEX loc_id_index IF NOT EXISTS FOR (l:Location) ON (l.id)",
            "CREATE INDEX org_id_index IF NOT EXISTS FOR (org:Organization) ON (org.id)",
            "CREATE INDEX ev_id_index IF NOT EXISTS FOR (e:Event) ON (e.id)"
        ]
        async with self.driver.session() as session:
            for q in queries:
                try:
                    await session.run(q)
                except Exception as e:
                    print(f"[-] Index/Constraint Creation Error: {e}")

    # ==========================================
    # 1. SHORT-TERM MEMORY (Session & Message)
    # ==========================================

    async def create_session(self, session_id: str):
        """Creates a session node if it doesn't exist."""
        query = """
        MERGE (s:Session {id: $session_id})
        ON CREATE SET s.created_at = datetime()
        RETURN s
        """
        async with self.driver.session() as session:
            await session.run(query, session_id=session_id)

    async def add_message(self, session_id: str, role: str, content: str):
        """Adds a message to the session and chains it to the previous message."""
        msg_id = f"{session_id}_{datetime.utcnow().timestamp()}"
        
        # Cypher query to:
        # 1. Create the Message node
        # 2. Link Session -> Message
        # 3. Chain Message -> previous Message (linked-list)
        query = """
        MATCH (s:Session {id: $session_id})
        CREATE (m:Message {id: $msg_id, role: $role, content: $content, timestamp: datetime()})
        CREATE (s)-[:HAS_MESSAGE]->(m)
        
        WITH s, m
        MATCH (s)-[:HAS_MESSAGE]->(prev:Message)
        WHERE prev <> m
        WITH m, prev
        ORDER BY prev.timestamp DESC
        LIMIT 1
        MERGE (prev)-[:NEXT]->(m)
        
        RETURN m.id
        """
        async with self.driver.session() as session:
            # First ensure session exists
            await self.create_session(session_id)
            await session.run(query, session_id=session_id, msg_id=msg_id, role=role, content=content)

    async def get_chat_history(self, session_id: str, limit: int = 15):
        """Retrieves ordered chat history for a session."""
        query = """
        MATCH (s:Session {id: $session_id})-[:HAS_MESSAGE]->(m:Message)
        RETURN m.role AS role, m.content AS content, m.timestamp AS timestamp
        ORDER BY m.timestamp ASC
        LIMIT $limit
        """
        async with self.driver.session() as session:
            result = await session.run(query, session_id=session_id, limit=limit)
            history = []
            async for record in result:
                history.append({
                    "role": record["role"],
                    "content": record["content"],
                    "timestamp": str(record["timestamp"])
                })
            return history

    # ==========================================
    # 2. LONG-TERM MEMORY (POLE+O Facts)
    # ==========================================

    async def write_fact_node(self, entity_id: str, entity_type: str, properties: dict):
        """Writes/Updates a long-term fact node."""
        valid_labels = {"Person", "Object", "Location", "Event", "Organization"}
        label = entity_type if entity_type in valid_labels else "Entity"
        
        props = dict(properties)
        props["id"] = entity_id
        props["type"] = label
        props["updated_at"] = str(datetime.utcnow())
        
        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $props
        RETURN n
        """
        async with self.driver.session() as session:
            await session.run(query, id=entity_id, props=props)

    async def write_fact_relationship(self, source_id: str, target_id: str, rel_type: str, properties: dict):
        """Writes/Updates relationship between facts."""
        rel_type = re.sub(r'[^a-zA-Z0-9_]', '', rel_type.upper().replace(" ", "_"))
        if not rel_type:
            rel_type = "RELATED_TO"
            
        props = dict(properties)
        props["updated_at"] = str(datetime.utcnow())
        
        query = f"""
        MATCH (s {{id: $source_id}})
        MATCH (t {{id: $target_id}})
        MERGE (s)-[r:{rel_type}]->(t)
        SET r += $props
        RETURN r
        """
        async with self.driver.session() as session:
            await session.run(query, source_id=source_id, target_id=target_id, props=props)

    async def search_facts(self, query_text: str, limit: int = 10) -> str:
        """
        Retrieves relevant sub-graphs based on entity matching (GraphRAG).
        Looks for nodes whose IDs are mentioned in the query_text, OR nodes whose IDs/properties
        contain keywords from the query_text.
        """
        # Clean and tokenize query text
        # Stopwords to filter out from general keyword matching
        stopwords = {
            "dan", "di", "dari", "yang", "ke", "ini", "itu", "pada", "dengan", "adalah", "yaitu", "seperti", "oleh",
            "the", "of", "to", "and", "a", "in", "is", "it", "you", "that", "he", "was", "for", "on", "are", "as", "with",
            "what", "where", "did", "come", "from", "who", "how", "why", "about", "berasal", "darimana", "apa", "siapa", "mengapa", "bagaimana", "dimana", "virusnya"
        }
        
        words = [re.sub(r'[^a-zA-Z0-9.\-_]', '', w).lower() for w in query_text.split()]
        keywords = [w for w in words if w and w not in stopwords and len(w) >= 3]
        
        # Suffix handling: e.g. "virusnya" -> also add "virus"
        extra_keywords = []
        for kw in keywords:
            if kw.endswith("nya") and len(kw) > 3:
                extra_keywords.append(kw[:-3])
        keywords.extend(extra_keywords)
        
        if not keywords and words:
            keywords = [w for w in words if w and len(w) >= 2]
            
        matched_ids = []
        
        async with self.driver.session() as session:
            # 1. First pass: Check if any node ID is explicitly mentioned in the query text (original template logic)
            result = await session.run(
                "MATCH (n) WHERE labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization'] "
                "RETURN n.id AS id"
            )
            async for record in result:
                node_id = record["id"]
                if re.search(r'\b' + re.escape(node_id) + r'\b', query_text, re.IGNORECASE):
                    matched_ids.append(node_id)
            
            # 2. Second pass: Search database for nodes where their ID or properties contain any keywords (semantic lookup)
            if keywords:
                search_query = """
                MATCH (n)
                WHERE labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization']
                AND any(kw in $keywords WHERE 
                  toLower(n.id) CONTAINS kw 
                  OR any(prop in keys(n) WHERE toLower(toString(n[prop])) CONTAINS kw)
                )
                RETURN n.id AS id
                LIMIT 50
                """
                res = await session.run(search_query, keywords=keywords)
                async for rec in res:
                    nid = rec["id"]
                    if nid not in matched_ids:
                        matched_ids.append(nid)
                        
            # 3. Fallback: If still no nodes matched, return a descriptive summary of the database
            if not matched_ids:
                summary_query = """
                MATCH (n) WHERE labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization']
                RETURN labels(n)[0] AS type, collect(n.id)[0..5] AS samples, count(n) AS total
                """
                res = await session.run(summary_query)
                summary_text = "No specific entities matched your query. However, the long-term memory contains the following entity types and samples:\n"
                has_data = False
                async for rec in res:
                    has_data = True
                    samples_str = ", ".join(rec["samples"])
                    summary_text += f"- {rec['type']} (Total: {rec['total']}): {samples_str}\n"
                
                if not has_data:
                    return "No facts found in long-term memory database. It is currently empty."
                return summary_text
                
            # 4. Retrieve 1-hop subgraph details for matched nodes
            subgraph_query = """
            MATCH (n)-[r]->(m)
            WHERE (n.id IN $matched_ids OR m.id IN $matched_ids)
            AND labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization']
            AND labels(m)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization']
            RETURN n.id AS source, labels(n)[0] AS source_type, 
                   type(r) AS rel, 
                   m.id AS target, labels(m)[0] AS target_type
            LIMIT $limit
            """
            
            result_sub = await session.run(subgraph_query, matched_ids=matched_ids, limit=limit)
            facts = []
            async for record in result_sub:
                facts.append(
                    f"({record['source']}:{record['source_type']}) -[{record['rel']}]-> "
                    f"({record['target']}:{record['target_type']})"
                )
            
            # Also append individual properties of matched nodes
            prop_query = """
            MATCH (n) WHERE n.id IN $matched_ids
            AND labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization']
            RETURN n.id AS id, labels(n)[0] AS type, properties(n) AS props
            """
            result_props = await session.run(prop_query, matched_ids=matched_ids)
            node_facts = []
            async for record in result_props:
                raw_props = record["props"] or {}
                clean_props = {}
                for k, v in raw_props.items():
                    if k not in ["id", "type"]:
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            clean_props[k] = v
                        else:
                            clean_props[k] = str(v)
                if clean_props:
                    node_facts.append(f"Entity '{record['id']}' ({record['type']}) properties: {json.dumps(clean_props)}")
            
            final_report = "### MATCHED GRAPH FACTS:\n"
            if facts:
                final_report += "\n".join(facts) + "\n\n"
            if node_facts:
                final_report += "### ENTITY PROPERTIES:\n" + "\n".join(node_facts)
                
            return final_report


    # ==========================================
    # 3. EPISODIC MEMORY (ReasoningStep & Action)
    # ==========================================

    async def log_reasoning_step(self, session_id: str, step_index: int, thought: str, action_name: str, action_details: str):
        """Saves a step in the agent's reasoning process and ties it to an action."""
        step_id = f"step_{session_id}_{step_index}_{datetime.utcnow().timestamp()}"
        act_id = f"act_{session_id}_{step_index}_{datetime.utcnow().timestamp()}"
        
        query = """
        MATCH (s:Session {id: $session_id})
        CREATE (rs:ReasoningStep {id: $step_id, step_index: $step_index, thought: $thought, timestamp: datetime()})
        CREATE (act:Action {id: $act_id, name: $action_name, details: $action_details, timestamp: datetime()})
        CREATE (s)-[:HAS_REASONING]->(rs)
        CREATE (rs)-[:EXECUTED]->(act)
        
        WITH s, rs
        MATCH (s)-[:HAS_REASONING]->(prev:ReasoningStep)
        WHERE prev <> rs
        WITH rs, prev
        ORDER BY prev.step_index DESC, prev.timestamp DESC
        LIMIT 1
        MERGE (prev)-[:NEXT_STEP]->(rs)
        
        RETURN rs.id
        """
        async with self.driver.session() as session:
            await self.create_session(session_id)
            await session.run(
                query, 
                session_id=session_id, 
                step_id=step_id, 
                step_index=step_index, 
                thought=thought, 
                act_id=act_id, 
                action_name=action_name, 
                action_details=action_details
            )

    async def delete_session_history(self, session_id: str):
        """Deletes short-term (Message) and episodic (ReasoningStep, Action) memories for a session, preserving long-term facts."""
        query = """
        MATCH (s:Session {id: $session_id})
        OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message)
        OPTIONAL MATCH (s)-[:HAS_REASONING]->(rs:ReasoningStep)-[:EXECUTED]->(act:Action)
        DETACH DELETE s, m, rs, act
        """
        async with self.driver.session() as session:
            await session.run(query, session_id=session_id)

# Create MCP server instance
mcp_server = FastMCP("Neo4j Distributed Memory Server")
memory_manager = Neo4jMemoryServer()

@mcp_server.tool()
async def save_chat_message(session_id: str, role: str, content: str) -> str:
    """Saves a user or assistant message to the short-term memory of a session."""
    await memory_manager.connect()
    await memory_manager.add_message(session_id, role, content)
    return f"Saved {role} message to short-term memory."

@mcp_server.tool()
async def get_session_history(session_id: str, limit: int = 15) -> str:
    """Retrieves the chat history for a session from short-term memory."""
    await memory_manager.connect()
    history = await memory_manager.get_chat_history(session_id, limit)
    return json.dumps(history, indent=2)

@mcp_server.tool()
async def search_memory_graph(query_text: str, limit: int = 10) -> str:
    """Performs a GraphRAG search in long-term memory to retrieve relevant entities and subgraphs."""
    await memory_manager.connect()
    facts = await memory_manager.search_facts(query_text, limit)
    return facts

@mcp_server.tool()
async def write_fact(entity_id: str, entity_type: str, properties_json: str) -> str:
    """Writes or updates an entity (Person, Object, Location, Event, Organization) in long-term memory."""
    await memory_manager.connect()
    try:
        props = json.loads(properties_json)
    except Exception:
        props = {"raw": properties_json}
    await memory_manager.write_fact_node(entity_id, entity_type, props)
    return f"Saved fact: {entity_id} ({entity_type})"

@mcp_server.tool()
async def create_fact_relationship(source_id: str, target_id: str, rel_type: str, properties_json: str = "{}") -> str:
    """Creates a relationship between two long-term memory entities."""
    await memory_manager.connect()
    try:
        props = json.loads(properties_json)
    except Exception:
        props = {}
    await memory_manager.write_fact_relationship(source_id, target_id, rel_type, props)
    return f"Created relationship: {source_id} -[{rel_type}]-> {target_id}"

@mcp_server.tool()
async def log_episodic_reasoning(session_id: str, step_index: int, thought: str, action_name: str, action_details: str) -> str:
    """Logs the agent's episodic reasoning trace (thought and action) for a session."""
    await memory_manager.connect()
    await memory_manager.log_reasoning_step(session_id, step_index, thought, action_name, action_details)
    return f"Logged reasoning step {step_index}."

@mcp_server.tool()
async def clear_session_history(session_id: str) -> str:
    """Deletes a session's short-term and episodic memory logs from Neo4j, while keeping long-term facts untouched."""
    await memory_manager.connect()
    await memory_manager.delete_session_history(session_id)
    return f"Successfully cleared session {session_id} chat history and reasoning logs, preserving all long-term facts."

if __name__ == "__main__":
    # When executed, start the MCP server
    print("[*] Running Neo4j Memory Server as MCP service...")
    mcp_server.run()
