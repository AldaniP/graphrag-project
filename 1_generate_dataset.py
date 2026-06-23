import os
import sys
import random
import asyncio
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

# Load environment variables if .env exists
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Names helper to generate employees
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Elizabeth", 
    "William", "Linda", "David", "Elizabeth", "Richard", "Barbara", "Joseph", "Susan", 
    "Thomas", "Jessica", "Charles", "Sarah", "Christopher", "Karen", "Daniel", "Lisa", 
    "Matthew", "Nancy", "Anthony", "Betty", "Mark", "Sandra", "Donald", "Ashley"
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", 
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", 
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", 
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young"
]

LOCATIONS = [
    "Jakarta HQ", "London Office", "Berlin Branch", "Singapore Data Center",
    "Tokyo Branch", "Sydney Branch", "Seattle Branch", "Paris Office", "San Francisco HQ",
    "Jakarta Server Room 1A", "Jakarta Server Room 1B", "Singapore Server Room 3A", "Singapore Server Room 3B"
]

DEPARTMENTS = [
    "Finance Team", "HR Department", "Operations Division", "IT Support Desk", 
    "Database Engineering", "Security Operations Center", "Executive Board", "Legal Team"
]

ORGANIZATIONS = [
    "DeltaCorp", "CyberGuard Inc", "Aegis Labs", "Fenix Security", "DarkWeb Syndicate"
]

def generate_text_dataset():
    """Generates the raw unstructured text narratives for the breach story in the dataset folder."""
    # Ensure dataset directory exists
    os.makedirs("dataset", exist_ok=True)
    
    narratives = [
        # Report 1: The Phishing Wave
        "NARRATIVE REPORT #001: THE INITIAL PHISHING WAVE\n"
        "On June 12, 2026, a highly targeted spear-phishing campaign was launched against DeltaCorp employees. "
        "The phishing campaign, named 'Operation Credential Harvest', utilized an external email relay server "
        "named MailServer-Z located in Fenix Security's Berlin Branch. The phishing emails contained a malicious link "
        "pointing to 'secure-update-deltacorp.net', a domain registered by the threat group DarkWeb Syndicate. "
        "Five DeltaCorp employees received this email: Charlie Brown (Financial Officer at Jakarta HQ), "
        "Grace Lee (COO at Jakarta HQ), Frank Wright (Database Engineer at London Office), "
        "Susan Miller (HR Manager at Berlin Branch), and Sarah Connor (SysAdmin at Singapore Data Center). "
        "Charlie Brown clicked the link using Laptop-01. Frank Wright also clicked the link using Desktop-05. "
        "Susan Miller clicked the link on Laptop-Berlin-03, while Grace Lee and Sarah Connor successfully flagged "
        "the email and reported it to CyberGuard Inc's Security Operations Center (SOC).",

        # Report 2: Endpoint Compromise & Malware Execution
        "NARRATIVE REPORT #002: ENDPOINT INTRUSION ANALYSIS\n"
        "On June 15, 2026, CyberGuard Inc analyst Alice Smith conducted forensics on Charlie Brown's Laptop-01 "
        "and Frank Wright's Desktop-05. Alice Smith discovered a custom-built Trojan executable file named 'shadow.exe' "
        "installed in the temporary folders of both systems. On Laptop-01, shadow.exe was launched and immediately "
        "injected code into a system process. The malware extracted cached domain credentials from memory, "
        "specifically compromising the local password hashes of Charlie Brown. On Desktop-05, the malware "
        "stored a keystroke logger file named 'keylog.txt' in the root directory. Laptop-01 established "
        "a covert communication channel (beaconing) to the command-and-control (C2) server 'malwaredomain.com' "
        "hosted at IP address 198.51.100.45. Desktop-05 beaconed to another IP address, 198.51.100.99, "
        "which is registered to a proxy host named Proxy-Node-Beta.",

        # Report 3: Lateral Movement to Database Servers
        "NARRATIVE REPORT #003: LATERAL MOVEMENT AND RECONNAISSANCE\n"
        "On June 16, 2026, the attacker utilized compromised credentials from Frank Wright to perform "
        "lateral movement from Desktop-05. The attacker accessed the core database server DB-SQL-01, "
        "which is located in Server Room 3B at the Jakarta HQ. Bob Johnson, DeltaCorp's System Administrator, "
        "discovered anomalous administrative logins on DB-SQL-01 originating from Desktop-05. "
        "Log analysis showed that the attacker executed several database queries targeting a highly sensitive database "
        "called CustomerDataDB on DB-SQL-01. The database CustomerDataDB contains records of over 10,000 corporate clients. "
        "The attacker was also found to have used the remote desktop protocol (RDP) to connect from Laptop-01 "
        "to a staging file server named BackupServer-02, located in the Berlin Branch.",

        # Report 4: Network Infiltration and Log Evasion
        "NARRATIVE REPORT #004: NETWORK ROUTING AND FIREWALL EVASION\n"
        "On June 16, 2026, the Singapore Data Center reported network anomalies. Sarah Connor inspected "
        "the core network router Router-SG-01 and detected unauthorized configuration changes. "
        "The router Router-SG-01 had its routing table modified to bypass the firewall device FireWall-X. "
        "This bypass allowed outbound network packets from Server Room 3B in Jakarta HQ to flow directly "
        "to malwaredomain.com without inspection. FireWall-X, which is managed by Fenix Security, failed to "
        "alert on this traffic because of the router modification. Investigative logs indicate that the "
        "modification command was sent from an internal IP address 10.10.200.5, which is assigned to "
        "a virtual machine named VM-JumpHost-02 running in the Singapore Data Center.",

        # Report 5: Domain Controller Compromise
        "NARRATIVE REPORT #005: ACTIVE DIRECTORY COMPROMISE\n"
        "On June 17, 2026, the incident escalated to a full network compromise. The attacker used credential "
        "harvesting tools on VM-JumpHost-02 to attack the primary Active Directory Domain Controller, DC-ADMIN-01, "
        "located in Jakarta HQ. The attacker successfully gained Domain Administrator privileges by exploiting "
        "a legacy vulnerability in DC-ADMIN-01. With these credentials, the attacker created a rogue domain admin "
        "account named 'ad-service-temp'. System Administrator Bob Johnson noticed the creation of this account "
        "during a routine audit. Bob Johnson immediately flagged the account as unauthorized and notified Fenix Security "
        "to initiate directory-wide password resets.",

        # Report 6: Data Exfiltration and Staging
        "NARRATIVE REPORT #006: DATA ARCHIVING AND EXFILTRATION\n"
        "On June 17, 2026, using the rogue account 'ad-service-temp', the attacker accessed the database DB-SQL-01 "
        "and compressed the client data into a file named 'customer_records_2026.tar.gz'. "
        "The file customer_records_2026.tar.gz was then copied to BackupServer-02 in the Berlin Branch. "
        "David Miller, a Malware Expert from Aegis Labs, confirmed that the attacker initiated an FTP upload "
        "of customer_records_2026.tar.gz from BackupServer-02 to the external storage server file-upload-drop.org "
        "located at IP address 203.0.113.12. The data exfiltration event occurred between 03:00 UTC and 04:30 UTC "
        "and was logged by the local Berlin firewall Berlin-FW-01.",

        # Report 7: Ransomware Payload Deployment
        "NARRATIVE REPORT #007: RANSOMWARE ACTIVATION AND CRYPTO-LOCKING\n"
        "On June 18, 2026, at 06:00 UTC, the threat group DarkWeb Syndicate triggered a ransomware payload "
        "across DeltaCorp's network. The ransomware, identified as a variant named 'FenixLocker', encrypted "
        "files on 25 corporate laptops, including Charlie Brown's Laptop-01 and Susan Miller's Laptop-Berlin-03. "
        "The encrypted files were renamed with the extension '.locked'. On Laptop-Berlin-03, the files encrypted "
        "included 'Contracts_2026.pdf' and 'Salaries_Q2.xlsx'. A ransom note file named 'RESTORE_INSTRUCTIONS.txt' "
        "was created in every directory, demanding a payment of 10 Bitcoins to a specific crypto wallet address.",

        # Report 8: Forensic Analysis of USB Media
        "NARRATIVE REPORT #008: PERIPHERAL INVESTIGATION\n"
        "On June 18, 2026, David Miller of Aegis Labs conducted forensic analysis on a physical USB drive, USB-09, "
        "which was found discarded near Server Room 3B at Jakarta HQ. David Miller discovered that USB-09 contained "
        "a copy of shadow.exe, along with a text file named 'config_pass.txt' containing administrative passwords "
        "for DeltaCorp's network devices. Fingerprint and access log analysis of the Server Room 3B security gate "
        "revealed that the room was accessed using a cloned access card assigned to Frank Wright on June 14, 2026. "
        "This indicates a physical breach component to the digital cyber attack.",

        # Report 9: Emergency Incident Response Task Force
        "NARRATIVE REPORT #009: TASK FORCE COORDINATION AND CONTAINMENT\n"
        "On June 18, 2026, an emergency event named 'Joint Incident Command Center' was established at Singapore HQ. "
        "The event was chaired by Grace Lee. Key attendees included Alice Smith (CyberGuard Inc), "
        "David Miller (Aegis Labs), Bob Johnson (DeltaCorp), and Victor Vance (Incident Response Lead at Fenix Security). "
        "The task force agreed on immediate containment steps: isolating VM-JumpHost-02, disabling the rogue domain account "
        "ad-service-temp, restoring the routing table on Router-SG-01, and placing BackupServer-02 in quarantine. "
        "CyberGuard Inc agreed to monitor all network traffic for further beaconing to malwaredomain.com.",

        # Report 10: Legal Actions & Endpoint Remediation
        "NARRATIVE REPORT #010: POST-INCIDENT REMEDIATION AND LEGAL RESPONSE\n"
        "On June 19, 2026, DeltaCorp's legal team, led by general counsel Karen Nelson, filed a formal complaint "
        "with law enforcement against the hacker group DarkWeb Syndicate. Aegis Labs provided a detailed threat "
        "intelligence report containing threat actor profiles to Karen Nelson. Meanwhile, Bob Johnson and "
        "Alice Smith deployed a new endpoint detection agent named SecurityAgent-Pro on all DeltaCorp workstations. "
        "SecurityAgent-Pro successfully deleted FenixLocker and shadow.exe from Frank Wright's Desktop-05. "
        "Fenix Security confirmed that the external command-and-control domain malwaredomain.com has been sinkholed "
        "by national cybersecurity authorities, successfully preventing any further data exfiltration attempts."
    ]
    
    # Save the narratives to dataset/dataset.txt
    output_filename = os.path.join("dataset", "dataset.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n\n=== END OF REPORT ===\n\n".join(narratives))
    
    print(f"[+] Default text narratives saved to '{output_filename}'.")

async def populate_large_scale_data():
    """Generates the structured network topology and loads it directly to Neo4j."""
    print("[*] Connecting to Neo4j database to inject default network topology (>500 nodes)...")
    
    # Verify .env config
    if not os.path.exists(".env"):
        print("[!] Warning: .env file is missing. Skipping database injection.")
        print("    Please copy .env.example to .env, set credentials, and run this script again to load the topology.")
        return
        
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    # 1. Generate 150 unique Employees
    employees = []
    generated_names = set()
    core_employees = {"Alice Smith", "Bob Johnson", "Charlie Brown", "David Miller", "Eve Torres", "Grace Lee", "Frank Wright", "Susan Miller", "Sarah Connor", "Victor Vance", "Karen Nelson"}
    generated_names.update(core_employees)
    
    while len(employees) < 150:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in generated_names:
            generated_names.add(name)
            employees.append({
                "id": name,
                "role": f"{random.choice(['Staff', 'Senior Specialist', 'Manager', 'Lead'])} of {random.choice(['IT', 'Security', 'Finance', 'HR', 'Ops'])}",
                "email": f"{name.lower().replace(' ', '.')}@deltacorp.net"
            })
            
    # 2. Generate 150 Endpoints (Laptops/Desktops)
    endpoints = []
    for i in range(1, 151):
        endpoints.append({
            "id": f"Laptop-Corp-{i:03d}" if i % 2 == 0 else f"Desktop-Corp-{i:03d}",
            "os": random.choice(["Windows 11", "macOS Sequoia", "Ubuntu 24.04"]),
            "status": random.choice(["Active", "Active", "Active", "Quarantined", "Patched"])
        })
        
    # 3. Generate 50 Servers
    servers = []
    for i in range(1, 51):
        srv_type = random.choice(["DB", "WEB", "FILE", "APP", "MAIL", "BACKUP"])
        servers.append({
            "id": f"{srv_type}-SRV-{i:02d}",
            "role": f"Production {srv_type} server",
            "version": random.choice(["RHEL 9", "Windows Server 2022", "Ubuntu Server 22.04"])
        })
        
    # 4. Generate 30 Network Devices
    network_devices = []
    for i in range(1, 31):
        dev_type = random.choice(["Router", "Firewall", "Switch"])
        network_devices.append({
            "id": f"{dev_type}-{random.choice(['Jakarta', 'Singapore', 'Berlin', 'London'])}-{i:02d}",
            "firmware": "v8.4.1-patch2",
            "model": random.choice(["Cisco Catalyst", "Palo Alto Networks", "Juniper SRX"])
        })
        
    # 5. Generate 200 IP Addresses
    ip_addresses = []
    for i in range(1, 201):
        ip_addresses.append({
            "id": f"10.10.{random.randint(1, 254)}.{random.randint(1, 254)}",
            "subnet": "10.10.0.0/16",
            "dns_name": f"host-{i}.internal.deltacorp.net"
        })
        
    # 6. Generate 100 Event Logs
    event_logs = []
    for i in range(1, 101):
        event_logs.append({
            "id": f"AuditLog-2026-{i:04d}",
            "severity": random.choice(["INFO", "INFO", "WARNING", "WARNING", "CRITICAL"]),
            "timestamp": f"2026-06-{random.randint(12, 19)}T{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00Z",
            "action": random.choice(["Login Success", "SSH Connect", "File Access", "Config Change", "Policy Block"])
        })

    try:
        async with driver:
            await driver.verify_connectivity()
            
            async with driver.session() as session:
                print("[*] Inserting structural nodes (Locations, Orgs, Departments)...")
                await session.run("UNWIND $locations AS loc MERGE (:Location {id: loc})", locations=LOCATIONS)
                await session.run("UNWIND $orgs AS org MERGE (:Organization {id: org})", orgs=ORGANIZATIONS)
                for dept in DEPARTMENTS:
                    await session.run(
                        "MERGE (d:Organization {id: $dept}) "
                        "MERGE (parent:Organization {id: 'DeltaCorp'}) "
                        "MERGE (d)-[:PART_OF]->(parent)",
                        dept=dept
                    )
                
                print("[*] Inserting 150 Employees...")
                await session.run(
                    "UNWIND $employees AS emp MERGE (p:Person {id: emp.id}) SET p.role = emp.role, p.email = emp.email, p.type = 'Person'", 
                    employees=employees
                )
                
                print("[*] Linking Employees to locations and departments...")
                link_emp_query = """
                MATCH (p:Person) WHERE NOT p.id IN $core_employees
                WITH p, rand() AS r ORDER BY r
                WITH p, $locations[toInteger(rand() * size($locations))] AS loc_id
                MATCH (l:Location {id: loc_id})
                MERGE (p)-[:WORKS_AT]->(l)
                WITH p, $depts[toInteger(rand() * size($depts))] AS dept_id
                MATCH (d:Organization {id: dept_id})
                MERGE (p)-[:BELONGS_TO]->(d)
                WITH p, ['Grace Lee', 'Bob Johnson', 'Susan Miller', 'Sarah Connor'] AS managers
                MATCH (m:Person {id: managers[toInteger(rand() * size(managers))]})
                MERGE (p)-[:REPORTS_TO]->(m)
                """
                await session.run(link_emp_query, locations=LOCATIONS, depts=DEPARTMENTS, core_employees=list(core_employees))
                
                print("[*] Inserting 150 Endpoints...")
                await session.run(
                    "UNWIND $endpoints AS end MERGE (o:Object {id: end.id}) SET o.os = end.os, o.status = end.status, o.type = 'Object', o.subtype = 'Endpoint'", 
                    endpoints=endpoints
                )
                
                print("[*] Linking Endpoints to locations and employees...")
                link_endpoints_query = """
                MATCH (o:Object) WHERE o.subtype = 'Endpoint' AND NOT o.id IN ['Laptop-01', 'Desktop-05', 'Laptop-Berlin-03']
                WITH o
                WITH o, $locations[toInteger(rand() * size($locations))] AS loc_id
                MATCH (l:Location {id: loc_id})
                MERGE (o)-[:LOCATED_AT]->(l)
                WITH o
                MATCH (p:Person) WHERE NOT p.id IN $core_employees AND NOT (p)-[:USES]->(:Object)
                WITH o, p LIMIT 1
                MERGE (p)-[:USES]->(o)
                """
                await session.run(link_endpoints_query, locations=LOCATIONS, core_employees=list(core_employees))
                
                print("[*] Inserting 50 Servers...")
                await session.run(
                    "UNWIND $servers AS srv MERGE (o:Object {id: srv.id}) SET o.role = srv.role, o.version = srv.version, o.type = 'Object', o.subtype = 'Server'", 
                    servers=servers
                )
                
                print("[*] Linking Servers to locations...")
                link_servers_query = """
                MATCH (o:Object) WHERE o.subtype = 'Server' AND NOT o.id IN ['DB-SQL-01', 'BackupServer-02', 'DC-ADMIN-01']
                WITH o
                WITH o, ['Singapore Data Center', 'Singapore Server Room 3A', 'Singapore Server Room 3B', 'Jakarta HQ', 'Jakarta Server Room 1A', 'Jakarta Server Room 1B'] AS dc_locs
                MATCH (l:Location {id: dc_locs[toInteger(rand() * size(dc_locs))]})
                MERGE (o)-[:LOCATED_AT]->(l)
                """
                await session.run(link_servers_query)
                
                print("[*] Inserting 30 Network Devices...")
                await session.run(
                    "UNWIND $net AS dev MERGE (o:Object {id: dev.id}) SET o.firmware = dev.firmware, o.model = dev.model, o.type = 'Object', o.subtype = 'NetworkDevice'", 
                    net=network_devices
                )
                
                print("[*] Creating network topology...")
                await session.run(
                    "MATCH (o:Object) WHERE o.subtype = 'NetworkDevice' WITH o WITH o, $locations[toInteger(rand() * size($locations))] AS loc_id MATCH (l:Location {id: loc_id}) MERGE (o)-[:LOCATED_AT]->(l)", 
                    locations=LOCATIONS
                )
                await session.run(
                    "MATCH (d1:Object) WHERE d1.subtype = 'NetworkDevice' MATCH (d2:Object) WHERE d2.subtype = 'NetworkDevice' AND d1 <> d2 WITH d1, d2, rand() AS r WHERE r < 0.08 MERGE (d1)-[:CONNECTS_TO]->(d2)"
                )
                
                print("[*] Inserting 200 IP Addresses...")
                await session.run(
                    "UNWIND $ips AS ip MERGE (l:Location {id: ip.id}) SET l.subnet = ip.subnet, l.dns_name = ip.dns_name, l.type = 'Location'", 
                    ips=ip_addresses
                )
                
                print("[*] Linking IP addresses to endpoints and servers...")
                link_ip_query = """
                MATCH (o:Object) WHERE o.subtype IN ['Endpoint', 'Server'] AND NOT (o)-[:HAS_IP]->(:Location)
                MATCH (ip:Location) WHERE ip.id STARTS WITH '10.10.' AND NOT (:Object)-[:HAS_IP]->(ip)
                WITH o, ip LIMIT 1
                MERGE (o)-[:HAS_IP]->(ip)
                """
                for _ in range(15):
                    await session.run(link_ip_query)
                
                print("[*] Inserting 100 Event Logs...")
                await session.run(
                    "UNWIND $events AS ev MERGE (e:Event {id: ev.id}) SET e.severity = ev.severity, e.timestamp = datetime(ev.timestamp), e.action = ev.action, e.type = 'Event'", 
                    events=event_logs
                )
                
                print("[*] Linking Event Logs to entities...")
                link_events_query = """
                MATCH (e:Event) WHERE e.id STARTS WITH 'AuditLog-' WITH e
                WITH e, $locations[toInteger(rand() * size($locations))] AS loc_id MATCH (l:Location {id: loc_id}) MERGE (e)-[:OCCURRED_AT]->(l)
                WITH e MATCH (p:Person) WITH e, p, rand() AS r ORDER BY r LIMIT 1 MERGE (e)-[:INVOLVES]->(p)
                WITH e MATCH (s:Object) WHERE s.subtype = 'Server' WITH e, s, rand() AS r ORDER BY r LIMIT 1 MERGE (e)-[:TARGETED]->(s)
                """
                await session.run(link_events_query, locations=LOCATIONS)
                
                print("[*] Verifying database node counts in Neo4j...")
                res = await session.run(
                    "MATCH (n) WHERE labels(n)[0] IN ['Person', 'Object', 'Location', 'Event', 'Organization'] "
                    "RETURN labels(n)[0] AS label, count(n) AS count"
                )
                print("\n=== DATABASE NODE COUNTS ===")
                total = 0
                async for rec in res:
                    print(f"  - {rec['label']}: {rec['count']}")
                    total += rec['count']
                print(f"  * Total Nodes: {total}")
                print("============================\n")
                
    except Exception as e:
        print(f"[-] Database connection failed: {e}")
        print("    Please ensure your Neo4j instance is running and credentials in '.env' are correct.")

async def main():
    print("=" * 60)
    print("DELTA CORP DATASET GENERATOR (TEXT & GRAPH TOPOLOGY)")
    print("=" * 60)
    
    # 1. Generate text narrative inside dataset folder
    generate_text_dataset()
    
    # 2. Inject large network topology into Neo4j
    await populate_large_scale_data()
    
    print("\n[+] Dataset generation and initialization complete!")
    print("    Next step: Run `python3 2_graph_builder.py` to extract narrative facts.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
